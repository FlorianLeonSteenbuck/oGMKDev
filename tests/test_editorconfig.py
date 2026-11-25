import os
import tempfile
import unittest

from ogmkdev import editorconfig as ec


def _match(glob: str, rel: str) -> bool:
    return ec.compile_section_glob(glob).match(rel) is not None


class GlobTests(unittest.TestCase):
    def test_name_without_slash_matches_at_any_depth(self):
        self.assertTrue(_match("*.py", "main.py"))
        self.assertTrue(_match("*.py", "pkg/sub/main.py"))
        self.assertFalse(_match("*.py", "main.pyc"))

    def test_star_does_not_cross_directories(self):
        self.assertTrue(_match("src/*.c", "src/a.c"))
        self.assertFalse(_match("src/*.c", "src/deep/a.c"))
        self.assertFalse(_match("src/*.c", "other/src/a.c"))

    def test_double_star_crosses_directories(self):
        self.assertTrue(_match("src/**.c", "src/deep/er/a.c"))
        self.assertTrue(_match("**/test", "test"))
        self.assertTrue(_match("**/test", "a/b/test"))

    def test_leading_slash_anchors_to_config_dir(self):
        self.assertTrue(_match("/top.txt", "top.txt"))
        self.assertFalse(_match("/top.txt", "sub/top.txt"))

    def test_question_mark_and_character_classes(self):
        self.assertTrue(_match("file?.txt", "file1.txt"))
        self.assertFalse(_match("file?.txt", "file12.txt"))
        self.assertTrue(_match("[abc].txt", "b.txt"))
        self.assertFalse(_match("[!abc].txt", "b.txt"))
        self.assertTrue(_match("[!abc].txt", "z.txt"))

    def test_braces_alternatives_and_numeric_ranges(self):
        self.assertTrue(_match("*.{js,ts}", "app.ts"))
        self.assertFalse(_match("*.{js,ts}", "app.tsx"))
        self.assertTrue(_match("v{1..3}.txt", "v2.txt"))
        self.assertFalse(_match("v{1..3}.txt", "v4.txt"))
        self.assertTrue(_match("{single}", "{single}"))

    def test_escapes_and_regex_metacharacters_are_literal(self):
        self.assertTrue(_match("a+b.txt", "a+b.txt"))
        self.assertFalse(_match("a+b.txt", "aab.txt"))
        self.assertTrue(_match("\\*.txt", "*.txt"))
        self.assertFalse(_match("\\*.txt", "a.txt"))


class ParseAndResolveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_parse_preamble_root_and_comments(self):
        cfg = ec.parse("# comment\nroot = TRUE\n\n[*]\n; another\nIndent_Style = Space\n")
        self.assertTrue(cfg.root)
        self.assertEqual(cfg.sections[0].properties, {"indent_style": "space"})

    def test_nearer_file_and_later_section_win_and_unset_removes(self):
        self._write(".editorconfig", "root = true\n[*]\nindent_style = space\nindent_size = 4\n"
                                     "charset = utf-8\n[*.md]\ncharset = unset\n")
        self._write("sub/.editorconfig", "[*.py]\nindent_size = 2\n[*]\nindent_size = 8\n")
        props = ec.effective_properties(os.path.join(self.root, "sub", "mod.py"))
        self.assertEqual(props["indent_style"], "space")
        self.assertEqual(props["indent_size"], "8")  # later [*] in the nearer file beats [*.py]
        self.assertEqual(props["charset"], "utf-8")
        md = ec.effective_properties(os.path.join(self.root, "README.md"))
        self.assertNotIn("charset", md)

    def test_root_true_stops_the_search_upwards(self):
        self._write("outer/.editorconfig", "[*]\nindent_size = 9\n")  # must be ignored
        self._write("outer/inner/.editorconfig", "root = true\n[*]\nindent_size = 3\n")
        target = os.path.join(self.root, "outer", "inner", "x.txt")
        self.assertEqual(len(ec.find_config_files(target)), 1)
        self.assertEqual(ec.effective_properties(target)["indent_size"], "3")

    def test_sections_are_relative_to_their_own_config_file(self):
        self._write("proj/.editorconfig", "root = true\n[gen/*.c]\nindent_size = 1\n")
        hit = ec.effective_properties(os.path.join(self.root, "proj", "gen", "a.c"))
        miss = ec.effective_properties(os.path.join(self.root, "proj", "x", "gen", "a.c"))
        self.assertEqual(hit.get("indent_size"), "1")
        self.assertNotIn("indent_size", miss)


class SettingsTests(unittest.TestCase):
    def test_tab_style_without_size_uses_tab_width(self):
        s = ec.settings_from_properties({"indent_style": "tab", "tab_width": "4"})
        self.assertEqual((s.indent_style, s.indent_size, s.tab_width), ("tab", 4, 4))

    def test_indent_size_tab_takes_tab_width(self):
        s = ec.settings_from_properties({"indent_style": "space", "indent_size": "tab", "tab_width": "8"})
        self.assertEqual((s.indent_size, s.tab_width), (8, 8))

    def test_tab_width_defaults_to_indent_size(self):
        s = ec.settings_from_properties({"indent_style": "space", "indent_size": "2"})
        self.assertEqual((s.indent_size, s.tab_width), (2, 2))

    def test_core_values_normalised_and_invalid_ignored(self):
        s = ec.settings_from_properties({
            "indent_style": "mixed", "end_of_line": "crlf", "charset": "utf-8-bom",
            "trim_trailing_whitespace": "true", "insert_final_newline": "false",
            "max_line_length": "off",
        })
        self.assertIsNone(s.indent_style)
        self.assertEqual(s.end_of_line, "crlf")
        self.assertEqual(s.charset, "utf-8-bom")
        self.assertIs(s.trim_trailing_whitespace, True)
        self.assertIs(s.insert_final_newline, False)
        self.assertIsNone(s.max_line_length)

    def test_custom_keys_are_kept_for_language_scoping(self):
        s = ec.settings_from_properties({"ogmkdev_language": "mysql", "indent_size": "4"})
        self.assertEqual(s.custom, {"ogmkdev_language": "mysql"})


if __name__ == "__main__":
    unittest.main()
