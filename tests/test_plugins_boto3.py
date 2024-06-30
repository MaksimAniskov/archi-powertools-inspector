import plugin_registry
import logging
from unittest import mock
import pytest


@pytest.fixture(scope="session")
def plugins():
    logger = logging.getLogger("tests")

    boto3_plugin_whitelisted_services_and_methods = """
secretsmanager:
  - get_secret_value
"""
    with mock.patch(
        "builtins.open",
        mock.mock_open(read_data=boto3_plugin_whitelisted_services_and_methods),
    ):
        plugins = plugin_registry.Registry(
            plugin_directory="plugins", logger=logger
        ).loadPlugins()
        return [P(logger) for P in plugins]


@pytest.fixture
def url_resolver(plugins):
    return plugin_registry.getUrlResolver(plugins=plugins, scheme="boto3")

@mock.patch("boto3.client")
class TestBoto3Plugin:
    def test_resolveToContent(self, boto3client, url_resolver):
        boto3client.return_value.get_secret_value.return_value = {
            "SecretString": '{"key1":"value1"}'
        }
        content_obj = url_resolver.resolveToContent(
            "boto3://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:425828444339:secret:my/secret-W0Wo0L#SecretString"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b'{"key1":"value1"}'

    def test_resolveToContentNoHash(self, boto3client, url_resolver):
        boto3client.return_value.get_secret_value.return_value = {
            "SecretString": '{"key1":"value1"}'
        }
        content_obj = url_resolver.resolveToContent(
            "boto3://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:425828444339:secret:my/secret-W0Wo0L"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"""{'SecretString': '{"key1":"value1"}'}"""

    def test_resolveToContentNotWhitelistedMethod(self, boto3client, url_resolver):
        content_obj = url_resolver.resolveToContent(
            "boto3://secretsmanager/some_method"
        )
        assert content_obj is None

    def test_resolveToContentNotWhitelistedService(self, boto3client, url_resolver):
        content_obj = url_resolver.resolveToContent(
            "boto3://someservice/some_method"
        )
        assert content_obj is None
