from typing import Any
import app
import plugin_registry
import xml.etree.ElementTree as ET
import git
import logging
import pytest
import unittest
from unittest import mock
import lib


class TestWriteXmlTreeInArchiFormat:
    def test(self):
        test_xml_str = """
            <?xml version="1.0"?>
            <data/>
        """
        mock_file = mock.Mock()
        app.writeXmlTreeInArchiFormat(ET.fromstring(test_xml_str.strip()), mock_file)
        mock_file.write.assert_called()
        assert lib.reconstructOutput(mock_file) == "<data/>\n"

    def test_archimate_flowrelationship(self):
        test_xml_str = """
            <archimate:FlowRelationship
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xmlns:archimate="http://www.archimatetool.com/archimate"
                id="id-a1b2c3d4">
            <properties
                key="pwrt:inspector:value"
                value="somevalue"/>
            </archimate:FlowRelationship>
        """
        mock_file = mock.Mock()
        app.writeXmlTreeInArchiFormat(ET.fromstring(test_xml_str.strip()), mock_file)
        mock_file.write.assert_called()
        assert (
            lib.reconstructOutput(mock_file)
            == """<archimate:FlowRelationship
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:archimate="http://www.archimatetool.com/archimate"
    id="id-a1b2c3d4">
  <properties
      key="pwrt:inspector:value"
      value="somevalue"/>
</archimate:FlowRelationship>
"""
        )

    def test_quotes(self):
        tree = ET.fromstring("<root><properties/></root>")
        tree.find(f"./properties").set("value", 'here is " quote')

        mock_file = mock.Mock()
        app.writeXmlTreeInArchiFormat(tree, mock_file)
        assert (
            lib.reconstructOutput(mock_file)
            == """<root>
  <properties
      value="here is &quot; quote"/>
</root>
"""
        )


class TestUpsertProperty:
    def test_update(self):
        tree = ET.fromstring(
            '<root><properties key="somekey" value="somevalue"/></root>'
        )
        app.upsertProperty(tree, "somekey", "newvalue")
        assert (
            ET.tostring(tree)
            == b'<root><properties key="somekey" value="newvalue" /></root>'
        )

    def test_insert(self):
        tree = ET.fromstring(
            '<root><properties key="otherkey" value="somevalue"/></root>'
        )
        app.upsertProperty(tree, "somekey", "newvalue")
        assert (
            ET.tostring(tree)
            == b'<root><properties key="otherkey" value="somevalue" /><properties key="somekey" value="newvalue" /></root>'
        )


def test_redact_url():
    assert (
        app.redact_url("https://user:password@host.com/path")
        == "https://user:REDACTED@host.com/path"
    )


@mock.patch("app.logger", logging.getLogger("test"))
class TestProcessFile:
    def test_minimalistic(self):
        file_content = "<root/>"
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            changes_detected = app.processFile("somefile.xml")
            assert not changes_detected
            mock_file.assert_called_with("somefile.xml", "rb")
            mock_file.return_value.close.assert_called_with()

    def test_deps(self):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                b"fakecontent"
            )
            with mock.patch("app.plugins", [mock_plugin]):
                changes_detected = app.processFile("somefile.xml")
                assert changes_detected
                mock_file.assert_called_with("somefile.xml", "w")
                mock_file.return_value.close.assert_called_with()
                mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                    "someproto://some.host/some/path/file.ext#L1"
                )

    def test_deps_no_content(self):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = None
            with mock.patch("app.plugins", [mock_plugin]):
                changes_detected = app.processFile("somefile.xml")
                assert not changes_detected
                mock_file.assert_called_with("somefile.xml", "rb")
                mock_file.return_value.close.assert_called_with()
                mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                    "someproto://some.host/some/path/file.ext#L1"
                )

    def test_deps_no_plugin(self):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="wrongproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value = None
            with mock.patch("app.plugins", [mock_plugin]):
                with pytest.raises(AttributeError):
                    app.processFile("somefile.xml")

    def test_value_ref(self):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                b"fakecontent"
            )
            with mock.patch("app.plugins", [mock_plugin]):
                changes_detected = app.processFile("somefile.xml")
                assert changes_detected
                mock_file.assert_called_with("somefile.xml", "w")
                mock_file.return_value.close.assert_called_with()
                mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                    "someproto://some.host/some/path/file.ext#L1"
                )

    def test_value_ref_no_regexp(self):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                b"fakecontent"
            )
            with mock.patch("app.plugins", [mock_plugin]):
                with pytest.raises(AttributeError):
                    app.processFile("somefile.xml")

    def test_value_ref_known_value(self):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                b"fakecontent"
            )
            with mock.patch("app.plugins", [mock_plugin]):
                changes_detected = app.processFile("somefile.xml")
                assert changes_detected
                mock_file.assert_called_with("somefile.xml", "w")
                mock_file.return_value.close.assert_called_with()
                mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                    "someproto://some.host/some/path/file.ext#L1"
                )


