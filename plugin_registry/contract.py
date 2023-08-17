import logging
import typing


class IPluginRegistry(type):
    plugins: typing.List[type] = list()

    def __init__(cls, name, bases, attrs):
        super().__init__(cls)
        if name != "IPlugin":
            IPluginRegistry.plugins.append(cls)


class IUrlResolver:
    def resolveToContent(self, url: str) -> str | None:
        pass # pragma: no cover

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger


class IPlugin(object, metaclass=IPluginRegistry):
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def getUrlResolver(self, scheme: str) -> IUrlResolver:
        pass # pragma: no cover
