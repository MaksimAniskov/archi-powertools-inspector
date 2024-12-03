import app
import lib
import plugin_registry
import xml.etree.ElementTree as ET
import git
import logging
import pytest
import unittest
from unittest import mock
import tests.tests_lib as tests_lib


class TestWriteXmlTreeInArchiFormat:
    def test(self):
        test_xml_str = """
            <?xml version="1.0"?>
            <data/>
        """
        mock_file = mock.Mock()
        lib.writeXmlTreeInArchiFormat(ET.fromstring(test_xml_str.strip()), mock_file)
        mock_file.write.assert_called()
        assert tests_lib.reconstructOutput(mock_file) == "<data/>\n"

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
        lib.writeXmlTreeInArchiFormat(ET.fromstring(test_xml_str.strip()), mock_file)
        mock_file.write.assert_called()
        assert (
            tests_lib.reconstructOutput(mock_file)
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
        lib.writeXmlTreeInArchiFormat(tree, mock_file)
        assert (
            tests_lib.reconstructOutput(mock_file)
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
        lib.upsertProperty(tree, "somekey", "newvalue")
        assert (
            ET.tostring(tree)
            == b'<root><properties key="somekey" value="newvalue" /></root>'
        )

    def test_insert(self):
        tree = ET.fromstring(
            '<root><properties key="otherkey" value="somevalue"/></root>'
        )
        lib.upsertProperty(tree, "somekey", "newvalue")
        assert (
            ET.tostring(tree)
            == b'<root><properties key="otherkey" value="somevalue" /><properties key="somekey" value="newvalue" /></root>'
        )


def test_redact_url():
    assert (
        app.redact_url("https://user:password@host.com/path")
        == "https://user:REDACTED@host.com/path"
    )


@pytest.fixture
def logger():
    return logging.getLogger("test")


class TestProcessFileWithVersioning:
    def test_deps_LinesMoved(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    current_lines_content="fakecontent",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
</root>
"""
            )

    def test_deps_ContentChanged(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L2-4"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = plugin_registry.contract.IDiffContentChanged(
                updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L3-5",
                current_lines_content="line2 changed\nline3\nline4",
                was_lines_content="line2\nline3\nline4",
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L2-4"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L3-5"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_deps_no_diff_detected(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = False
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert not changes_detected
            mock_file.return_value.write.assert_not_called()
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )

    def test_deps_no_ref(self, logger):
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
                plugin_registry.contract.IVersionedContent(
                    content=b"fakecontent",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_deps_plugin_mix(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps"
                  value="proto1://some.host/file1.ext#L1;proto2://some.host/file2.ext@a1b2c3d4#L1;proto1://some.host/file3.ext#L2"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            url_resolver1 = mock.MagicMock()
            url_resolver1.isVersioningSupported = False
            mock_plugin1 = mock.MagicMock()
            mock_plugin1.getUrlResolver = mock.MagicMock(
                side_effect=(lambda proto: url_resolver1 if proto == "proto1" else None)
            )

            url_resolver2 = mock.MagicMock()
            mock_plugin2 = mock.MagicMock()
            mock_plugin2.getUrlResolver = mock.MagicMock(
                side_effect=(lambda proto: url_resolver2 if proto == "proto2" else None)
            )

            url_resolver1.resolveToContent.return_value = (
                plugin_registry.contract.IContent(content=b"fakecontent")
            )

            url_resolver2.diff.return_value = (
                plugin_registry.contract.IDiffContentChanged(
                    updated_url="proto2://some.host/file2.ext@a1b2c3d5#L2",
                    current_lines_content="line1 changed",
                    was_lines_content="line1",
                )
            )

            changes_detected = lib.processFile(
                logger, [mock_plugin1, mock_plugin2], "somefile.xml"
            )
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            url_resolver1.resolveToContent.assert_has_calls(
                [
                    unittest.mock.call("proto1://some.host/file1.ext#L1"),
                    unittest.mock.call("proto1://some.host/file3.ext#L2"),
                ],
                any_order=True,
            )
            url_resolver2.diff.assert_called_with(
                "proto2://some.host/file2.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="proto1://some.host/file1.ext#L1;proto2://some.host/file2.ext@a1b2c3d5#L2;proto1://some.host/file3.ext#L2"/>
  <properties
      key="pwrt:inspector:value-deps-hashes"
      value="d5683b61;;d5683b61"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_deps_multiple_only_1_changes(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps"
                  value="proto://some.host/file1.ext@a1b2c3d4#L1;proto://some.host/file2.ext@ffffffff#L999"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            # mock_plugin.getUrlResolver.return_value.diff.return_value = lambda url: (
            mock_plugin.getUrlResolver.return_value.diff = lambda url: (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="proto://some.host/file1.ext@a1b2c3d5#L2",
                    current_lines_content="fakecontent",
                )
                if url == "proto://some.host/file1.ext@a1b2c3d4#L1"
                else False
            )

            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="proto://some.host/file1.ext@a1b2c3d5#L2;proto://some.host/file2.ext@ffffffff#L999"/>
</root>
"""
            )

    def test_value_ref_LinesMoved(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    current_lines_content="knownvalue",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
</root>
"""
            )

    def test_value_ref_LinesMoved_no_content(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L3"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L4",
                    current_lines_content=None,
                )
            )
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=b"fakecontent",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L3"
            )

            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L4"
            )

            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="fakecontent"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L4"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_LinesMoved_no_known_value(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    current_lines_content="fakecontent",
                )
            )
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=b"newvalue",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="fakecontent"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_LinesMoved_no_known_value_no_content(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    current_lines_content="",
                )
            )
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=None,
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value=""/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_LinesMoved_regexp_does_not_match(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="aaa(.+)bbb"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffLinesMoved(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    current_lines_content="fakecontent",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="~none~"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="aaa(.+)bbb"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_ContentChanged(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffContentChanged(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    was_lines_content="knownvalue",
                    current_lines_content="newvalue",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="newvalue"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_ContentChanged_no_known_value(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffContentChanged(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    was_lines_content="knownvalue",
                    current_lines_content="newvalue",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_not_called()
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="newvalue"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_ContentChanged_partial(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="123([a-z]+)456"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = (
                plugin_registry.contract.IDiffContentChanged(
                    updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2",
                    was_lines_content="123knownvalue456",
                    current_lines_content="xyz123newvalue456abc",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="newvalue"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="123([a-z]+)456"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_ContentChanged_lines_deleted(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = plugin_registry.contract.IDiffContentChanged(
                updated_url="someproto://some.host/some/path/file.ext@a1b2c3d5#L2<-lines deleted",
                was_lines_content="knownvalue",
                current_lines_content="",
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value=""/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a1b2c3d5#L2&lt;-lines deleted"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_ref(self, logger):
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
                plugin_registry.contract.IVersionedContent(
                    content=b"newvalue",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="newvalue"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_ref_no_known_value(self, logger):
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
                plugin_registry.contract.IVersionedContent(
                    content=b"newvalue",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="newvalue"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_diff_detected(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = False
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert not changes_detected
            mock_file.assert_called_with("somefile.xml", "rb")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )

    def test_value_ref_no_diff_detected_no_known_value(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = False
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=b"fakecontent",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="fakecontent"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_diff_detected_no_known_value_partial(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="123([a-z]+)456"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = False
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=b"123fakecontent456",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="fakecontent"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="123([a-z]+)456"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_diff_detected_no_known_value_no_content(self, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = False
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=None,
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="~none~"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_diff_detected_no_known_value_regexp_does_not_match(
        self, logger
    ):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="aaa(.+)bbb"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            mock_plugin.getUrlResolver.return_value.diff.return_value = False
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IVersionedContent(
                    content=b"fakecontent",
                    last_commit_id="a996319a",
                )
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.diff.assert_called_with(
                "someproto://some.host/some/path/file.ext@a1b2c3d4#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="~none~"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext@a996319a#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="aaa(.+)bbb"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_deps_non_reviewed(self, logger):
        # If value-requires-reviewing present, processFile is expected to exit without processing
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1&lt;-lines deleted"/>
                <properties key="pwrt:inspector:value-requires-reviewing" value="true"/>
            </root>
        """
        with mock.patch("builtins.open", mock.mock_open(read_data=file_content)):
            mock_plugin = mock.MagicMock()
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert not changes_detected
            mock_plugin.getUrlResolver.assert_not_called()

    def test_value_ref_non_reviewed(self, logger):
        # If value-requires-reviewing present, processFile is expected to exit without processing
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1&lt;-lines deleted"/>
                <properties key="pwrt:inspector:value-requires-reviewing" value="true"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin = mock.MagicMock()
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert not changes_detected
            mock_plugin.getUrlResolver.assert_not_called()


@pytest.fixture
def mock_plugin():
    mock_plugin = mock.MagicMock()
    mock_plugin.getUrlResolver.return_value.isVersioningSupported = False
    return mock_plugin


class TestProcessFile:
    def test_minimalistic(self, logger):
        file_content = "<root/>"
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            changes_detected = lib.processFile(logger, [], "somefile.xml")
            assert not changes_detected
            mock_file.assert_called_with("somefile.xml", "rb")
            mock_file.return_value.close.assert_called_with()

    def test_deps(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(b"fakecontent")
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
        assert (
            tests_lib.reconstructOutput(mock_file.return_value)
            == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="someproto://some.host/some/path/file.ext#L1"/>
  <properties
      key="pwrt:inspector:value-deps-hashes"
      value="d5683b61"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
        )

    def test_out_file(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(b"fakecontent")
            )
            changes_detected = lib.processFile(
                logger, [mock_plugin], "somefile.xml", "outfile.xml"
            )
            assert changes_detected
            mock_file.assert_called_with("outfile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
        assert (
            tests_lib.reconstructOutput(mock_file.return_value)
            == """<root>
  <properties
      key="pwrt:inspector:value-deps"
      value="someproto://some.host/some/path/file.ext#L1"/>
  <properties
      key="pwrt:inspector:value-deps-hashes"
      value="d5683b61"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
        )

    def test_deps_no_content(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            with mock.patch(
                "builtins.open", mock.mock_open(read_data=file_content)
            ) as mock_file:
                mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                    None
                )
                changes_detected = lib.processFile(
                    logger, [mock_plugin], "somefile.xml"
                )
                assert not changes_detected
                mock_file.assert_called_with("somefile.xml", "rb")
                mock_file.return_value.close.assert_called_with()
                mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                    "someproto://some.host/some/path/file.ext#L1"
                )

    def test_deps_no_plugin(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-deps" value="wrongproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value = None
            with pytest.raises(AttributeError):
                lib.processFile(logger, [mock_plugin], "somefile.xml")

    def test_value_ref(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(b"fakecontent")
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value-new"
      value="fakecontent"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_content(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(None)
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert not changes_detected

    def test_value_ref_no_content_does_not_match(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(None)
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="~none~"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_regexp_does_not_match(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value" value="knownvalue"/>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
                <properties key="pwrt:inspector:value-regexp" value="aaa(.+)bbb"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(b"thisshouldnotmatch")
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="~none~"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="aaa(.+)bbb"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
            )

    def test_value_ref_no_regexp(self, mock_plugin, logger):
        file_content = """
            <root>
                <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext#L1"/>
            </root>
        """
        with mock.patch(
            "builtins.open", mock.mock_open(read_data=file_content)
        ) as mock_file:
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                b"fakecontent"
            )
            with pytest.raises(AttributeError):
                lib.processFile(logger, [mock_plugin], "somefile.xml")

    def test_value_ref_known_value(self, mock_plugin, logger):
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
            mock_plugin.getUrlResolver.return_value.resolveToContent.return_value = (
                plugin_registry.contract.IContent(b"fakecontent")
            )
            changes_detected = lib.processFile(logger, [mock_plugin], "somefile.xml")
            assert changes_detected
            mock_file.assert_called_with("somefile.xml", "w")
            mock_file.return_value.close.assert_called_with()
            mock_plugin.getUrlResolver.return_value.resolveToContent.assert_called_with(
                "someproto://some.host/some/path/file.ext#L1"
            )
            assert (
                tests_lib.reconstructOutput(mock_file.return_value)
                == """<root>
  <properties
      key="pwrt:inspector:value"
      value="knownvalue"/>
  <properties
      key="pwrt:inspector:value-new"
      value="fakecontent"/>
  <properties
      key="pwrt:inspector:value-ref"
      value="someproto://some.host/some/path/file.ext#L1"/>
  <properties
      key="pwrt:inspector:value-regexp"
      value="(.*)"/>
  <properties
      key="pwrt:inspector:value-requires-reviewing"
      value="true"/>
</root>
"""
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

    @mock.patch("lib.processFile")
    def test_main_some_files_found(
        self, processFile, os_path_exists, pathlib_path, git_repo
    ):
        os_path_exists.return_value = False
        pathlib_path.return_value.glob.return_value = ["fakefile.txt"]
        processFile.return_value = False  # No changes detected

        app.main()

        processFile.assert_called_with(
            unittest.mock.ANY, unittest.mock.ANY, "fakefile.txt"
        )

    @mock.patch("lib.processFile")
    def test_main_change_detected(
        self, processFile, os_path_exists, pathlib_path, git_repo
    ):
        os_path_exists.return_value = False
        pathlib_path.return_value.glob.return_value = ["fakefile.txt"]
        processFile.return_value = True  # Changes detected
        diffItem = mock.Mock()
        diffItem.a_path = "difffakefile.txt"
        git_repo.clone_from.return_value.index.diff.return_value = [diffItem]

        app.main()

        processFile.assert_called_with(
            unittest.mock.ANY, unittest.mock.ANY, "fakefile.txt"
        )
        git_repo.clone_from.return_value.index.diff.assert_called_once_with(None)
        git_repo.clone_from.return_value.index.add.assert_called_once()
        assert list(git_repo.clone_from.return_value.index.add.call_args.args[0]) == [
            "difffakefile.txt"
        ]
        git_repo.clone_from.return_value.index.commit.assert_called_with(
            "Report detected changes",
            author=git.Actor("Archi Power Tools Inspector", "some@email.com"),
        )
        git_repo.clone_from.return_value.remotes.origin.push.assert_called_with()
