import plugin_registry
import logging
import requests
from unittest import mock
import pytest


@pytest.fixture(scope="session")
def plugins():
    logger = logging.getLogger("tests")

    https_plugin_headers = """
Authorization: "Bearer glpat-test_token"
"""
    with mock.patch(
        "builtins.open",
        mock.mock_open(read_data=https_plugin_headers),
    ):
        plugins = plugin_registry.Registry(
            plugin_directory="plugins", logger=logger
        ).loadPlugins()
        return [P(logger) for P in plugins]


@pytest.fixture
def url_resolver(plugins):
    res = plugin_registry.getUrlResolver(plugins=plugins, scheme="https")
    res._cache = (
        {}
    )  # Clear the resolver's cache of repository_compare return objects.
    return res


@mock.patch("requests.get")
class TestHttpsPlugin:
    def test_resolveToContent(self, get, url_resolver):
        test_content = '{"variable_type":"env_var","key":"TEST1","value":"test1 value","hidden":false,"protected":false,"masked":false,"raw":true,"environment_scope":"*","description":null}'
        get.return_value.status_code = 200
        get.return_value.text = test_content

        content_obj = url_resolver.resolveToContent(
            "https://gitlab.mycompany.com/api/v4/projects/12345/variables/TEST1"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == test_content

    def test_errorStatusCode(self, get, url_resolver):
        get.return_value.status_code = 401

        content_obj = url_resolver.resolveToContent(
            "https://gitlab.mycompany.com/api/v4/projects/12345/variables/TEST1"
        )
        assert content_obj == None

    def test_caching(self, get, plugins):
        url_resolver = plugin_registry.getUrlResolver(plugins=plugins, scheme="https")
        url_resolver._cache = {}  # Clear the resolver's cache.

        get.return_value.status_code = 200
        get.return_value.text = ''

        test_url = "https://gitlab.mycompany.com/api/v4/projects/12345/variables/TEST1"
        url_resolver.resolveToContent(test_url)
        url_resolver.resolveToContent(test_url)

        get.assert_called_once()
