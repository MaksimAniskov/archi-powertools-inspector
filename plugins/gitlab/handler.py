import logging
import plugin_registry
import os
import gitlab
import urllib.parse
import re

MY_SCHEME_NAME = "gitlab"


class GitLab(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        self._url_resolver = UrlResolver(logger)
        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme == MY_SCHEME_NAME else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        self._gls = {}

    def resolveToContent(self, url: str) -> str | None:
        url_parsed = urllib.parse.urlparse(url)
        if url_parsed.hostname in self._gls:
            gl = self._gls[url_parsed.hostname]
        else:
            gl = gitlab.Gitlab(
                f"https://{url_parsed.hostname}",
                os.getenv("GITLAB_TOKEN"),  # TODO: Provide token as plugin config
            )
            if self._logger.isEnabledFor(logging.DEBUG):
                gl.enable_debug()  # TODO: Token leaks to output
            self._gls[url_parsed.hostname] = gl

        match = re.match(
            r"/(?P<project_id>.+)/-/blob/(?P<ref>[^/]+)/(?P<file_path>.+)",
            url_parsed.path,
        )
        project = gl.projects.get(match.group("project_id"))
        try:
            return project.files.get(
                file_path=match.group("file_path"), ref=match.group("ref")
            ).decode()
        except gitlab.GitlabGetError as e:
            self._logger.warning(f"{e.error_message}: {url}")
            return None
