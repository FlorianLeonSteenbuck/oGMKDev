"""The settings model: the category tree, the search, the typed values, the colours and the pairs. A text that is not a
valid value comes back as a Failure, a return value. It leaves the model as it was, and nothing is raised for it."""

import unittest

from ogmkdev import settings as S
from ogmkdev.othersettings import ColorPickerProvider, PairsProvider, PreStoredSettings
from ogmkdev.outcome import Failure, failed, then


class FailureTests(unittest.TestCase):
    def test_a_failure_is_text_with_its_reason(self):
        result = failed("not a number")
        self.assertIsInstance(result, Failure)
        self.assertEqual(result, "not a number")

    def test_then_applies_to_a_value_and_passes_a_failure_through(self):
        self.assertEqual(then(3, lambda n: n * 10), 30)
        passed = then(failed("bad"), lambda n: n * 10)
        self.assertIsInstance(passed, Failure)
        self.assertEqual(passed, "bad")


class CategoryTreeTests(unittest.TestCase):
    def test_categories_nest_to_the_depth_of_their_paths(self):
        tree = S.category_tree()
        names = [node["name"] for node in tree]
        self.assertIn("Diagnostics", names)
        diagnostics = next(node for node in tree if node["name"] == "Diagnostics")
        php = next(node for node in diagnostics["children"] if node["name"] == "PHP")
        self.assertEqual(php["path"], "Diagnostics / PHP")
        self.assertEqual({s.key for s in php["settings"]},
                         {"ogmkdev_diagnostic_php_function", "ogmkdev_diagnostic_php_partial_application"})

    def test_every_setting_sits_in_exactly_one_node(self):
        found = []

        def walk(nodes):
            for node in nodes:
                found.extend(node["settings"])
                walk(node["children"])

        walk(S.category_tree())
        self.assertEqual(sorted(s.key for s in found), sorted(s.key for s in S.SCHEMA))

    def test_a_category_contains_its_children(self):
        setting = S.SETTINGS_BY_KEY["ogmkdev_diagnostic_php_function"]
        self.assertTrue(S.in_category(setting, "Diagnostics"))
        self.assertTrue(S.in_category(setting, "Diagnostics / PHP"))
        self.assertFalse(S.in_category(setting, "Diagnostics / Style"))
        self.assertFalse(S.in_category(setting, "Diagnostic"))  # a prefix of a word is no category


class SearchTests(unittest.TestCase):
    def test_an_empty_query_finds_every_setting(self):
        self.assertEqual(len(S.search("")), len(S.SCHEMA))

    def test_every_word_must_occur_ignoring_case(self):
        keys = [s.key for s in S.search("DIAGNOSTIC php")]
        self.assertIn("ogmkdev_diagnostic_php_function", keys)
        self.assertNotIn("ogmkdev_diagnostic_css_braces", keys)

    def test_the_label_the_key_and_the_category_are_searched(self):
        self.assertIn("ogmkdev_change_color_added", [s.key for s in S.search("added")])
        self.assertIn("indent_size", [s.key for s in S.search("indent_size")])
        self.assertIn("indent_style", [s.key for s in S.search("Indentation")])


class ParseTests(unittest.TestCase):
    def test_a_valid_text_gives_its_value(self):
        self.assertEqual(S.parse_value(S.SETTINGS_BY_KEY["indent_size"], "2"), 2)
        self.assertIs(S.parse_value(S.SETTINGS_BY_KEY["trim_trailing_whitespace"], "TRUE"), True)

    def test_an_invalid_text_is_a_failure_with_its_reason(self):
        result = S.parse_value(S.SETTINGS_BY_KEY["indent_size"], "two")
        self.assertIsInstance(result, Failure)
        self.assertIn("whole number", result)
        self.assertIsInstance(S.parse_value(S.SETTINGS_BY_KEY["insert_final_newline"], "maybe"), Failure)

    def test_the_lenient_reading_of_a_file_falls_back_to_the_default(self):
        self.assertEqual(S.typed_value(S.SETTINGS_BY_KEY["indent_size"], "two"), 4)
        self.assertIs(S.typed_value(S.SETTINGS_BY_KEY["insert_final_newline"], "maybe"), True)

    def test_a_colour_is_checked_and_kept_in_capitals(self):
        colour = S.SETTINGS_BY_KEY["ogmkdev_change_color_added"]
        self.assertEqual(S.parse_value(colour, "#3fb950"), "#3FB950")
        self.assertIsInstance(S.parse_value(colour, "green"), Failure)
        self.assertIsInstance(S.parse_value(colour, "#3FB95"), Failure)

    def test_pairs_are_keyword_and_priority(self):
        todo = S.SETTINGS_BY_KEY["ogmkdev_todo_keywords"]
        self.assertEqual(S.parse_value(todo, "FIXME:1, TODO:3"), [("FIXME", 1), ("TODO", 3)])
        self.assertEqual(S.parse_value(todo, ""), [])
        for text in ("FIXME", "FIXME:high", ":1", "1X:2"):
            self.assertIsInstance(S.parse_value(todo, text), Failure, text)


