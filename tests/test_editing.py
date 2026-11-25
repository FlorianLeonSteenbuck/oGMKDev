import unittest

from ogmkdev.editing import encode_for_save, indent_unit, prepare_for_save
from ogmkdev.editorconfig import EditorSettings


class SaveTests(unittest.TestCase):
    def test_trim_final_newline_and_crlf(self):
        s = EditorSettings(trim_trailing_whitespace=True, insert_final_newline=True, end_of_line="crlf")
        self.assertEqual(prepare_for_save("a  \nb\t\n\n\n", s), "a\r\nb\r\n")

    def test_no_changes_when_unset(self):
        self.assertEqual(prepare_for_save("x  \r\n", EditorSettings()), "x  \n")

    def test_bom_and_latin1(self):
        self.assertTrue(encode_for_save("hi", EditorSettings(charset="utf-8-bom")).startswith(b"\xef\xbb\xbf"))
        self.assertEqual(encode_for_save("é", EditorSettings(charset="latin1")), b"\xe9")

    def test_indent_unit(self):
        self.assertEqual(indent_unit(EditorSettings(indent_style="tab")), "\t")
        self.assertEqual(indent_unit(EditorSettings(indent_style="space", indent_size=2)), "  ")
        self.assertEqual(indent_unit(EditorSettings()), "    ")


if __name__ == "__main__":
    unittest.main()
