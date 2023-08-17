import plugin_registry
import gitlab
import logging
from test_plugin_registry import plugins
import os
from unittest import mock
import pytest


@pytest.fixture
def url_resolver(plugins):
    res = plugin_registry.getUrlResolver(plugins=plugins, scheme="gitlab")
    res._gls = (
        {}
    )  # Clear the resolver's cache of GitLab objects. Otherwise subsequent tests will use the first test's GitLab mock object.
    return res


@mock.patch("gitlab.Gitlab")
@mock.patch.dict(os.environ, {"GITLAB_TOKEN": "gitlabfaketoken"}, clear=True)
class TestGitLabPlugin:
    def test_resolveToContent(self, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent\nline2\nline3"
        )

        content = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L2"
        )

        gl.assert_called_once_with("https://mygitlab.io", "gitlabfaketoken")
        gl.return_value.projects.get.return_value.files.get.assert_called_once_with(
            file_path="some/path/file1.txt", ref="main"
        )
        assert content == b"line2"

    def test_resolveToContent_Multiline(self, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent\nline2\nline3\nline4"
        )

        content = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L2-3"
        )

        gl.return_value.projects.get.return_value.files.get.assert_called_once_with(
            file_path="some/path/file1.txt", ref="main"
        )

        assert content == b"line2\nline3"

    def test_resolveToContent_Exception(self, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.side_effect = (
            gitlab.GitlabGetError("Test")
        )

        content = url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )
        assert content == None

    def test_resolveToContent_Cache(self, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent"
        )

        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )
        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )

        assert gl.call_count == 1  # Not 2

    def test_resolveToContent_EnableDebug(self, gl, url_resolver):
        gl.return_value.projects.get.return_value.files.get.return_value.decode.return_value = (
            b"fakefilecontent"
        )

        logging.getLogger("tests").setLevel("DEBUG")
        url_resolver.resolveToContent(
            "gitlab://mygitlab.io/user/project/-/blob/main/some/path/file1.txt#L1"
        )

        gl.return_value.enable_debug.assert_called()
