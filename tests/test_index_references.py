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

    def test_plain_text_gives_no_references(self):
        self.assertEqual([], I.extract_references("notes.txt", "Shape helper total\n"))


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


SQL_SAMPLE = "SELECT id, total FROM orders -- orders\nWHERE total > 0 AND note = 'orders';\n"


class SqlReferencesTest(unittest.TestCase):
    def test_identifiers_are_occurrences_and_keywords_comments_and_strings_are_not(self):
        found = I.extract_references("query.sql", SQL_SAMPLE)
        self.assertEqual([(line, column) for name, line, column in found if name == "orders"], [(1, 23)])
        self.assertEqual([(line, column) for name, line, column in found if name == "total"], [(1, 12), (2, 7)])
        names = [name for name, _line, _column in found]
        self.assertNotIn("SELECT", names)
        self.assertNotIn("WHERE", names)


HTML_SAMPLE = ('<!-- <p id="hidden"> -->\n<div id="main" class="card wide">\n'
               '  <a href="#main">Top</a>\n</div>\n')
CSS_SAMPLE = ('/* .ghost { } */\n@media (max-width: 600px) { .card { color: red; } }\n'
              '#main > a:hover, div.card[type="x"] { content: "a.b"; }\n')


class MarkupReferencesTest(unittest.TestCase):
    def test_element_names_ids_classes_and_references_to_ids_are_occurrences(self):
        names = [name for name, _line, _column in I.extract_references("page.html", HTML_SAMPLE)]
        self.assertEqual(names.count("main"), 2)  # the declaration and href="#main"
        self.assertEqual(names.count("div"), 2)  # the start tag and the end tag
        self.assertEqual(names.count("card"), 1)
        self.assertEqual(names.count("wide"), 1)

    def test_comments_hold_no_references(self):
        names = [name for name, _line, _column in I.extract_references("page.html", HTML_SAMPLE)]
        self.assertNotIn("hidden", names)
        self.assertNotIn("p", names)


class StyleReferencesTest(unittest.TestCase):
    def test_classes_ids_and_element_names_in_the_selectors_are_occurrences(self):
        names = [name for name, _line, _column in I.extract_references("site.css", CSS_SAMPLE)]
        self.assertEqual(names.count("card"), 2)  # .card in the media rule and div.card
        self.assertEqual(names.count("main"), 1)
        self.assertEqual(names.count("a"), 1)
        self.assertEqual(names.count("div"), 1)

    def test_comments_strings_at_rules_attributes_and_declarations_hold_none(self):
        names = [name for name, _line, _column in I.extract_references("site.css", CSS_SAMPLE)]
        for name in ("ghost", "media", "hover", "x", "b", "color", "red", "max-width"):
            self.assertNotIn(name, names)


class IndexedFilesTest(unittest.TestCase):
    def test_sql_and_style_sheets_are_read_into_the_references(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "orders.sql"), "w", encoding="utf-8") as handle:
                handle.write("SELECT total FROM orders;\n")
            with open(os.path.join(root, "site.css"), "w", encoding="utf-8") as handle:
                handle.write(".card { color: red; }\n")
            index = I.ProjectIndex(root)
            self.assertEqual([(line, column) for _path, line, column in index.references("orders")], [(1, 19)])
            self.assertEqual(len(index.references("card")), 1)

    def test_json_bare_down_and_template_files_are_read_into_the_references(self):
        with tempfile.TemporaryDirectory() as root:
            for name, text in (("config.json", JSON_SAMPLE), ("guide.bd", BAREDOWN_SAMPLE),
                               ("page.twig.html", TWIG_SAMPLE)):
                with open(os.path.join(root, name), "w", encoding="utf-8") as handle:
                    handle.write(text)
            index = I.ProjectIndex(root)
            self.assertEqual(sorted(os.path.basename(path) for path, _l, _c in index.references("Shape")),
                             ["config.json", "guide.bd", "guide.bd"])
            self.assertEqual(index.references("Circle"), [(os.path.join(root, "config.json"), 2, 18)])
            self.assertEqual(index.references("cls"), [(os.path.join(root, "page.twig.html"), 1, 15)])


JSON_SAMPLE = '{\n  "Shape": "App\\\\Circle",\n  "tax": "1.5",\n  "label": "Add to cart" // "Quoted"\n}\n'
BAREDOWN_SAMPLE = ("= Shape\nUse |Shape| and |$total|.\nSee [[Cart|the cart]] or [[docs/Order]].\n"
                   "~~~ php\n$s = new Shape(1);\n~~~\n~~~\nfoo(bar);\n~~~\n")
