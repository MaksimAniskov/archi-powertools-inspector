import logging
import plugin_registry
import boto3
import urllib.parse
import yaml
import re

MY_SCHEME_NAME = "boto3"

# Example:
# boto3://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:012345678901:secret:mysecretname-aBcDeF&VersionId=abcd#SecretString


class Boto3(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        with open("boto3_plugin_whitelisted_services_and_methods.yaml") as stream:
            self._url_resolver = UrlResolver(logger, yaml.safe_load(stream))
        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme == MY_SCHEME_NAME else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(
        self, logger: logging.Logger, whitelisted_services_and_methods
    ) -> None:
        super().__init__(logger)
        self._whitelisted_services_and_methods = whitelisted_services_and_methods

    def resolveToContent(
        self, url: str
    ) -> plugin_registry.contract.IVersionedContent | None:

        url_parsed = urllib.parse.urlparse(url)

        aws_service_name = url_parsed.netloc  # E.g. secretsmanager
        method_name = url_parsed.path[1:]  # E.g. /get_secret_value
        method_params = url_parsed.query
        # E.g. SecretId=arn:aws:secretsmanager:eu-west-1:012345678901:secret:mysecretname-aBcDeF&VersionId=abcd'
        value_to_return = url_parsed.fragment  # E.g. SecretString

        try:
            if (aws_service_name in self._whitelisted_services_and_methods) and (
                method_name in self._whitelisted_services_and_methods[aws_service_name]
            ):
                pass
            else:
                raise Exception(
                    f"Boto3 service/method is not whitelisted: {aws_service_name}.{method_name}"
                )

            client = boto3.client(aws_service_name)
            method = getattr(client, method_name)

            params = {}
            for equation in method_params.split("&"):
                match = re.match(
                    r"(?P<name>[^=]+)=(?P<value>.+)",
                    equation,
                )
                params[match.group("name")] = match.group("value")

            response = method(**params)

            if value_to_return == "":
                result = str(response)
            else:
                result = str(response[value_to_return])
            return plugin_registry.contract.IContent(content=result.encode())

        except Exception as e:
            self._logger.warning(f"{e}: {url}")
            return None
