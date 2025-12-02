import logging
import plugin_registry
import boto3
from botocore.config import Config
import json
import jmespath
import urllib.parse
import yaml
import re

MY_SCHEMES = ["boto3", "boto3+json+jmespath"]

# Examples:
# boto3://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:012345678901:secret:mysecretname-aBcDeF&VersionId=abcd#SecretString
# boto3://secretsmanager@us-east-1/get_secret_value ...
# boto3+json+jmespath://secretsmanager/get_secret_value?SecretId=arn:aws:secretsmanager:eu-west-1:012345678901:secret:mysecretname-aBcDeF&VersionId=abcd#SecretString/key1
# boto3://elbv2/describe_tags?ResourceArns=[arn:aws:elasticloadbalancing:eu-west-1:012345678901:loadbalancer/net/a1b2c3d4e5f6]#TagDescriptions


class Boto3(plugin_registry.contract.IPlugin):
    _url_resolver: plugin_registry.IUrlResolver

    def __init__(self, logger: logging.Logger) -> None:
        super().__init__(logger)
        with open("boto3_plugin_whitelisted_services_and_methods.yaml") as stream:
            self._url_resolver = UrlResolver(logger, yaml.safe_load(stream))
        logger.info(__class__.__name__ + " plugin loaded")

    def getUrlResolver(self, scheme: str) -> plugin_registry.IUrlResolver:
        return self._url_resolver if scheme in MY_SCHEMES else None


class UrlResolver(plugin_registry.IUrlResolver):
    def __init__(
        self, logger: logging.Logger, whitelisted_services_and_methods
    ) -> None:
        super().__init__(logger)
        self._whitelisted_services_and_methods = whitelisted_services_and_methods
        self._boto_results_cache = {}

    def resolveToContent(
        self, url: str
    ) -> plugin_registry.contract.IVersionedContent | None:

        url_parsed = urllib.parse.urlparse(url)

        is_jmespath_mode = url_parsed.scheme == "boto3+json+jmespath"
        match = re.match(
            r"(?P<service_name>[^@]+)(@(?P<region>.+))?", url_parsed.netloc)
        aws_service_name = match.group("service_name")  # E.g. secretsmanager
        aws_region = match.group("region")  # E.g. us-east-1
        method_name = url_parsed.path[1:]  # E.g. /get_secret_value
        method_params = url_parsed.query
        # E.g. SecretId=arn:aws:secretsmanager:eu-west-1:012345678901:secret:mysecretname-aBcDeF&VersionId=abcd'

        if is_jmespath_mode:
            match = re.match(
                r"(?P<value_to_return>.+)/(?P<jmethpath_expression>.+)", url_parsed.fragment)
            value_to_return = match.group(
                "value_to_return")  # E.g. SecretString
            jmethpath_expression = match.group(
                "jmethpath_expression")  # E.g. key1
        else:
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

            cache_key = f"{aws_service_name}@{aws_region}/{method_name}?{method_params}"

            if cache_key not in self._boto_results_cache:
                config = Config(
                    region_name=aws_region) if aws_region else None
                client = boto3.client(aws_service_name, config=config)
                method = getattr(client, method_name)

                params = {}
                for equation in method_params.split("&"):
                    match = re.match(
                        r"(?P<name>[^=]+)=(?P<value>.+)",
                        equation,
                    )
                    param_name = match.group("name")
                    param_value = match.group("value")
                    if not re.match(r"^\[.+\]$", param_value):
                        params[param_name] = param_value
                    else:
                        params[param_name] = param_value[1:-1].split(",")

                response = method(**params)
                self._boto_results_cache[cache_key] = response

            response = self._boto_results_cache[cache_key]

            if value_to_return == "":
                result = str(response)
            else:
                result = str(response[value_to_return])
            if is_jmespath_mode:
                json_doc = json.loads(result)
                result = str(jmespath.search(jmethpath_expression, json_doc))
            return plugin_registry.contract.IContent(content=result.encode())

        except Exception as e:
            self._logger.warning(f"{e}: {url}")
            return None