TWIG_SAMPLE = ('<h1 class="{{ cls }}">{{ title|upper }}</h1>\n{% for item in items %}<li>{{ item.name }}</li>'
               '{% endfor %}\n{# hidden: note #}\n')
MUSTACHE_SAMPLE = "<p>{{user.name}} {{{raw}}} {{#items}}{{.}}{{/items}} {{! hidden }}</p>\n"


class JsonReferencesTest(unittest.TestCase):
    def test_keys_and_names_in_values_are_occurrences_with_their_positions(self):
        self.assertEqual(I.extract_references("config.json", JSON_SAMPLE), [
            ("Shape", 2, 4), ("Circle", 2, 18), ("tax", 3, 4), ("label", 4, 4)])

    def test_a_string_that_is_no_name_and_the_comments_hold_none(self):
        names = [name for name, _line, _column in I.extract_references("config.json", JSON_SAMPLE)]
        self.assertNotIn("Add", names)
        self.assertNotIn("Quoted", names)

    def test_json_files_are_indexed_but_generated_lock_files_are_not(self):
        self.assertTrue(I.is_indexed("config.json"))
        self.assertFalse(I.is_indexed("web/package-lock.json"))
        self.assertTrue(I.is_indexed("guide.bd"))


class BareDownReferencesTest(unittest.TestCase):
    def test_code_spans_blocks_and_link_targets_are_occurrences(self):
        self.assertEqual(I.extract_references("guide.bd", BAREDOWN_SAMPLE), [
            ("Shape", 2, 6), ("Cart", 3, 7), ("Order", 3, 33), ("Shape", 5, 10), ("foo", 8, 1), ("bar", 8, 5)])

    def test_prose_labels_and_variables_hold_none(self):
        names = [name for name, _line, _column in I.extract_references("guide.bd", BAREDOWN_SAMPLE)]
        for word in ("Use", "and", "See", "the", "cart", "total"):
            self.assertNotIn(word, names)


MARKDOWN_SAMPLE = ("# Shape\nUse `Shape` and `$total` here. See [the cart](Cart) or [order](docs/Order.md).\n"
                   "```php\n$s = new Shape(1);\n```\n```\nfoo(bar);\n```\n")


class MarkdownReferencesTest(unittest.TestCase):
    def test_code_spans_blocks_and_link_names_are_occurrences(self):
        self.assertEqual(I.extract_references("guide.md", MARKDOWN_SAMPLE), [
            ("Shape", 2, 6), ("Cart", 2, 47), ("Shape", 4, 10), ("foo", 7, 1), ("bar", 7, 5)])

    def test_prose_variables_and_links_to_files_hold_none(self):
        names = [name for name, _line, _column in I.extract_references("guide.md", MARKDOWN_SAMPLE)]
        for word in ("Use", "and", "here", "order", "Order", "total", "cart"):
            self.assertNotIn(word, names)


class TemplateReferencesTest(unittest.TestCase):
    def test_names_in_twig_tags_and_in_the_base_markup(self):
        self.assertEqual(I.extract_references("page.twig.html", TWIG_SAMPLE), [
            ("h1", 1, 2), ("cls", 1, 15), ("title", 1, 26), ("h1", 1, 42), ("item", 2, 8), ("items", 2, 16),
            ("li", 2, 25), ("item", 2, 31), ("name", 2, 36), ("li", 2, 45)])

    def test_names_in_mustache_tags(self):
        self.assertEqual(I.extract_references("view.mustache.html", MUSTACHE_SAMPLE), [
            ("p", 1, 2), ("user", 1, 6), ("name", 1, 11), ("raw", 1, 21), ("items", 1, 31), ("items", 1, 46),
            ("p", 1, 69)])

    def test_filters_keywords_comments_and_strings_hold_none(self):
        names = [name for name, _line, _column in I.extract_references("page.twig.html", TWIG_SAMPLE)]
        for word in ("upper", "for", "in", "endfor", "hidden", "note"):
            self.assertNotIn(word, names)
        source = "{{ 'Shape' }} {{ name|upper }}"
        names = [name for name, _line, _column in I.extract_references("page.twig.txt", source)]
        self.assertEqual(names, ["name"])


if __name__ == "__main__":
    unittest.main()
