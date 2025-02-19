import logging
import plugin_registry
import kubernetes
import jmespath
import urllib.parse
import re

MY_SCHEME_NAME = "k8s+jmespath"

# Example:
# k8s+jmespath://https://ABC123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name#rules[0].host
# k8s+jmespath://https://ABC123.xyz.eu-west-1.eks.amazonaws.com/ns=some-namespace//v1/ConfigMap/some-name#data.somekey


class K8s(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        with open("k8s_plugin_whitelisted_kubectl_contexts.txt", "r") as file:
            self._url_resolver = UrlResolver(logger, file.readlines())
        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme == MY_SCHEME_NAME else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(self, logger: logging.Logger, whitelisted_kubectl_contexts) -> None:
        super().__init__(logger)
        self._k8s_results_cache = {}

        self._host_name_to_kubectl_context_name = {}
        for context_name in whitelisted_kubectl_contexts:
            context_name = context_name.strip()
            config = kubernetes.client.Configuration()
            try:
                kubernetes.config.load_kube_config(
                    context=context_name, client_configuration=config
                )
                self._host_name_to_kubectl_context_name[config.host] = context_name
            except kubernetes.config.ConfigException:
                pass

    def resolveToContent(
        self, url: str
    ) -> plugin_registry.contract.IVersionedContent | None:

        url_parsed = urllib.parse.urlparse(
            # Chop off protocol and "://" beginning the string
            url[len(MY_SCHEME_NAME) + 3 :]
        )

        host = url_parsed.scheme + "://" + url_parsed.hostname

        # '/ns=some-namespace/networking.k8s.io/v1/Ingress/some-name'
        match = re.match(
            r"/ns=(?P<namespace>[^/]+)/(?P<api_group>[^/]*)/(?P<api_version>[^/]+)/(?P<resource_kind>[^/]+)/(?P<resource_name>.+)",
            url_parsed.path,
        )
        namespace = match.group("namespace")
        api_group = match.group("api_group")
        api_version = match.group("api_version")
        resource_kind = match.group("resource_kind")
        resource_name = match.group("resource_name")

        jmethpath_expression = url_parsed.fragment

        cache_key = host + url_parsed.path

        try:
            if cache_key not in self._k8s_results_cache:
                config = kubernetes.client.Configuration()
                kubernetes.config.load_kube_config(
                    context=self._host_name_to_kubectl_context_name[host],
                    client_configuration=config,
                )

                client = kubernetes.dynamic.DynamicClient(
                    kubernetes.client.api_client.ApiClient(configuration=config)
                )

                api = client.resources.get(
                    group=api_group, api_version=api_version, kind=resource_kind
                )

                response = api.get(
                    body=None,
                    name=resource_name,
                    namespace=namespace,
                )

                self._k8s_results_cache[cache_key] = response

            response = self._k8s_results_cache[cache_key]

            result = str(jmespath.search(jmethpath_expression, response))

        except kubernetes.client.exceptions.ApiException as e:
            if e.status==404:
                return None
            else:
                raise e

        return plugin_registry.contract.IContent(content=result.encode())
