import logging
import plugin_registry
import urllib.parse
import re

MY_SCHEME_NAME = "file"


class File(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        self._url_resolver = UrlResolver(logger)
        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme == MY_SCHEME_NAME else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(self, logger: logging.Logger) -> str:
        super().__init__(logger)

    def resolveToContent(self, url: str) -> plugin_registry.contract.IContent | None:
        url = urllib.parse.urlparse(url)
        try:
            with open(url.path, "rb") as file:
                m = re.match(r"L(?P<from>\d+)(-(?P<to>\d+))?", url.fragment)

                from_line: int = int(m.group("from"))
                to_line: int = int(m.group("to")) if m.group("to") else None
                lines = file.readlines()[
                    from_line - 1 : to_line if to_line else from_line
                ]

                file.close()
                return plugin_registry.contract.IContent(content=b"".join(lines))
        except FileNotFoundError as e:
            self._logger.warning(f"{e.strerror}: {e.filename}")
            return None
