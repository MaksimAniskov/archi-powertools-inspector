import logging
import plugin_registry
import requests
import yaml

MY_SCHEME_NAME = "https"


class Https(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)

        with open("https_plugin_headers.yaml") as stream:
            self._url_resolver = UrlResolver(logger, yaml.safe_load(stream))

        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme == MY_SCHEME_NAME else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(self, logger: logging.Logger, headers) -> None:
        super().__init__(logger)
        self.isVersioningSupported = False
        self._headers = headers
        self._cache = {}

    def resolveToContent(self, url: str) -> plugin_registry.contract.IContent | None:

        cache_key = url

        if cache_key not in self._cache:
            r = requests.get(url, headers=self._headers)
            if r.status_code >= 300:
                self._logger.warning(f"{r.status_code} {r.reason}: {url}")
                self._cache[cache_key] = None
            else:
                self._cache[cache_key] = plugin_registry.contract.IContent(r.text.encode())

        return self._cache[cache_key]
