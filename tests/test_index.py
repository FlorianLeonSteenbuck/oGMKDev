import os
import tempfile
import time
import unittest

from ogmkdev import index as I

SHAPE = "<?php\nnamespace App;\n\ninterface Shape extends \\Countable\n{\n    public function area(): float;\n}\n"
BASE = "<?php\nnamespace App\\Geometry;\n\nabstract class Base implements \\App\\Shape\n{\n    use Loggable;\n    public const int SIDES = 0;\n    protected $name = 'x';\n    public function describe(Helper $h): string { return new Helper(); }\n}\n"
CIRCLE = "<?php\nnamespace App;\nuse App\\Geometry\\Base as Parent_;\n\nfinal class Circle extends Parent_ implements Shape\n{\n    public function area(): float { return 3.14; }\n}\n\nfunction make(): Circle { return new Circle(); }\n"
SQUARE = "<?php\nnamespace App;\n\nclass Square extends Circle\n{\n}\n"
PY = "class Animal(Base, metaclass=Meta):\n    pass\n\ndef greet(name):\n    return name\n"
TS = "export interface Store extends Reader<T> {}\nexport class Cache extends Store {\n}\nfunction build() {}\n"


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class IndexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        write(self.root, "src/Shape.php", SHAPE)
        write(self.root, "src/Geometry/Base.php", BASE)
        write(self.root, "src/Circle.php", CIRCLE)
        write(self.root, "src/Square.php", SQUARE)
        write(self.root, "tools/animal.py", PY)
        write(self.root, "web/store.ts", TS)
        write(self.root, "notes.txt", "Circle is mentioned here\n")
        self.index = I.ProjectIndex(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_symbols_resolve_namespaces_and_imports(self):
        circle = self.index.find("App\\Circle")[0]
        self.assertEqual((circle.kind, circle.line), ("class", 5))
        self.assertEqual(circle.supertypes, ("App\\Geometry\\Base", "App\\Shape"))
        base = self.index.find("App\\Geometry\\Base")[0]
        self.assertEqual(base.traits, ("App\\Geometry\\Loggable",))
        self.assertEqual(self.index.find("app\\circle")[0].name, "App\\Circle")  # PHP names are case-insensitive
        members = [s.name for s in self.index.symbols if s.container == "App\\Geometry\\Base"]
        self.assertEqual(members, ["App\\Geometry\\Base::SIDES", "App\\Geometry\\Base::$name",
                                   "App\\Geometry\\Base::describe"])

    def test_members_and_functions_are_indexed(self):
        names = {s.name for s in self.index.symbols}
        self.assertIn("App\\Circle::area", names)
        self.assertIn("App\\make", names)
        self.assertIn("App\\Geometry\\Base::SIDES", names)
        self.assertIn("App\\Geometry\\Base::$name", names)
        self.assertIn("greet", names)

    def test_subtypes_and_implementations_are_transitive(self):
        subs = {s.short for s in self.index.subtypes("App\\Shape")}
        self.assertEqual(subs, {"Base", "Circle", "Square"})
        self.assertEqual({s.short for s in self.index.implementations("App\\Circle")}, {"Square"})
        # external types (Countable, Loggable) appear as unresolved supertypes
        self.assertEqual({s.short for s in self.index.supertypes("App\\Square")},
                         {"Circle", "Base", "Shape", "Countable", "Loggable"})

    def test_hierarchy_tree_goes_up_and_down(self):
        tree = self.index.hierarchy("App\\Circle")
        self.assertEqual({n["name"] for n in tree["up"]}, {"App\\Geometry\\Base", "App\\Shape"})
        self.assertEqual([n["name"] for n in tree["down"]], ["App\\Square"])

    def test_dependencies_include_types_and_new(self):
        deps = self.index.dependencies("App\\Geometry\\Base")
        self.assertIn("App\\Geometry\\Helper", deps)
        self.assertIn("App\\Shape", deps)

    def test_python_and_typescript_hierarchies(self):
        self.assertEqual({s.name for s in self.index.subtypes("Base")}, {"Animal"})
        self.assertEqual({s.name for s in self.index.subtypes("Store")}, {"Cache"})
        self.assertIn("build", {s.name for s in self.index.find("build")})

    def test_unresolved_supertypes_are_inspections(self):
        findings = [i for i in self.index.inspect() if i.code == "unresolved-supertype"]
        messages = {i.message for i in findings}
        self.assertIn("Shape extends or implements unknown type Countable", messages)
        self.assertTrue(any("Reader" in m for m in messages))
        self.assertFalse(any("Meta" in m for m in messages))  # metaclass=Meta is a keyword argument

    def test_find_in_files_searches_every_text_file(self):
        hits = self.index.find_in_files("Circle")
        self.assertEqual({os.path.basename(h.file) for h in hits}, {"Circle.php", "Square.php", "notes.txt"})
        self.assertTrue(all(h.column >= 1 for h in hits))
        only_php = self.index.find_in_files("class", glob="*.php")
        self.assertTrue(all(h.file.endswith(".php") for h in only_php))
        regex_hits = self.index.find_in_files(r"function\s+\w+\(", regex=True)
        self.assertTrue(any(h.file.endswith("Circle.php") for h in regex_hits))

    def test_invalidation_after_edit_and_removal(self):
        path = os.path.join(self.root, "src/Square.php")
        time.sleep(0.01)
        write(self.root, "src/Square.php", "<?php\nnamespace App;\n\nclass Square extends Triangle\n{\n}\n")
        counts = self.index.refresh()
        self.assertEqual(counts["changed"], 1)
        self.assertEqual({s.short for s in self.index.supertypes("App\\Square", transitive=False)}, {"Triangle"})
        os.remove(path)
        self.assertEqual(self.index.refresh()["removed"], 1)
        self.assertEqual(self.index.find("App\\Square"), [])

    def test_invalidate_one_file_after_save(self):
        path = write(self.root, "src/New.php", "<?php\nnamespace App;\nclass Fresh extends Circle {}\n")
        self.assertTrue(self.index.invalidate(path))
        self.assertEqual({s.short for s in self.index.subtypes("App\\Circle")}, {"Square", "Fresh"})

    def test_cache_round_trip_keeps_unchanged_files(self):
        cache = os.path.join(self.root, "cache", "index.json")
        self.index.save_cache(cache)
        again = I.ProjectIndex(self.root, cache_path=cache)
        self.assertEqual(len(again.files), len(self.index.files))
        self.assertEqual({s.short for s in again.subtypes("App\\Shape")}, {"Base", "Circle", "Square"})
        self.assertEqual(again.refresh(), {"added": 0, "changed": 0, "removed": 0})


if __name__ == "__main__":
    unittest.main()
