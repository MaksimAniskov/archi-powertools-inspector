import debug_processing_single_file

import unittest
from unittest import mock

builtin_open = open


@mock.patch(
    "sys.argv",
    ["program_name", "fake-file.xml"],
)
class TestMain(unittest.TestCase):

    @mock.patch("lib.processFile")
    def test_main_no_changes_detected(self, processFile):
        processFile.return_value = False  # No changes detected
        debug_processing_single_file.main()

    @mock.patch("lib.processFile")
    def test_main_change_detected(self, processFile):
        processFile.return_value = True  # Changes detected

        def my_open(*args, **kwargs):
            filename = args[0]
            if filename == "fake-file.xml":
                content = """
                    <root>
                        <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                        <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                        <properties key="pwrt:inspector:value" value="oldvalue"/>
                    </root>"""
            elif filename == "processed.xml":
                content = """
                    <root>
                        <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                        <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
                        <properties key="pwrt:inspector:value" value="newvalue"/>
                    </root>"""
            else:
                return builtin_open(*args, **kwargs)

            file_object = mock.mock_open(read_data=content).return_value
            file_object.__iter__.return_value = content.splitlines(True)
            return file_object

        with mock.patch("builtins.open", new=my_open), mock.patch(
            "builtins.print"
        ) as mock_print:
            debug_processing_single_file.main()
            mock_print.assert_called_with(
                """  
                      <root>
                          <properties key="pwrt:inspector:value-ref" value="someproto://some.host/some/path/file.ext@a1b2c3d4#L1"/>
                          <properties key="pwrt:inspector:value-regexp" value="(.*)"/>
-                         <properties key="pwrt:inspector:value" value="oldvalue"/>
?                                                                       ^^^
+                         <properties key="pwrt:inspector:value" value="newvalue"/>
?                                                                       ^^^
                      </root>"""
            )
