"""The frame's editor commands against real files: Edit > Organize Imports rewrites the open PHP file and
the Howl buffer reloads it; with autosave on, a modified file is saved on its own.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

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


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@unittest.skipUnless(GTK_AVAILABLE, "needs GTK 4, a display and libhowl.so")
class ProjectCommandTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = self._directory.name
        self.app = Gtk.Application(application_id="org.ogmkdev.test.project", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self._frames = []

    def tearDown(self):
        for frame in self._frames:
            frame.close()  # stops the frame's status poll and autosave
        self._directory.cleanup()

    def _frame(self, files, autosave=None):
        frame = Frame(self.app, self.folder, files, "light", "blend", autosave=autosave)
        self._frames.append(frame)
        frame.present()
        self.assertTrue(_pump_until(lambda: frame.editors.status() is not None, timeout=40))
        return frame

    def _write(self, name, text):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_organize_imports_merges_sorts_and_drops_unused_uses(self):
        path = self._write("svc.php", "<?php\nnamespace App;\nuse Zeta\\B;\nuse Alpha\\A;\nuse Zeta\\B;\n"
                                      "class C { public function f(): A { return new A(); } }\n")
        frame = self._frame([path])
        frame.organize_imports()
        organised = _read(path)
        self.assertIn("use Alpha\\A;", organised)
        self.assertNotIn("Zeta", organised)  # unused, and the duplicate is gone
        self.assertEqual(frame.status.get_text(), "imports organised")
        self.assertTrue(_pump_until(lambda: not frame.editors.status()["modified"], timeout=20))

    def test_organize_imports_says_so_when_nothing_changes(self):
        path = self._write("done.php", "<?php\nnamespace App;\nuse Alpha\\A;\nclass C { public function f(): A {} }\n")
        frame = self._frame([path])
        frame.organize_imports()
        self.assertEqual(frame.status.get_text(), "imports are already organised")

    def test_organize_imports_refuses_other_languages(self):
        path = self._write("notes.txt", "plain\n")
        frame = self._frame([path])
        frame.organize_imports()
        self.assertEqual(frame.status.get_text(), "organise imports works on PHP files")

    def test_autosave_saves_a_modified_file_on_its_own(self):
        path = self._write("auto.txt", "start\n")
        frame = self._frame([path], autosave=True)
        self.assertTrue(frame.autosave_enabled)
        frame.editors.insert_before(path, 1, "typed\n")
        self.assertTrue(_pump_until(lambda: "typed" in _read(path), timeout=12))

    def test_without_autosave_the_file_stays_unsaved(self):
        path = self._write("manual.txt", "start\n")
        frame = self._frame([path], autosave=False)
        frame.editors.insert_before(path, 1, "typed\n")
        self.assertTrue(_pump_until(lambda: frame.editors.status()["modified"], timeout=5))
        self.assertFalse(_pump_until(lambda: "typed" in _read(path), timeout=5))  # modified, not saved


if __name__ == "__main__":
    unittest.main()
