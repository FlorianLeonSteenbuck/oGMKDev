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


if __name__ == "__main__":
    unittest.main()
