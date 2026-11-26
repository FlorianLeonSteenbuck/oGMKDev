"""The methods of Python classes in the index: the methods written directly in the body of a top-level class are
member symbols of that class, as the PHP methods are. Functions nested in a method and members of a nested class
are no methods of the outer class."""

import os
import tempfile
import unittest

from ogmkdev import htmldoc as H
from ogmkdev import index as I

SOURCE = (
    "class Animal(Creature):\n"
    '    """A thing that moves."""\n'
    "\n"
    "    def __init__(self, name):\n"
    "        self.name = name\n"
    "\n"
    "    @property\n"
    "    async def speak(self):\n"
    "        def inner():\n"
    "            return 1\n"
    "        return inner()\n"
    "\n"
    "    class Nested:\n"
    "        def hidden(self):\n"
    "            pass\n"
    "\n"
    "\n"
    "def greet(name):\n"
    "    return name\n"
)


class PythonMethodsTest(unittest.TestCase):
    def setUp(self):
        self.symbols = I.extract("/project/animal.py", SOURCE)

    def test_the_methods_of_a_class_are_members_of_it(self):
        methods = [(s.member, s.container, s.line, s.column) for s in self.symbols if s.kind == "method"]
        self.assertEqual(methods, [("__init__", "Animal", 4, 9), ("speak", "Animal", 8, 15)])
        init = next(s for s in self.symbols if s.member == "__init__")
        self.assertEqual(init.name, "Animal::__init__")

    def test_functions_of_a_method_and_members_of_a_nested_class_are_no_methods(self):
        names = {s.member for s in self.symbols if s.kind == "method"}
        self.assertNotIn("inner", names)
        self.assertNotIn("hidden", names)

    def test_top_level_classes_and_functions_are_as_before(self):
        top = [(s.kind, s.name, s.line) for s in self.symbols if s.container is None]
        self.assertEqual(top, [("class", "Animal", 1), ("function", "greet", 18)])


class PythonMethodsExportTest(unittest.TestCase):
    def test_the_html_export_has_a_page_entry_for_each_method(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as out:
            os.makedirs(os.path.join(root, "pkg"))
            with open(os.path.join(root, "pkg", "animal.py"), "w", encoding="utf-8") as handle:
                handle.write(SOURCE)
            H.export(I.ProjectIndex(root), out)
            with open(os.path.join(out, "pages", "pkg", "animal.py.html"), encoding="utf-8") as handle:
                page = handle.read()
        self.assertIn('id="method-Animal--__init__"', page)
        self.assertIn('id="method-Animal--speak"', page)


if __name__ == "__main__":
    unittest.main()
