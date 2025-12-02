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
elbv2:
  - describe_tags
"""
    with mock.patch(
        "builtins.open",
        mock.mock_open(
            read_data=boto3_plugin_whitelisted_services_and_methods),
    ):
        plugins = plugin_registry.Registry(
            plugin_directory="plugins", logger=logger
        ).loadPlugins()
        return [P(logger) for P in plugins]


@pytest.fixture
def url_resolver(plugins):
    res = plugin_registry.getUrlResolver(plugins=plugins, scheme="boto3")
    res._boto_results_cache = {}  # Clear the resolver's cache.
    return res


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

    def test_resolveToContentWithRegion(self, boto3client, url_resolver):
        boto3client.return_value.get_secret_value.return_value = {
            "SecretString": '{"key1":"value1"}'
        }
        content_obj = url_resolver.resolveToContent(
            "boto3://secretsmanager@us-east-1/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:425828444339:secret:my/secret-W0Wo0L"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"""{'SecretString': '{"key1":"value1"}'}"""
        assert boto3client.call_args.kwargs["config"].region_name == "us-east-1"

    def test_resolveToContentNotWhitelistedMethod(self, boto3client, url_resolver):
        content_obj = url_resolver.resolveToContent(
            "boto3://secretsmanager/some_method"
        )
        assert content_obj is None

    def test_resolveToContentNotWhitelistedService(self, boto3client, url_resolver):
        content_obj = url_resolver.resolveToContent(
            "boto3://someservice/some_method")
        assert content_obj is None

    def test_caching(self, boto3client, plugins):
        url_resolver = plugin_registry.getUrlResolver(
            plugins=plugins, scheme="boto3")
        url_resolver._boto_results_cache = {}  # Clear the resolver's cache.

        boto3client.return_value.get_secret_value.return_value = {
            "SecretString": '{"key1":"value1"}'
        }
        content_obj1 = url_resolver.resolveToContent(
            "boto3://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:425828444339:secret:my/secret-W0Wo0L"
        )
        content_obj2 = url_resolver.resolveToContent(
            "boto3://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:425828444339:secret:my/secret-W0Wo0L#SecretString"
        )

        boto3client.assert_called_once()

    def test_jmespath_resolveToContent(self, boto3client, url_resolver):
        boto3client.return_value.get_secret_value.return_value = {
            "SecretString": '{"key1":"value1"}'
        }
        content_obj = url_resolver.resolveToContent(
            "boto3+json+jmespath://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:425828444339:secret:my/secret-W0Wo0L#SecretString/key1"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b'value1'

    def test_array_param_resolveToContent(self, boto3client, url_resolver):
        boto3client.return_value.describe_tags.return_value = {
            "TagDescriptions": [
                {
                    'ResourceArn': 'arn:aws:elasticloadbalancing:eu-west-1:012345678901:loadbalancer/net/a1b2c3d4e5f6',
                    'Tags': [
                        {
                            'Key': 'some_tag',
                            'Value': 'some_tag_value'
                        },
                    ]
                },
            ]
        }
        content_obj = url_resolver.resolveToContent(
            "boto3://elbv2/describe_tags?ResourceArns=[arn:aws:elasticloadbalancing:eu-west-1:012345678901:loadbalancer/net/a1b2c3d4e5f6]#TagDescriptions"
        )

        boto3client.return_value.describe_tags.assert_called_once_with(
            ResourceArns=[
                'arn:aws:elasticloadbalancing:eu-west-1:012345678901:loadbalancer/net/a1b2c3d4e5f6']
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"[{'ResourceArn': 'arn:aws:elasticloadbalancing:eu-west-1:012345678901:loadbalancer/net/a1b2c3d4e5f6', 'Tags': [{'Key': 'some_tag', 'Value': 'some_tag_value'}]}]"
