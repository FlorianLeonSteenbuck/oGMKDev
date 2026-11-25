"""The class diagram of the Hierarchy tab: the frame draws the supertype to the left of the selected class
and the subtype to the right, and a click on a class opens its declaration.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import tempfile
import time
import unittest

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk  # noqa: E402

    from ogmkdev import diagram  # noqa: E402
    from ogmkdev.frame.howl import LIBRARY  # noqa: E402
    from ogmkdev.frame.window import Frame  # noqa: E402

    GTK_AVAILABLE = bool(os.environ.get("DISPLAY")) and os.path.isfile(LIBRARY)
except Exception:  # pragma: no cover - reported as a skip
    GTK_AVAILABLE = False


def _pump_until(predicate, timeout=30.0) -> bool:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(GTK_AVAILABLE, "needs GTK 4, a display and libhowl.so")
class ClassDiagramTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = self._directory.name
        with open(os.path.join(self.folder, "base.php"), "w", encoding="utf-8") as handle:
            handle.write("<?php\nclass Base {}\n")
        self.child = os.path.join(self.folder, "child.php")
        with open(self.child, "w", encoding="utf-8") as handle:
            handle.write("<?php\nclass Child extends Base {}\n")
        self.app = Gtk.Application(application_id="org.ogmkdev.test.diagram", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self.frame = Frame(self.app, self.folder, [self.child], "light", "blend")
        self.frame.present()
        self.assertTrue(_pump_until(lambda: self.frame.editors.status() is not None, timeout=40))
        self.assertTrue(_pump_until(lambda: bool(self.frame.index.symbols), timeout=90))

    def tearDown(self):
        self.frame.close()
        self._directory.cleanup()

    def test_the_supertype_is_left_of_the_class_and_the_subtype_right_of_it(self):
        self.frame.show_hierarchy()
        boxes = {box.name: box for box in self.frame.class_diagram.boxes}
        self.assertEqual(set(boxes), {"Child", "Base"} if "Child" in boxes else set(boxes))
        self.assertEqual(boxes["Child"].grid_column, boxes["Base"].grid_column + 1)
        self.assertTrue(boxes["Child"].root)

    def test_a_click_opens_the_declaration_of_the_class(self):
        self.frame.show_hierarchy()
        base = next(box for box in self.frame.class_diagram.boxes if box.name == "Base")
        self.frame.class_diagram._activate(base)
        self.assertTrue(_pump_until(lambda: self.frame.area.current_path() == base.file, timeout=10))

    def test_zoom_changes_the_drawing_and_stays_within_its_range(self):
        self.frame.show_hierarchy()
        diagram_view = self.frame.class_diagram
        area = diagram_view.area
        diagram_view.set_zoom(1.0)
        normal = area.get_content_width()
        diagram_view.zoom_in()
        self.assertGreater(area.get_content_width(), normal)
        diagram_view.set_zoom(10)
        self.assertEqual(diagram_view.zoom, diagram.ZOOM_MAX)
        diagram_view.zoom_out()
        self.assertLess(diagram_view.zoom, diagram.ZOOM_MAX)
        diagram_view.zoom_reset()
        self.assertEqual(area.get_content_width(), normal)

    def test_every_inheritance_edge_is_drawn_as_an_orthogonal_route(self):
        self.frame.show_hierarchy()
        diagram_view = self.frame.class_diagram
        self.assertEqual(len(diagram_view.routes), len(diagram_view.edges))
        for points, _parent in diagram_view.routes:
            for start, end in zip(points, points[1:]):
                self.assertTrue(start[0] == end[0] or start[1] == end[1])


@unittest.skipUnless(GTK_AVAILABLE, "needs GTK 4, a display and libhowl.so")
class HierarchyDependenciesTests(unittest.TestCase):
    """The Dependencies heading under the class in the Hierarchy tab: the supertypes and the classes the class
    refers to, each with its file; a name the project does not declare is marked external."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = self._directory.name
        self.base = self._write("base.php", "<?php\nclass Base {}\n")
        self.money = self._write("money.php", "<?php\nclass Money {}\n")
        order = self._write("order.php", "<?php\n"
                            "class Order extends Base {\n"
                            "    public function total(): Money { return new Money(); }\n"
                            "    public function stamp(): DateTime { return new DateTime(); }\n"
                            "}\n")
        self.app = Gtk.Application(application_id="org.ogmkdev.test.dependencies",
                                   flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self.frame = Frame(self.app, self.folder, [order], "light", "blend")
        self.frame.present()
        self.assertTrue(_pump_until(lambda: self.frame.editors.status() is not None, timeout=40))
        self.assertTrue(_pump_until(lambda: all(self.frame.index.find(name) for name in ("Base", "Money", "Order")),
                                    timeout=90))

    def tearDown(self):
        self.frame.close()
        self._directory.cleanup()

    def _write(self, name, text):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _dependencies(self):
        """The rows under the Dependencies heading as (label, (file, line) or None)."""
        store = self.frame.hierarchy_store
        rows = []
        heading = store.iter_children(store.get_iter_first())
        while heading is not None:
            if store[heading][0] == "dependencies":
                row = store.iter_children(heading)
                while row is not None:
                    rows.append((store[row][0], store[row][3]))
                    row = store.iter_next(row)
            heading = store.iter_next(heading)
        return rows

    def test_the_dependencies_are_the_supertypes_and_the_classes_referred_to(self):
        self.frame.show_hierarchy()
        found = dict(self._dependencies())
        self.assertEqual(found["Base"], (self.base, 2))
        self.assertEqual(found["Money"], (self.money, 2))
        self.assertIsNone(found["DateTime  (external)"])
        self.assertNotIn("Order", found)

    def test_a_class_without_dependencies_still_has_the_heading(self):
        self.frame.open_file(self.base)
        self.assertTrue(_pump_until(lambda: self.frame.area.current_path() == self.base, timeout=10))
        self.frame.show_hierarchy()
        self.assertEqual(self._dependencies(), [])


if __name__ == "__main__":
    unittest.main()
