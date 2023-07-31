import argparse
import logging
import typing
import git
import xml.etree.ElementTree as ET
import xml.sax.saxutils
import plugin_registry
import urllib.parse
import hashlib
import re
import io
import os
import pathlib


def __description() -> str:
    return "TODO: Description"


def __init_cli() -> argparse:
    parser = argparse.ArgumentParser(description=__description())  # , usage=__usage())
    parser.add_argument(
        "coarchi_git_repo_url",
        help="Url of git repository which contains Archi model in coArchi format. See https://github.com/archimatetool/archi-modelrepository-plugin",
    )

    parser.add_argument("git_clone_dir")

    parser.add_argument("--nocommit", action="store_true")

    parser.add_argument(
        "-l",
        "--log",
        default="INFO",
        help="""
        Specify log level which should use. Default will always be DEBUG, choose between the following options
        CRITICAL, ERROR, WARNING, INFO, DEBUG
        """,
    )

    return parser


def writeXmlTreeInArchiFormat(
    element: ET.Element, file: io.TextIOBase, indentation: int = 0
):
    xsi_tag_match = re.match(
        r"{http://www.archimatetool.com/archimate}(?P<tag>.+)", element.tag
    )
    if xsi_tag_match is None:
        tag = element.tag
        file.write(f"{' '*indentation}<{tag}")
    else:
        tag = "archimate:" + xsi_tag_match.group("tag")
        file.write(f"{' '*indentation}<{tag}\n")
        file.write(
            f'{" "*indentation}    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n'
        )
        file.write(
            f'{" "*indentation}    xmlns:archimate="http://www.archimatetool.com/archimate"'
        )

    for attr_name in element.attrib:
        file.write(
            f'\n{" "*indentation}    {attr_name.replace("{http://www.w3.org/2001/XMLSchema-instance}", "xsi:")}='
            + xml.sax.saxutils.quoteattr(
                element.attrib[attr_name], entities={'"': "&quot;"}
            )
        )

    if len(element) == 0:
        file.write(f"/>\n")
    else:
        file.write(f">\n")
        for child in list(element):
            writeXmlTreeInArchiFormat(child, file, indentation=indentation + 2)
        file.write(f"</{tag}>\n")


def upsertProperty(tree: ET.ElementTree, key, value):
    e = tree.find(f"./properties[@key='{key}']")
    if e is None:
        e = ET.Element("properties")
        e.set("key", key)
        tree.append(e)
    e.set("value", value)


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.password:
        return parsed._replace(
            netloc=parsed.netloc.replace(parsed.password, "REDACTED")
        ).geturl()
    return url