class ModelTests(unittest.TestCase):
    def test_every_default_fits_its_provider(self):
        model = S.build_model({})
        self.assertEqual(S.model_values(model), {s.key: s.default for s in S.SCHEMA})

    def test_values_survive_the_round_trip_through_the_model(self):
        model = S.build_model({"ogmkdev_appearance": "dark", "trim_trailing_whitespace": "true", "tab_width": "2"})
        values = S.model_values(model)
        self.assertEqual(values["ogmkdev_appearance"], "dark")
        self.assertEqual(values["trim_trailing_whitespace"], "true")
        self.assertEqual(values["tab_width"], "2")

    def test_a_colour_and_pairs_are_held_by_their_providers(self):
        model = S.build_model({"ogmkdev_change_color_added": "#112233", "ogmkdev_todo_keywords": "BUG:9"})
        providers = model.get_setting_providers()
        self.assertIsInstance(providers["ogmkdev_change_color_added"], ColorPickerProvider)
        self.assertIsInstance(providers["ogmkdev_todo_keywords"], PairsProvider)
        self.assertEqual(model.get_color("ogmkdev_change_color_added"), "#112233")
        self.assertEqual(model.get_pairs("ogmkdev_todo_keywords"), [("BUG", 9)])

    def test_a_bad_colour_or_pairs_text_leaves_the_model_as_it_was(self):
        model = S.build_model({"ogmkdev_change_color_added": "#112233", "ogmkdev_todo_keywords": "BUG:9"})
        colour = S.SETTINGS_BY_KEY["ogmkdev_change_color_added"]
        pairs = S.SETTINGS_BY_KEY["ogmkdev_todo_keywords"]
        self.assertIsInstance(S.set_model_text(model, colour, "red"), Failure)
        self.assertIsInstance(S.set_model_text(model, pairs, "BUG"), Failure)
        self.assertEqual(S.model_text(model, colour), "#112233")
        self.assertEqual(S.model_text(model, pairs), "BUG:9")

    def test_a_bad_text_leaves_the_model_as_it_was(self):
        model = S.build_model({"indent_size": "8"})
        setting = S.SETTINGS_BY_KEY["indent_size"]
        self.assertIsInstance(S.set_model_text(model, setting, "abc"), Failure)
        self.assertEqual(model.get("indent_size"), 8)
        self.assertEqual(S.set_model_text(model, setting, "2"), 2)
        self.assertEqual(model.get("indent_size"), 2)

    def test_pairs_are_stored_as_a_copy(self):
        model = S.build_model({})
        pairs = [("BUG", 2)]
        model.set_pairs("ogmkdev_todo_keywords", pairs)
        pairs.append(("LATER", 1))
        self.assertEqual(model.get_pairs("ogmkdev_todo_keywords"), [("BUG", 2)])

    def test_a_missing_value_reads_as_the_default(self):
        self.assertEqual(S.model_text(PreStoredSettings({}), S.SETTINGS_BY_KEY["indent_size"]), "4")

    def test_the_text_of_a_value_of_another_type_is_the_default(self):
        self.assertEqual(S.text_value(S.SETTINGS_BY_KEY["indent_size"], ["x"]), "4")


if __name__ == "__main__":
    unittest.main()
