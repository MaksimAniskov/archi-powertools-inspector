import logging
import typing
import importlib
import plugin_registry
import pkgutil


class Registry:
    def __init__(self, plugin_directory: str, logger: logging.Logger) -> None:
        self._plugin_directory: str = plugin_directory
        self._logger: logging.Logger = logger

    def loadPlugins(self) -> typing.List[plugin_registry.IPlugin]:
        self._logger.debug(
            f"Searching for plugins under package {self._plugin_directory}"
        )

        for _, plugin_name, ispkg in pkgutil.iter_modules(
            path=[self._plugin_directory]
        ):
            importlib.import_module(self._plugin_directory + "." + plugin_name)

        return plugin_registry.IPluginRegistry.plugins

    def setupPlugins(self) -> None: # pragma: no cover
        self._logger.debug(
            f"Searching for plugins under package {self._plugin_directory}"
        )

        for _, plugin_name, ispkg in pkgutil.iter_modules(
            path=[self._plugin_directory]
        ):
            importlib.import_module(
                self._plugin_directory + "." + plugin_name + ".setup"
            )


def getUrlResolver(
    plugins: typing.List[plugin_registry.IPlugin], scheme: str
) -> plugin_registry.IUrlResolver:
    for p in plugins:
        urlResolver: plugin_registry.IUrlResolver = p.getUrlResolver(scheme)
        if urlResolver:
            return urlResolver