def test_main_no_args():
    with pytest.raises(SystemExit):
        app.main()


@mock.patch(
    "sys.argv",
    ["program_name", "fake-coarchi-repo-url", "/fake/path/to/local/clone/dir"],
)
@mock.patch("git.Repo")
@mock.patch("pathlib.Path")
@mock.patch("os.path.exists")
class TestMain(unittest.TestCase):
    def test_main_local_clone_does_not_exist(
        self, os_path_exists, pathlib_path, git_repo
    ):
        os_path_exists.return_value = False

        app.main()

        os_path_exists.assert_called_with("/fake/path/to/local/clone/dir")
        git_repo.clone_from.assert_called_once_with(
            "fake-coarchi-repo-url", "/fake/path/to/local/clone/dir"
        )
        pathlib_path.assert_called_with("/fake/path/to/local/clone/dir")

    @mock.patch("os.path.isdir")
    @mock.patch("git.remote.Remote")
    def test_main_local_clone_exists(
        self, git_remote_remote, os_path_isdir, os_path_exists, pathlib_path, git_repo
    ):
        os_path_exists.return_value = True

        os_path_isdir.return_value = False
        with self.assertRaises(Exception):
            app.main()
        os_path_exists.assert_called_with("/fake/path/to/local/clone/dir")
        os_path_isdir.assert_called_with("/fake/path/to/local/clone/dir")
        git_repo.clone_from.assert_not_called()

        os_path_isdir.return_value = True
        app.main()
        os_path_exists.assert_called_with("/fake/path/to/local/clone/dir")
        os_path_isdir.assert_called_with("/fake/path/to/local/clone/dir")
        git_repo.clone_from.assert_not_called()
        git_remote_remote.assert_called()
        git_remote_remote.return_value.pull.assert_called_with()

    @mock.patch("app.processFile")
    def test_main_some_files_found(
        self, processFile, os_path_exists, pathlib_path, git_repo
    ):
        os_path_exists.return_value = False
        pathlib_path.return_value.glob.return_value = ["fakefile.txt"]
        processFile.return_value = False  # No changes detected

        app.main()

        processFile.assert_called_with("fakefile.txt")

    @mock.patch("app.processFile")
    def test_main_change_detected(
        self, processFile, os_path_exists, pathlib_path, git_repo
    ):
        os_path_exists.return_value = False
        pathlib_path.return_value.glob.return_value = ["fakefile.txt"]
        processFile.return_value = True  # Changes detected

        app.main()

        processFile.assert_called_with("fakefile.txt")
        git_repo.clone_from.return_value.index.diff.assert_called_with(None)
        git_repo.clone_from.return_value.index.add.assert_called()
        git_repo.clone_from.return_value.index.commit.assert_called_with(
            "Report detected changes",
            author=git.Actor("Archi Power Tools Inspector", "some@email.com"),
        )
        git_repo.clone_from.return_value.remotes.origin.push.assert_called_with()
