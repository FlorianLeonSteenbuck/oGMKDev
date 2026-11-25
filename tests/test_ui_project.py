"""Project tools in the editor: implementations, hierarchy, search in files, inspections, index on save."""

import os
import tempfile
import unittest

from tests.test_index import BASE, CIRCLE, PY, SHAPE, SQUARE, TS, write

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from ogmkdev.ui.app import EditorWindow
    GTK_AVAILABLE = bool(os.environ.get("DISPLAY"))
except Exception:  # pragma: no cover
    GTK_AVAILABLE = False


def place(win, line, column):
    buffer = win.buffer
    buffer.place_cursor(buffer.get_iter_at_line_offset(line - 1, column - 1))


@unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
class ProjectToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        write(self.root, "src/Shape.php", SHAPE)
        write(self.root, "src/Geometry/Base.php", BASE)
        write(self.root, "src/Circle.php", CIRCLE)
        write(self.root, "src/Square.php", SQUARE)
        write(self.root, "tools/animal.py", PY)
        write(self.root, "web/store.ts", TS)
        self.win = EditorWindow(os.path.join(self.root, "src/Shape.php"), project_dir=self.root)
        self.win.index.cache_path = None
        self.win.show_all()

    def tearDown(self):
        self.win.destroy()
        self._tmp.cleanup()

    def test_find_implementations_lists_transitive_implementers(self):
        place(self.win, 4, 12)  # on "Shape" in "interface Shape extends ..."
        self.win.find_implementations()
        names = [row[0] for row in self.win.search_view.store]
        self.assertEqual(sorted(names), ["Base", "Circle", "Square"])
        self.assertEqual(self.win.bottom.get_current_page(), self.win.bottom_pages["Search"])

    def test_hierarchy_panel_shows_up_and_down(self):
        write(self.root, "src/Other.php", "<?php\nnamespace App;\nclass Circle2 {}\n")
        self.win.open_path(os.path.join(self.root, "src/Circle.php"))
        place(self.win, 5, 14)  # on "Circle"
        self.win.show_hierarchy()
        labels = []
        self.win.hierarchy_view.store.foreach(lambda m, p, it: labels.append(m[it][0]))
        self.assertIn("supertypes", labels)
        self.assertIn("subtypes", labels)
        self.assertIn("App\\Square", labels)
        self.assertEqual(self.win.left.get_current_page(), self.win.left_pages["Hierarchy"])

    def test_search_in_files_and_navigation_by_activation(self):
        self.win.search_in_files("Circle")
        rows = list(self.win.search_view.store)
        self.assertTrue(rows)
        target = rows[0]
        self.win.navigate(target[2], target[3], target[4])
        self.assertEqual(self.win.page.document.path, os.path.abspath(target[2]))

    def test_inspection_reports_unresolved_supertypes(self):
        self.win.inspect_project()
        messages = [row[0] for row in self.win.problems_view.store]
        self.assertTrue(any("Countable" in m for m in messages))
        self.assertTrue(any("Reader" in m for m in messages))

    def test_saving_invalidates_the_index(self):
        page = self.win.open_path(os.path.join(self.root, "src/Square.php"))
        page.buffer.set_text("<?php\nnamespace App;\n\nclass Square extends Triangle\n{\n}\n")
        self.win.save_current()
        supers = {s.short for s in self.win.index.supertypes("App\\Square", transitive=False)}
        self.assertEqual(supers, {"Triangle"})

    def test_refresh_index_reports_changes(self):
        write(self.root, "src/Extra.php", "<?php\nnamespace App;\nclass Extra {}\n")
        self.win.refresh_index()
        self.assertIn("1 added", self.win.status.get_text())


if __name__ == "__main__":
    unittest.main()


class DiagramTests(unittest.TestCase):
    def test_layout_puts_supertypes_left_and_subtypes_right(self):
        from ogmkdev import diagram
        from ogmkdev.index import Symbol

        class_symbol = Symbol("App\\Circle", "class", "/p/Circle.php", 5, 1)
        tree = {"name": "App\\Circle", "symbol": class_symbol,
                "up": [{"name": "App\\Shape", "symbol": None, "children": []}],
                "down": [{"name": "App\\Square", "symbol": Symbol("App\\Square", "class", "/p/Square.php", 3, 1),
                          "children": []}]}
        boxes, edges, (width, height) = diagram.layout(tree)
        by_name = {b.name: b for b in boxes}
        self.assertLess(by_name["App\\Shape"].x, by_name["App\\Circle"].x)
        self.assertLess(by_name["App\\Circle"].x, by_name["App\\Square"].x)
        self.assertEqual(by_name["App\\Shape"].kind, "external")
        self.assertIn(diagram.Edge("App\\Circle", "App\\Shape"), edges)
        self.assertIn(diagram.Edge("App\\Square", "App\\Circle"), edges)
        self.assertIsNotNone(diagram.box_at(boxes, by_name["App\\Circle"].x + 1, by_name["App\\Circle"].y + 1))

    @unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
    def test_hierarchy_panel_has_dependencies_and_diagram(self):
        root = tempfile.mkdtemp()
        try:
            write(root, "src/Shape.php", SHAPE)
            write(root, "src/Circle.php", CIRCLE)
            win = EditorWindow(os.path.join(root, "src/Circle.php"), project_dir=root)
            win.show_all()
            place(win, 5, 14)
            win.show_hierarchy()
            labels = []
            win.hierarchy_view.store.foreach(lambda m, p, it: labels.append(m[it][0]))
            self.assertIn("dependencies", labels)
            self.assertEqual(len(win.diagram_view.boxes), len({b.name for b in win.diagram_view.boxes}))
            self.assertTrue(any(b.name == "App\\Shape" for b in win.diagram_view.boxes))
            win.destroy()
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
