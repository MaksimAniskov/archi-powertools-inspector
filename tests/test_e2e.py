import lib
import plugin_registry
import logging
import pytest
from unittest import mock

@pytest.fixture(scope="session")
def plugins():
    logger = logging.getLogger("tests")

    with mock.patch(
        "builtins.open",
        mock.mock_open(read_data=""),
    ):
        plugins = plugin_registry.Registry(
            plugin_directory="plugins", logger=logger
        ).loadPlugins()
        return [P(logger) for P in plugins]

@mock.patch("requests.get")
class TestPlugins:
    def test_https_value_ref(self, get, plugins):

        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="https://some.host.com/api/v1/some/path"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        get.return_value.status_code = 200
        get.return_value.text = '{"some_attr":"some value"}'

        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            lib.processFile(logging.getLogger("test"), plugins, "somefile.xml")
