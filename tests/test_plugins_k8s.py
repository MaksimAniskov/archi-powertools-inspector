import plugin_registry
import logging
import unittest
from unittest import mock
import pytest

import kubernetes

builtin_open = open


def my_open(*args, **kwargs):
    fake_kube_config = """
apiVersion: v1
kind: Config
contexts:
- name:  fake_context_1
  context:
    cluster:  cluster_1
- name:  fake_context_2
  context:
    cluster:  cluster_2

clusters:
- name: cluster_1
  cluster:
    server: https://abc123.xyz.eu-west-1.eks.amazonaws.com
- name: cluster_2
  cluster:
    server: https://zyx098.cba.us-east-100.eks.amazonaws.com
"""

    filename = args[0]
    if filename == "k8s_plugin_whitelisted_kubectl_contexts.txt":
        content = "fake_context_1\nfake_context_2\nnonexisting_context"
    elif filename.endswith("/.kube/config"):
        content = fake_kube_config
    else:
        return builtin_open(*args, **kwargs)

    file_object = mock.mock_open(read_data=content).return_value
    file_object.__iter__.return_value = content.splitlines(True)
    return file_object


@pytest.fixture(scope="session")
def plugins():
    logger = logging.getLogger("tests")

    with mock.patch(
        "builtins.open",
        new=my_open,
    ):
        plugins = plugin_registry.Registry(
            plugin_directory="plugins", logger=logger
        ).loadPlugins()
        return [P(logger) for P in plugins]


@pytest.fixture
def url_resolver(plugins):
    res = plugin_registry.getUrlResolver(plugins=plugins, scheme="k8s+jmespath")
    res._k8s_results_cache = {}  # Clear the resolver's cache.
    return res


@pytest.fixture
def kubernetes_resource_get_result_ingress():
    return {
        "ingressClassName": "my-nginx-ingress-class",
        "rules": [
            {
                "host": "service1.acme.com",
                "http": {
                    "paths": [
                        {
                            "backend": {
                                "service": {
                                    "name": "my-service-1",
                                    "port": {"number": 8080},
                                }
                            },
                            "path": "/some-path(/|$)(.*)",
                            "pathType": "Prefix",
                        }
                    ]
                },
            }
        ],
    }

@pytest.fixture
def kubernetes_resource_get_result_configmap():
    return {
        "data": {
            "somekey": "somevalue",
        }
    }

@mock.patch("kubernetes.dynamic.DynamicClient")
@mock.patch("builtins.open", new=my_open)
class TestK8sPlugin:
    def test_resolveToContent(
        self, k8s_client, url_resolver, kubernetes_resource_get_result_ingress
    ):
        k8s_client.return_value.resources.get.return_value.get.return_value = (
            kubernetes_resource_get_result_ingress
        )

        content_obj = url_resolver.resolveToContent(
            "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#rules[0].host"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"service1.acme.com"

    def test_resolveToContentCoreApiGroup(
        self, k8s_client, url_resolver, kubernetes_resource_get_result_configmap
    ):
        k8s_client.return_value.resources.get.return_value.get.return_value = (
            kubernetes_resource_get_result_configmap
        )

        content_obj = url_resolver.resolveToContent(
            "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace//v1/ConfigMap/some-name#data.somekey"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"somevalue"

    def test_resolveToContent_advanced_jmethpath_expression(
        self, k8s_client, url_resolver, kubernetes_resource_get_result_ingress
    ):
        k8s_client.return_value.resources.get.return_value.get.return_value = (
            kubernetes_resource_get_result_ingress
        )

        content_obj = url_resolver.resolveToContent(
            "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#rules[0].join('',[host,http.paths[0].path])"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"service1.acme.com/some-path(/|$)(.*)"

    def test_caching(
        self, k8s_client, url_resolver, kubernetes_resource_get_result_ingress
    ):
        k8s_client.return_value.resources.get.return_value.get.return_value = (
            kubernetes_resource_get_result_ingress
        )

        content_obj = url_resolver.resolveToContent(
            "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#rules[0].host"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"service1.acme.com"

        content_obj = url_resolver.resolveToContent(
            "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#ingressClassName"
        )
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"my-nginx-ingress-class"

        k8s_client.return_value.resources.get.return_value.get.assert_called_once()

    def test_resolveToContent_404(
        self, k8s_client, url_resolver
    ):
        k8s_client.return_value.resources.get.return_value.get.side_effect = (
            kubernetes.client.exceptions.ApiException(http_resp=mock.Mock(status=404))
        )

        content_obj = url_resolver.resolveToContent(
            "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#rules[0].host"
        )
        assert content_obj == None

    def test_resolveToContent_503(
        self, k8s_client, url_resolver
    ):
        k8s_client.return_value.resources.get.return_value.get.side_effect = (
            kubernetes.client.exceptions.ApiException(http_resp=mock.Mock(status=503))
        )

        try:
            url_resolver.resolveToContent(
                "k8s+jmespath://https://abc123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#rules[0].host"
            )
            assert(False) # pragma: no cover
        except:
            pass