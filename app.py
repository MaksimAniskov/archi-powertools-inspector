import lib
import plugin_registry

import argparse
import logging
import git
import xml.etree.ElementTree as ET
import plugin_registry
import urllib.parse
import pathlib
import os


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


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.password:
        return parsed._replace(
            netloc=parsed.netloc.replace(parsed.password, "REDACTED")
        ).geturl()
    return url


def main():

    __cli_args = __init_cli().parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname).1s %(message)s", level=__cli_args.log
    )
    logger = logging.getLogger("app")

    plugins = plugin_registry.Registry(
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
        changes_detected |= lib.processFile(logger, plugins, file)

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


if __name__ == "__main__":  # pragma: no cover
    main()
