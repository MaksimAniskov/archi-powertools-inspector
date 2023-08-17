import logging
import plugin_registry
import pytest


@pytest.fixture(scope="session")
def plugins():
    logger = logging.getLogger("tests")
    plugins = plugin_registry.Registry(
        plugin_directory="plugins", logger=logger
    ).loadPlugins()
    return [P(logger) for P in plugins]


def test_plugins_loaded(plugins):
    assert len(plugins) > 0


def test_getUrlResolver_file(plugins):
    assert plugin_registry.getUrlResolver(plugins=plugins, scheme="file") != None


def test_getUrlResolver_gitlab(plugins):
    assert plugin_registry.getUrlResolver(plugins=plugins, scheme="gitlab") != None
