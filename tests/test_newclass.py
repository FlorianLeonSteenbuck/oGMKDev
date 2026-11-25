import json
import os
import tempfile
import unittest

from ogmkdev import newclass as N


class NamespaceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        self.src_shop = os.path.join(self.project, "src", "Shop")
        self.plain = os.path.join(self.project, "my-shop", "cart")
        os.makedirs(self.src_shop)
        os.makedirs(self.plain)
        with open(os.path.join(self.project, "composer.json"), "w", encoding="utf-8") as handle:
            json.dump({"autoload": {"psr-4": {"App\\": "src/"}}}, handle)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_psr4_mapping_of_composer_gives_the_namespace(self):
        self.assertEqual("App\\Shop", N.default_namespace(self.src_shop, self.project))

    def test_without_a_mapping_the_folder_path_gives_the_namespace(self):
        os.remove(os.path.join(self.project, "composer.json"))
        self.assertEqual("MyShop\\Cart", N.default_namespace(self.plain, self.project))


class CreateClassTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        self.folder = os.path.join(self.project, "src", "Shop")
        os.makedirs(self.folder)
        with open(os.path.join(self.project, "composer.json"), "w", encoding="utf-8") as handle:
            json.dump({"autoload": {"psr-4": {"App\\": "src/"}}}, handle)

    def tearDown(self):
        self._tmp.cleanup()

    def read(self, created):
        with open(created.path, encoding="utf-8") as handle:
            return handle.read()

    def test_a_php_class_gets_the_namespace_the_uses_and_the_cursor_in_its_body(self):
        created = N.create_class_file(self.folder, "CartItem.php", self.project, "",
                                      ["Shop\\Product", "Psr\\Log\\LoggerInterface"])
        text = self.read(created)
        self.assertIn("namespace App\\Shop;", text)
        self.assertIn("use Shop\\Product;", text)
        self.assertIn("use Psr\\Log\\LoggerInterface;", text)
        self.assertIn("class CartItem\n{\n    \n}\n", text)
        self.assertNotIn("$0", text)
        self.assertEqual("    ", text.splitlines()[created.line - 1])
        self.assertEqual(5, created.column)

    def test_an_explicit_namespace_and_none_at_all(self):
        created = N.create_class_file(self.folder, "A.php", self.project, "Shop\\Model", [])
        self.assertIn("namespace Shop\\Model;", self.read(created))
        created = N.create_class_file(self.folder, "B.php", self.project, "-", [])
        self.assertNotIn("namespace", self.read(created))

    def test_typescript_imports_name_the_symbol_after_the_module(self):
        created = N.create_class_file(self.folder, "Cart.ts", self.project, "", ["./cart-item"])
        text = self.read(created)
        self.assertIn("import { CartItem } from './cart-item';", text)
        self.assertIn("export class Cart {", text)

    def test_python_class_name_is_the_file_name_in_pascal_case(self):
        created = N.create_class_file(self.folder, "cart_item.py", self.project, "", ["pathlib.Path", "os"])
        text = self.read(created)
        self.assertIn("from pathlib import Path", text)
        self.assertIn("import os", text)
        self.assertIn("class CartItem:", text)

    def test_invalid_names_languages_and_imports_are_refused(self):
        for name in ("my-class.php", "1Cart.php", "Cart.rb", "sub/Cart.php", ""):
            with self.assertRaises(N.ClassError):
                N.create_class_file(self.folder, name, self.project, "", [])
        with self.assertRaises(N.ClassError):
            N.create_class_file(self.folder, "Cart.php", self.project, "", ["Shop\\ Product"])

    def test_an_existing_file_is_never_overwritten(self):
        path = os.path.join(self.folder, "Keep.php")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("keep")
        with self.assertRaises(ValueError) as problem:
            N.create_class_file(self.folder, "Keep.php", self.project, "", [])
        self.assertIn("exists already", str(problem.exception))
        with open(path, encoding="utf-8") as handle:
            self.assertEqual("keep", handle.read())


if __name__ == "__main__":
    unittest.main()
