import plugin_registry

import typing
import xml.etree.ElementTree as ET
import xml.sax.saxutils
import hashlib
import re
import io
import urllib.parse

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


def processFile(
    logger, plugins, file_name: str, out_file_name: str = None, log_indentation: int = 0
) -> bool:

    logger.info(f'{" "*log_indentation}Processing file: {file_name}')

    if out_file_name is None:
        out_file_name = file_name

    changed_detected: bool = False
    requires_reviewing: bool = False

    tree = ET.parse(file_name)
    root = tree.getroot()

    if (
        root.find("./properties[@key='pwrt:inspector:value-requires-reviewing']")
        is not None
    ):
        return False

    deps = root.find("./properties[@key='pwrt:inspector:value-deps']")
    value_ref = root.find("./properties[@key='pwrt:inspector:value-ref']")
    if deps is None and value_ref is None:
        logger.info(
            f'{" "*log_indentation}  No top-level properties tag with key="pwrt:inspector:value-deps" or "pwrt:inspector:value-ref". Skipping this file'
        )
        return False

    if deps is not None:
        deps_arr: typing.List[str] = deps.get("value").split(";")
        deps_hashes = root.find("./properties[@key='pwrt:inspector:value-deps-hashes']")
        deps_hashes_arr: typing.List[str] = (
            deps_hashes.get("value").split(";") if deps_hashes is not None else None
        )

        deps_mismatches: typing.List[str] = []
        new_deps_hashes: typing.List[str] = []
        new_deps_arr: typing.List[str] = []
        use_deps_hashes = False
        for i, deps_url in enumerate(deps_arr):
            logger.debug(
                f'{" "*log_indentation}  Processing value dependency: {deps_url}'
            )
            url = urllib.parse.urlparse(deps_url)
            url_resolver: plugin_registry.IUrlResolver = plugin_registry.getUrlResolver(
                plugins, url.scheme
            )

            if url_resolver.isVersioningSupported and re.match(
                r".+@[0-9a-fA-F]+", url.path
            ):
                new_deps_hashes.append("")
                diff: plugin_registry.contract.IDiff = url_resolver.diff(deps_url)
                logger.debug(f'{" "*log_indentation}    Diff: {diff}')
                if diff == False:
                    new_deps_arr.append(deps_url)
                else:
                    new_deps_arr.append(diff.updated_url)
                    changed_detected = True
                    deps_mismatches.append(deps_url)
                    if type(diff) == plugin_registry.contract.IDiffContentChanged:
                        requires_reviewing = True
            else:
                hash_known = (
                    deps_hashes_arr[i]
                    if deps_hashes_arr and i < len(deps_hashes_arr)
                    else "~none~"
                )
                content_obj: plugin_registry.contract.IContent = (
                    url_resolver.resolveToContent(deps_url)
                )
                if content_obj is None:
                    hash_calculated = "~none~"
                else:
                    content = content_obj.content
                    logger.debug(
                        f'{" "*log_indentation}    Resolved content: {content}'
                    )
                    hash_calculated = hashlib.shake_128(content).hexdigest(4)
                    logger.debug(
                        f'{" "*log_indentation}    Hash of resolved content: {hash_calculated}. Hash known in pwrt:inspector:value-deps-hashes: {hash_known}{". Mismatch!" if hash_calculated != hash_known else ""}'
                    )
                if hash_calculated != hash_known:
                    deps_mismatches.append(deps_url)
                    requires_reviewing = True
                if isinstance(content_obj, plugin_registry.contract.IVersionedContent):
                    new_deps_arr.append(
                        url._replace(
                            path=url.path + "@" + content_obj.last_commit_id
                        ).geturl()
                    )
                    new_deps_hashes.append("")
                else:
                    new_deps_arr.append(deps_url)
                    use_deps_hashes = True
                    new_deps_hashes.append(hash_calculated)

        if len(deps_mismatches) == 0:
            logger.debug(f'{" "*log_indentation}  No changes detected.')
        else:
            logger.debug(
                f'{" "*log_indentation}  Changes detected in: {deps_mismatches}'
            )
            changed_detected = True
            upsertProperty(
                root,
                "pwrt:inspector:value-deps",
                ";".join(new_deps_arr),
            )
            if use_deps_hashes:
                upsertProperty(
                    root,
                    "pwrt:inspector:value-deps-hashes",
                    ";".join(new_deps_hashes),
                )

    if value_ref is not None:
        value_ref_url: str = value_ref.get("value")
        logger.debug(f'{" "*log_indentation}  Processing value ref: {value_ref_url}')
        url = urllib.parse.urlparse(value_ref_url)
        url_resolver: plugin_registry.IUrlResolver = plugin_registry.getUrlResolver(
            plugins, url.scheme
        )

        value_regexp = root.find("./properties[@key='pwrt:inspector:value-regexp']")
        value_regexp_str: str = value_regexp.get("value")
        logger.debug(
            f'{" "*log_indentation}    Ref regexp (in quotes "): "{value_regexp_str}"'
        )

        value_known = root.find("./properties[@key='pwrt:inspector:value']")
        if value_known is not None:
            value_known_str = value_known.get("value")
            # FIXME:
            # logger.debug(
            #     f'{" "*log_indentation}    Current value: {value_new_str}. Value known in pwrt:inspector:value: {value_known_str}{". Mismatch!" if value_new_str != value_known_str else ""}'
            # )
        else:
            value_known_str = "~none~"

        if url_resolver.isVersioningSupported and re.match(
            r".+@[0-9a-fA-F]+", url.path
        ):
            diff: plugin_registry.contract.IDiff = url_resolver.diff(value_ref_url)
            logger.debug(f'{" "*log_indentation}    Diff: {diff}')
            value_new_str: str = "~none~"
            if diff != False:
                changed_detected = True
                upsertProperty(root, "pwrt:inspector:value-ref", diff.updated_url)
                if diff.current_lines_content is None:
                    url_without_sha1 = re.sub(
                        r"@[a-fA-F0-9]+(#L.*)?$",
                        r"\1",
                        diff.updated_url,
                    )
                    current_lines_content = url_resolver.resolveToContent(
                        url_without_sha1
                    ).content.decode("utf-8")
                else:
                    current_lines_content = diff.current_lines_content
                search_res = re.search(value_regexp_str, current_lines_content)
                if search_res:
                    value_new_str = search_res.groups()[0]
            else:
                if value_known is None:
                    content_obj = url_resolver.resolveToContent(value_ref_url)
                    value_str = content_obj.content
                    if value_str:
                        changed_detected = True
                        logger.debug(
                            f'{" "*log_indentation}    Ref resolved to content: {value_str}'
                        )
                        search_res = re.search(
                            value_regexp_str, value_str.decode("utf-8")
                        )
                        if search_res:
                            value_new_str = search_res.groups()[0]
                    upsertProperty(
                        root,
                        "pwrt:inspector:value-ref",
                        url._replace(
                            path=re.sub(
                                r"@[a-fA-F0-9]+$",
                                "@" + content_obj.last_commit_id,
                                url.path,
                            )
                        ).geturl(),
                    )
                else:
                    value_new_str = value_known_str
            if value_known is None or value_new_str != value_known_str:
                changed_detected = True
                requires_reviewing = True
                upsertProperty(root, "pwrt:inspector:value-new", value_new_str)
        else:
            value_new_str = "~none~"
            content_obj = url_resolver.resolveToContent(value_ref_url)
            value_str: str = content_obj.content
            if value_str:
                logger.debug(
                    f'{" "*log_indentation}    Ref resolved to content: {value_str}'
                )
                search_res = re.search(value_regexp_str, value_str.decode("utf-8"))
                if search_res:
                    value_new_str = search_res.groups()[0]
                if type(content_obj) == plugin_registry.contract.IVersionedContent:
                    changed_detected = True
                    requires_reviewing = True
                    upsertProperty(
                        root,
                        "pwrt:inspector:value-ref",
                        url._replace(
                            path=url.path + "@" + content_obj.last_commit_id
                        ).geturl(),
                    )

            if value_new_str != value_known_str:
                changed_detected = True
                requires_reviewing = True
                upsertProperty(root, "pwrt:inspector:value-new", value_new_str)

    if changed_detected:
        logger.info(
            f'{" "*log_indentation}  Changes detected. Generating output to {out_file_name}'
        )
        if requires_reviewing:
            logger.debug(
                f'{" "*log_indentation}  Setting "pwrt:inspector:value-requires-reviewing"="true"'
            )
            upsertProperty(root, "pwrt:inspector:value-requires-reviewing", "true")

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
