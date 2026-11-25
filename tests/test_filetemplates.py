import datetime
import os
import tempfile
import unittest

from ogmkdev import filetemplates as F

TODAY = datetime.date(2026, 11, 25)


class FileTemplateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_builtin_template_expands_the_name_and_puts_the_cursor_in_the_body(self):
        text, cursor, has_template = F.new_file_text("cart.html", {}, self.project, "web", TODAY)
        self.assertTrue(has_template)
        self.assertIn("<title>Cart</title>", text)
        self.assertNotIn("$0", text)
        self.assertTrue(text[:cursor].endswith("<body>\n"))

    def test_the_name_folder_year_and_date_are_filled_in(self):
        path = os.path.join(self.project, "component.ts.tpl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("${name} | ${Name} | ${folder} | ${year} | ${date}\n$0")
        properties = {F.setting_key("ts"): "component.ts.tpl"}
        text, cursor, _ = F.new_file_text("cart_item.ts", properties, self.project, "shop", TODAY)
        self.assertEqual("cart_item | CartItem | shop | 2026 | 2026-11-25\n", text)
        self.assertEqual(len(text), cursor)

    def test_a_configured_file_wins_over_the_builtin_template(self):
        with open(os.path.join(self.project, "php-file.tpl"), "w", encoding="utf-8") as handle:
            handle.write("<?php // ${name}\n$0")
        properties = {F.setting_key("php"): "php-file.tpl"}
        text, _, _ = F.new_file_text("shop.php", properties, self.project, "x", TODAY)
        self.assertEqual("<?php // shop\n", text)

    def test_an_absolute_path_is_used_as_it_is(self):
        path = os.path.join(self.project, "absolute.tpl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("abs $0")
        text, cursor, _ = F.new_file_text("notes.md", {F.setting_key("md"): path}, "/elsewhere", "x", TODAY)
        self.assertEqual(("abs ", 4), (text, cursor))

    def test_a_missing_configured_file_is_an_error(self):
        with self.assertRaises(F.FileTemplateError):
            F.new_file_text("a.css", {F.setting_key("css"): "missing.tpl"}, self.project, "x", TODAY)

    def test_an_extension_without_template_gives_an_empty_file(self):
        self.assertEqual(("", 0, False), F.new_file_text("notes.xyz", {}, self.project, "x", TODAY))

    def test_the_setting_key_is_per_extension_and_lower_case(self):
        self.assertEqual("ogmkdev_filetemplate_php", F.setting_key("PHP"))
        self.assertEqual("php", F.extension_of("Shop.PHP"))
        self.assertEqual("", F.extension_of(".editorconfig"))


class CreateNewFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        self.folder = os.path.join(self.project, "shop")
        os.makedirs(self.folder)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_file_is_written_and_the_cursor_is_located(self):
        created = F.create_new_file(self.folder, "cart.html", self.project, {}, TODAY)
        self.assertEqual(os.path.join(self.folder, "cart.html"), created.path)
        with open(created.path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("<title>Cart</title>", text)
        self.assertEqual("<body>", text.splitlines()[created.line - 2])
        self.assertEqual("created cart.html from its file template", created.message)
        self.assertGreater(created.line, 1)

    def test_an_existing_file_is_never_overwritten(self):
        path = os.path.join(self.folder, "a.css")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("keep me")
        with self.assertRaises(ValueError) as problem:
            F.create_new_file(self.folder, "a.css", self.project, {}, TODAY)
        self.assertIn("exists already", str(problem.exception))
        with open(path, encoding="utf-8") as handle:
            self.assertEqual("keep me", handle.read())

    def test_a_name_with_folders_is_refused(self):
        for name in ("sub/a.php", "..\\a.php", "  ", ".."):
            with self.assertRaises(ValueError):
                F.create_new_file(self.folder, name, self.project, {}, TODAY)

    def test_without_a_template_the_file_is_empty_and_the_message_names_the_setting(self):
        created = F.create_new_file(self.folder, "notes.xyz", self.project, {}, TODAY)
        self.assertEqual("", open(created.path, encoding="utf-8").read())
        self.assertIn("ogmkdev_filetemplate_xyz", created.message)


if __name__ == "__main__":
    unittest.main()
