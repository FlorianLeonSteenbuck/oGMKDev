"""GTK smoke tests. They need PyGObject with GTK 3 and a display (run under xvfb-run)."""

import os
import tempfile
import unittest

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: F401
    from ogmkdev.ui.app import EditorWindow
    GTK_AVAILABLE = bool(os.environ.get("DISPLAY"))
except Exception:  # pragma: no cover - missing GTK bindings
    GTK_AVAILABLE = False


@unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
class EditorWindowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        with open(os.path.join(self.dir, ".editorconfig"), "w", encoding="utf-8") as h:
            h.write("root = true\n[*]\nindent_style = space\nindent_size = 2\ntab_width = 8\n"
                    "trim_trailing_whitespace = true\ninsert_final_newline = true\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _file(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as h:
            h.write(text)
        return path

    def test_settings_detection_and_diagnostics_are_shown(self):
        path = self._file("bad.php", "<?php\n$s = <<<HEREDOC\nhello\nENDDOC;\n")
        win = EditorWindow(path)
        try:
            self.assertEqual(win.view.get_tab_width(), 8)
            self.assertEqual(win.view.get_indent_width(), 2)
            self.assertIn("PHP", win.status.get_text())
            self.assertIn("1 error(s)", win.status.get_text())
        finally:
            win.destroy()

    def test_save_applies_editorconfig_line_handling(self):
        path = self._file("ok.txt", "line  \n\n")
        win = EditorWindow(path)
        try:
            win._text()
            win.buffer.set_text("line  \nlast\t")
            win.save()
            with open(path, encoding="utf-8") as h:
                self.assertEqual(h.read(), "line\nlast\n")
        finally:
            win.destroy()

    def test_ctrl_space_expands_variable_template_at_cursor(self):
        path = self._file("q.php", "")
        win = EditorWindow(path)
        try:
            win.buffer.set_text("fo")
            win.buffer.place_cursor(win.buffer.get_end_iter())
            win._complete()
            self.assertIn("foreach ($items as key => value) {", win._text())
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
