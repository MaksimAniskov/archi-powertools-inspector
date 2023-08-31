import plugin_registry
from test_plugin_registry import plugins
from unittest import mock
import pytest


@pytest.fixture
def url_resolver(plugins):
    return plugin_registry.getUrlResolver(plugins=plugins, scheme="file")


class TestFilePlugin:
    def test_resolveToContent(self, url_resolver):
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=b"line1\nline2\nline3")
        ) as mock_file:
            content_obj = url_resolver.resolveToContent("file:///some/path/file1.txt#L2")
        mock_file.assert_called_with("/some/path/file1.txt", "rb")
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"line2\n"  # TODO: Make the plugin trim line feeds

    def test_resolveToContent_Multiline(self, url_resolver):
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=b"line1\nline2\nline3\nline4")
        ) as mock_file:
            content_obj = url_resolver.resolveToContent("file:///some/path/file1.txt#L2-3")
        mock_file.assert_called_with("/some/path/file1.txt", "rb")
        assert type(content_obj) == plugin_registry.contract.IContent
        assert content_obj.content == b"line2\nline3\n"  # TODO: Make the plugin trim line feeds

    def test_resolveToContent_Exception(self, url_resolver):
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=b"line1")
        ) as mock_file:
            mock_file.side_effect = FileNotFoundError("Test")
            content = url_resolver.resolveToContent(
                "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
            )

        assert content == None
