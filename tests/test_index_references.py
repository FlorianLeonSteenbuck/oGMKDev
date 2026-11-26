import json
import os
import tempfile
import unittest

from ogmkdev import index as I

PYTHON_SAMPLE = '''import os
from pkg import helper as h

class Shop:
    def total(self, price):
        return self.tax + price  # comment helper
s = "helper"
x = h.run("ü", price)  # trailing
'''

SCRIPT_SAMPLE = '''// helper in a comment
const s = "helper";
function total(price) { return helper(price) + obj.tax; }
'''


class PythonReferencesTest(unittest.TestCase):
    def test_names_attributes_declarations_and_arguments_with_their_positions(self):
        found = set(I.extract_references("a.py", PYTHON_SAMPLE))
        self.assertIn(("Shop", 4, 7), found)
        self.assertIn(("total", 5, 9), found)
        self.assertIn(("self", 5, 15), found)
        self.assertIn(("price", 5, 21), found)
        self.assertIn(("tax", 6, 21), found)
        self.assertIn(("helper", 2, 17), found)  # the imported name, not the alias

    def test_comments_and_strings_hold_no_references(self):
        names = [name for name, _line, _column in I.extract_references("a.py", PYTHON_SAMPLE)]
        self.assertNotIn("trailing", names)
        self.assertEqual(names.count("helper"), 1)  # only the import line

    def test_columns_count_characters_not_bytes(self):
        # the umlaut before `price` is two bytes in UTF-8; the column still counts characters
        self.assertIn(("price", 8, 16), I.extract_references("a.py", PYTHON_SAMPLE))

    def test_a_file_that_does_not_parse_gives_no_references(self):
        self.assertEqual([], I.extract_references("broken.py", "def (:\n"))


class ScriptReferencesTest(unittest.TestCase):
    def test_identifiers_with_their_positions_and_keywords_left_out(self):
        found = I.extract_references("a.js", SCRIPT_SAMPLE)
        self.assertIn(("s", 2, 7), found)
        self.assertIn(("total", 3, 10), found)
        self.assertIn(("helper", 3, 32), found)
        self.assertIn(("tax", 3, 52), found)
        names = [name for name, _line, _column in found]
        self.assertNotIn("function", names)
        self.assertNotIn("return", names)
        self.assertNotIn("const", names)

    def test_comments_and_strings_hold_no_references(self):
        found = I.extract_references("a.js", SCRIPT_SAMPLE)
        self.assertEqual(sum(1 for name, _l, _c in found if name == "helper"), 1)

    def test_other_languages_give_none_yet(self):
        self.assertEqual([], I.extract_references("a.css", "a { color: red; }\n"))


class ProjectReferencesTest(unittest.TestCase):
    def _project(self, root):
        with open(os.path.join(root, "a.py"), "w", encoding="utf-8") as handle:
            handle.write(PYTHON_SAMPLE)
        with open(os.path.join(root, "b.js"), "w", encoding="utf-8") as handle:
            handle.write(SCRIPT_SAMPLE)

    def test_references_of_a_name_across_the_files_in_order(self):
        with tempfile.TemporaryDirectory() as root:
            self._project(root)
            index = I.ProjectIndex([root])
            hits = index.references("helper")
            self.assertEqual({os.path.basename(path) for path, _l, _c in hits}, {"a.py", "b.js"})
            self.assertEqual(sorted(hits), hits)
            self.assertIn((os.path.join(root, "b.js"), 3, 32), hits)
            self.assertEqual(index.references("no-such-name"), [])

    def test_the_cache_keeps_the_references(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cache_dir:
            self._project(root)
            cache = os.path.join(cache_dir, "index.json")
            first = I.ProjectIndex([root])
            first.save_cache(cache)
            second = I.ProjectIndex([root], cache_path=cache)
            self.assertEqual(second.references("total"), first.references("total"))
            self.assertTrue(second.references("total"))

    def test_a_cache_of_another_version_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cache_dir:
            self._project(root)
            cache = os.path.join(cache_dir, "index.json")
            I.ProjectIndex([root]).save_cache(cache)
            with open(cache, encoding="utf-8") as handle:
                data = json.load(handle)
            data["version"] = I.CACHE_VERSION - 1
            for entry in data["files"].values():
                entry.pop("references", None)
            with open(cache, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            rebuilt = I.ProjectIndex([root], cache_path=cache)
            self.assertTrue(rebuilt.references("helper"))


PHP_SAMPLE = ("<?php\nnamespace App;\n// Circle in a comment\nclass Circle {\n"
              "    public function area() { return $this->Circle; }\n}\n"
              "$c = new \\App\\Circle('Circle');\n")


class PhpReferencesTest(unittest.TestCase):
    def test_names_are_occurrences_and_comments_strings_and_variables_are_not(self):
        refs = I.extract_references("/project/circle.php", PHP_SAMPLE)
        circle = [(line, column) for name, line, column in refs if name == "Circle"]
        self.assertEqual(circle, [(4, 7), (5, 44), (7, 15)])

    def test_a_qualified_name_is_an_occurrence_of_its_last_part(self):
        refs = I.extract_references("/project/circle.php", PHP_SAMPLE)
        self.assertIn(("Circle", 7, 15), refs)
        self.assertFalse(any(name.startswith("\\") or "\\" in name for name, _l, _c in refs))


TSX_SAMPLE = 'const card = (props: Props) => <Panel className="wrap">Add to cart {props.total}</Panel>;\n'
TS_SAMPLE = "interface Shape { area(): number }\nconst s: Shape = make(); // Shape in a comment\nconst t = 'Shape';\n"


class TypedScriptReferencesTest(unittest.TestCase):
    def test_a_jsx_element_name_is_an_occurrence_and_jsx_text_is_not(self):
        names = [name for name, _line, _column in I.extract_references("card.tsx", TSX_SAMPLE)]
        self.assertIn("Panel", names)
        self.assertIn("props", names)
        self.assertNotIn("cart", names)
        self.assertNotIn("Add", names)

    def test_types_are_occurrences_with_their_positions(self):
        found = I.extract_references("shape.ts", TS_SAMPLE)
        self.assertEqual([(line, column) for name, line, column in found if name == "Shape"], [(1, 11), (2, 10)])


if __name__ == "__main__":
    unittest.main()
