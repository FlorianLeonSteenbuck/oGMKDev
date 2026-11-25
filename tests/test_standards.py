import unittest

from ogmkdev import diagnostics, languages, standards
from ogmkdev.editorconfig import settings_from_properties


def rules(text, **properties):
    return standards.problems(text, settings_from_properties(properties))


class TrailingWhitespaceTest(unittest.TestCase):
    def test_trailing_blanks_are_reported_only_when_the_rule_is_set(self):
        self.assertEqual([(1, 2, "trailing-whitespace", "hint", "trailing spaces or tabs at the end of the line")],
                         rules("a  \nb\n", trim_trailing_whitespace="true"))
        self.assertEqual([], rules("a  \nb\n"))


class IndentStyleTest(unittest.TestCase):
    def test_a_tab_in_a_space_file_and_spaces_in_a_tab_file(self):
        self.assertEqual("indented with a tab, the style is spaces",
                         rules("\tx\n", indent_style="space")[0][4])
        self.assertEqual("indented with spaces, the style is tabs",
                         rules("    x\n", indent_style="tab")[0][4])
        self.assertEqual([], rules("    x\n", indent_style="space"))

    def test_tabs_and_spaces_mixed_in_one_indentation_are_reported(self):
        self.assertEqual("indentation mixes tabs and spaces", rules(" \tx\n", indent_style="space")[0][4])
        self.assertEqual("indentation mixes tabs and spaces", rules(" \tx\n", indent_style="tab")[0][4])

    def test_a_doc_comment_continuation_after_tabs_is_no_mix(self):
        self.assertEqual([], rules("\t/**\n\t * doc\n\t */\n", indent_style="tab"))


class LineLengthTest(unittest.TestCase):
    def test_a_line_longer_than_the_limit_counts_tabs_with_tab_width(self):
        problems = rules("\tabcdefghi\nshort\n", max_line_length="10", tab_width="4")
        self.assertEqual([(1, 11, "line-length", "warning", "line is 13 characters, the limit is 10")], problems)

    def test_without_the_setting_no_line_is_too_long(self):
        self.assertEqual([], rules("x" * 500 + "\n"))


class LineEndingsTest(unittest.TestCase):
    def test_a_line_ending_against_end_of_line_is_reported(self):
        problems = rules("a\r\nb\n", end_of_line="lf")
        self.assertEqual([(1, 2, "line-endings", "warning", "line ends with CRLF, end_of_line is LF")], problems)
        self.assertEqual([(1, 2, "line-endings", "warning", "line ends with LF, end_of_line is CRLF")],
                         rules("a\nbc\r\n", end_of_line="crlf"))

    def test_mixed_endings_are_reported_when_no_setting_says_which(self):
        self.assertEqual([(1, 1, "line-endings", "warning", "mixed line endings: 1 with CRLF, 1 with LF")],
                         rules("a\r\nb\n"))
        self.assertEqual([], rules("a\nb\n"))


class FinalNewlineTest(unittest.TestCase):
    def test_a_file_without_a_final_newline_is_reported_when_required(self):
        self.assertEqual([(2, 2, "final-newline", "hint", "the file does not end with a newline")],
                         rules("a\nb", insert_final_newline="true"))
        self.assertEqual([], rules("a\n", insert_final_newline="true"))
        self.assertEqual([], rules("", insert_final_newline="true"))


class DiagnosticsTest(unittest.TestCase):
    def test_the_rules_reach_the_diagnostics_with_their_severity_and_can_be_switched_off(self):
        detection = languages.detect("notes.txt", {})
        props = {"trim_trailing_whitespace": "true", "max_line_length": "5"}
        settings = settings_from_properties(dict(props))
        codes = {item.code for item in diagnostics.analyze("abcdefgh  \n", detection, settings)}
        self.assertIn("trailing-whitespace", codes)
        self.assertIn("line-length", codes)

        off = dict(props, ogmkdev_diagnostic_line_length="off")
        codes = {item.code for item in diagnostics.analyze("abcdefgh  \n", detection,
                                                           settings_from_properties(off))}
        self.assertNotIn("line-length", codes)
        self.assertIn("trailing-whitespace", codes)

        hint = dict(props, ogmkdev_diagnostic_trailing_whitespace="error")
        severities = {item.code: item.severity for item in
                      diagnostics.analyze("abcdefgh  \n", detection, settings_from_properties(hint))}
        self.assertEqual("error", severities["trailing-whitespace"])


if __name__ == "__main__":
    unittest.main()