def processFile(
    file_name: str, out_file_name: str = None, log_indentation: int = 0
) -> bool:
    logger.info(f'{" "*log_indentation}Processing file: {file_name}')

    if out_file_name is None:
        out_file_name = file_name

    requires_reviewing: bool = False

    tree = ET.parse(file_name)
    root = tree.getroot()

    deps = root.find("./properties[@key='pwrt:inspector:value-deps']")
    if deps is None:
        logger.info(
            f'{" "*log_indentation}  No top-level properties tag with key="pwrt:inspector:value-deps". Skipping this file'
        )
        return False

    deps_arr: typing.List[str] = deps.get("value").split(";")
    deps_hashes = root.find("./properties[@key='pwrt:inspector:value-deps-hashes']")
    deps_hashes_arr: typing.List[str] = (
        deps_hashes.get("value").split(";") if deps_hashes is not None else None
    )

    deps_mismatches: typing.List[str] = []
    deps_hashes_calculated: typing.List[str] = []
    for i, deps_url in enumerate(deps_arr):
        logger.debug(f'{" "*log_indentation}  Processing value dependency: {deps_url}')
        url = urllib.parse.urlparse(deps_url)
        url_resolver: plugin_registry.IUrlResolver = plugin_registry.getUrlResolver(
            plugins, url.scheme
        )
        hash_known = (
            deps_hashes_arr[i]
            if deps_hashes_arr and i < len(deps_hashes_arr)
            else "~none~"
        )
        content: str = url_resolver.resolveToContent(deps_url)
        if content is None:
            hash_calculated = "~none~"
        else:
            logger.debug(f'{" "*log_indentation}    Resolved content: {content}')
            hash_calculated = hashlib.shake_128(content).hexdigest(4)
            logger.debug(
                f'{" "*log_indentation}    Hash of resolved content: {hash_calculated}. Hash known in pwrt:inspector:value-deps-hashes: {hash_known}{". Mismatch!" if hash_calculated != hash_known else ""}'
            )
        if hash_calculated != hash_known:
            deps_mismatches.append(deps_url)
        deps_hashes_calculated.append(hash_calculated)

    if len(deps_mismatches) == 0:
        logger.debug(f'{" "*log_indentation}  No changes detected.')
    else:
        logger.debug(f'{" "*log_indentation}  Changes detected in: {deps_mismatches}')
        requires_reviewing = True
        upsertProperty(
            root, "pwrt:inspector:value-deps-hashes", ";".join(deps_hashes_calculated)
        )

    value_new_str = "~none~"
    value_ref = root.find("./properties[@key='pwrt:inspector:value-ref']")
    if value_ref is not None:
        value_ref_url: str = value_ref.get("value")
        logger.debug(f'{" "*log_indentation}  Processing value ref: {value_ref_url}')
        url = urllib.parse.urlparse(value_ref_url)
        url_resolver: plugin_registry.IUrlResolver = plugin_registry.getUrlResolver(
            plugins, url.scheme
        )
        value_str: str = url_resolver.resolveToContent(value_ref_url)
        if value_str:
            logger.debug(
                f'{" "*log_indentation}    Ref resolved to content: {value_str}'
            )
            value_regexp = root.find("./properties[@key='pwrt:inspector:value-regexp']")
            value_regexp_str: str = value_regexp.get("value")
            logger.debug(
                f'{" "*log_indentation}    Ref regexp (in quotes "): "{value_regexp_str}"'
            )
            value_new_str = re.search(
                value_regexp_str, value_str.decode("utf-8")
            ).groups()[0]

    value_known_str = "~none~"
    value_known = root.find("./properties[@key='pwrt:inspector:value']")
    if value_known is not None:
        value_known_str: str = value_known.get("value")
        logger.debug(
            f'{" "*log_indentation}    Current value: {value_new_str}. Value known in pwrt:inspector:value: {value_known_str}{". Mismatch!" if value_new_str != value_known_str else ""}'
        )

    if value_new_str != value_known_str:
        requires_reviewing = True
        upsertProperty(root, "pwrt:inspector:value-new", value_new_str)

    if requires_reviewing:
        logger.debug(
            f'{" "*log_indentation}  Setting "pwrt:inspector:value-requires-reviewing"="true"'
        )
        upsertProperty(root, "pwrt:inspector:value-requires-reviewing", "true")

        logger.info(
            f'{" "*log_indentation}  Changes detected. Generating output to {out_file_name}'
        )

        root[:] = sorted(
            root,
            key=lambda child: child.tag
            + "<>"
            + ("" if child.get("key") is None else child.get("key")),
        )

        f = open(out_file_name, "w")
        writeXmlTreeInArchiFormat(tree.getroot(), f)
        f.close()
        return True
    else:
        logger.info(f'{" "*log_indentation}  No changes detected')
        return False


if __name__ == "__main__":
    __cli_args = __init_cli().parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname).1s %(message)s", level=__cli_args.log
    )
    logger = logging.getLogger("app")

    plugins: typing.List[plugin_registry.IPlugin] = plugin_registry.Registry(
        plugin_directory="plugins", logger=logger
    ).loadPlugins()
    plugins = [P(logger) for P in plugins]

    coarchi_git_repo_url: str = __cli_args.coarchi_git_repo_url
    git_clone_dir: str = __cli_args.git_clone_dir

    logger.info(f"Processing coArchi repo: {redact_url(coarchi_git_repo_url)}")
    logger.info(f"Local clone dir: {git_clone_dir}")
    if os.path.exists(git_clone_dir):
        if not os.path.isdir(git_clone_dir):
            raise Exception(f"Can not use {git_clone_dir} as local clone dir.")
        else:
            logger.info("Local clone dir exists. Pulling...")
            cloned_repo = git.Repo(git_clone_dir)
            git.remote.Remote(cloned_repo, "origin").pull()
            logger.info("... Pulled")
    else:
        logger.info("Local clone dir does not exist. Cloning...")
        cloned_repo = git.Repo.clone_from(
            coarchi_git_repo_url, git_clone_dir
        )  # TODO: No history
        logger.info("... Cloned")

    changes_detected = False
    files = pathlib.Path(git_clone_dir).glob("model/**/*.xml")
    for file in files:
        changes_detected |= processFile(file)

    if changes_detected and not __cli_args.nocommit:
        logger.info("Preparing git commit...")
        modified_files_map = map(lambda item: item.a_path, cloned_repo.index.diff(None))
        cloned_repo.index.add(modified_files_map)
        cloned_repo.index.commit(
            "Report detected changes",
            author=git.Actor(
                "Archi Power Tools Inspector", "some@email.com"
            ),  # TODO: Make email configurable
        )
        logger.info("Pushing to the origin...")
        cloned_repo.remotes.origin.push()

    logger.info("Done")
