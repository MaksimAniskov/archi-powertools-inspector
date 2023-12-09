import logging
import typing


class IPluginRegistry(type):
    plugins: typing.List[type] = list()

    def __init__(cls, name, bases, attrs):
        super().__init__(cls)
        if name != "IPlugin":
            IPluginRegistry.plugins.append(cls)


class IDiff:
    def __init__(self, updated_url: str):
        self.updated_url = updated_url


class IDiffLinesMoved(IDiff):
    def __init__(self, updated_url: str, current_lines_content: str):
        super().__init__(updated_url=updated_url)
        self.current_lines_content = current_lines_content


class IDiffContentChanged(IDiffLinesMoved):
    def __init__(
        self, updated_url: str, current_lines_content: str, was_lines_content: str
    ):
        super().__init__(
            updated_url=updated_url, current_lines_content=current_lines_content
        )
        self.was_lines_content = was_lines_content


class IContent:
    def __init__(self, content: str):
        self.content = content


class IVersionedContent(IContent):
    def __init__(self, content: str, last_commit_id: str):
        super().__init__(content)
        self.last_commit_id = last_commit_id


class IUrlResolver:
    isVersioningSupported: bool = False

    def diff(self, url: str) -> IDiff | bool | None:
        pass  # pragma: no cover

    def resolveToContent(self, url: str) -> IContent | None:
        pass  # pragma: no cover

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger


class IPlugin(object, metaclass=IPluginRegistry):
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def getUrlResolver(self, scheme: str) -> IUrlResolver:
        pass  # pragma: no cover
