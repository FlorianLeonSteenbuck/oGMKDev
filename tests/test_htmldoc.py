import contextlib
import io
import os
import tempfile
import unittest

from ogmkdev import htmldoc as H
from ogmkdev import index as I


class FindingBlocksTest(unittest.TestCase):
    def test_the_block_above_skips_attributes_and_blank_lines(self):
        lines = ["/**", " * Doc.", " */", "", "#[Route('/x')]", "public function run() {}"]
        self.assertEqual("Doc.", H.block_above(lines, 6))

    def test_a_decorator_between_block_and_declaration_is_skipped(self):
        lines = ["/**", " * Adds.", " */", "@Input()", "export class Cart {}"]
        self.assertEqual("Adds.", H.block_above(lines, 5))

    def test_line_comments_and_plain_block_comments_are_no_doc_block(self):
        self.assertIsNone(H.block_above(["// not a doc", "function f() {}"], 2))
        self.assertIsNone(H.block_above(["/* plain */", "function f() {}"], 2))

    def test_no_block_gives_none(self):
        self.assertIsNone(H.block_above(["int x;", "function f() {}"], 2))


class ParsingBlocksTest(unittest.TestCase):
    def test_phpdoc_tags_keep_type_name_and_text(self):
        doc = H.parse_block("Summary line.\n\nMore text.\n@param string $name The name\n"
                            "  continued here\n@return int The count\n@throws \\LogicException when negative")
        self.assertEqual("Summary line.", doc.summary)
        self.assertEqual(["More text."], doc.description)
        param, returns, throws = doc.tags
        self.assertEqual(("param", "string", "$name", "The name continued here"),
                         (param.name, param.type, param.subject, param.text))
        self.assertEqual(("return", "int", "The count"), (returns.name, returns.type, returns.text))
        self.assertEqual(("throws", "\\LogicException", "when negative"), (throws.name, throws.type, throws.text))

    def test_jsdoc_types_in_braces_and_returns(self):
        doc = H.parse_block("Adds.\n@param {string} sku - the article number\n@returns {number} the new count")
        param, returns = doc.tags
        self.assertEqual(("string", "sku", "the article number"), (param.type, param.subject, param.text))
        self.assertEqual(("return", "number", "the new count"), (returns.name, returns.type, returns.text))

    def test_python_google_sections_become_tags(self):
        doc = H.parse_python_docstring(
            "Builds the report.\n\nArgs:\n    width: the line width.\n    rate (float): the tax.\n\n"
            "Returns:\n    The text.\n\nRaises:\n    ValueError: when the width is zero.")
        self.assertEqual("Builds the report.", doc.summary)
        width, rate, returns, raises = doc.tags
        self.assertEqual(("param", "width", "", "the line width."), (width.name, width.subject, width.type, width.text))
        self.assertEqual(("float", "the tax."), (rate.type, rate.text))
        self.assertEqual(("return", "The text."), (returns.name, returns.text))
        self.assertEqual(("throws", "ValueError", "when the width is zero."), (raises.name, raises.type, raises.text))


class ExportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "project")
        self.out = os.path.join(self._tmp.name, "docs")
        os.makedirs(os.path.join(self.root, "shop"))
        os.makedirs(os.path.join(self.root, "web"))
        with open(os.path.join(self.root, "shop", "Product.php"), "w", encoding="utf-8") as handle:
            handle.write("<?php\nnamespace Shop;\n\n/**\n * A product.\n *\n * Stored as <b>cents</b>.\n */\n"
                         "final class Product\n{\n}\n")
        with open(os.path.join(self.root, "web", "cart.ts"), "w", encoding="utf-8") as handle:
            handle.write("/**\n * Adds an item.\n * @param {string} sku - the number\n */\n"
                         "export function addItem(sku: string): number {\n  return 1;\n}\n")
            handle.write("\nexport function undocumented() {}\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_each_file_gets_a_page_and_the_index_links_them(self):
        result = H.export(I.ProjectIndex(self.root), self.out)
        self.assertEqual((2, 3, 2), (result.files, result.declarations, result.documented))
        index = open(os.path.join(self.out, "index.html"), encoding="utf-8").read()
        self.assertIn('href="pages/shop/Product.php.html"', index)
        self.assertIn('href="pages/web/cart.ts.html"', index)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "style.css")))

    def test_the_pages_show_the_description_and_escape_the_text(self):
        H.export(I.ProjectIndex(self.root), self.out)
        page = open(os.path.join(self.out, "pages", "shop", "Product.php.html"), encoding="utf-8").read()
        self.assertIn('<p class="summary">A product.</p>', page)
        self.assertIn("Stored as &lt;b&gt;cents&lt;/b&gt;.", page)
        self.assertNotIn("<b>cents</b>", page)

    def test_declarations_without_a_doc_comment_say_so(self):
        H.export(I.ProjectIndex(self.root), self.out)
        page = open(os.path.join(self.out, "pages", "web", "cart.ts.html"), encoding="utf-8").read()
        self.assertIn("@param sku", page)
        self.assertIn("No doc comment.", page)

    def test_the_command_line_exports_the_folders(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = H.main([self.root, "-o", self.out])
        self.assertEqual(0, status)
        self.assertIn("2 files, 3 declarations (2 with a doc comment)", output.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.out, "index.html")))


if __name__ == "__main__":
    unittest.main()
