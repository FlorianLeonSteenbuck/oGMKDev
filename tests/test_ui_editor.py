"""Editor window tests: tabs, tree, breakpoints, and an end-to-end GDB session.

They need PyGObject with GTK 3, GtkSourceView 3 and a display (run under xvfb-run).
The end-to-end test also needs gdb and gcc.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "gdb_target.c")

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from ogmkdev import runconfig
    from ogmkdev.ui.app import BREAKPOINT_CATEGORY, EditorWindow
    GTK_AVAILABLE = bool(os.environ.get("DISPLAY"))
except Exception:  # pragma: no cover
    GTK_AVAILABLE = False


def pump_until(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if predicate():
            return True
        time.sleep(0.02)
    return False


def line_of(path, marker):
    with open(path, encoding="utf-8") as handle:
        for number, text in enumerate(handle, 1):
            if marker in text:
                return number
    raise AssertionError(marker)


def place_cursor_on(win, line):
    buffer = win.buffer
    buffer.place_cursor(buffer.get_iter_at_line(line - 1))


@unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
class EditorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        self.source = os.path.join(self.project, "gdb_target.c")
        shutil.copy(FIXTURE, self.source)
        self.win = EditorWindow(self.source, project_dir=self.project)

    def tearDown(self):
        self.win.destroy()
        self._tmp.cleanup()

    def test_tree_lists_project_files_and_activation_opens_them(self):
        names = []
        model = self.win.tree_store
        model.foreach(lambda m, p, it: names.append(m[it][0]))
        self.assertIn("gdb_target.c", names)
        other = os.path.join(self.project, "notes.txt")
        with open(other, "w", encoding="utf-8") as handle:
            handle.write("hello\n")
        self.win.open_path(other)
        self.assertEqual(self.win.page.document.title, "notes.txt")
        self.assertEqual(len(self.win.pages), 2)

    def test_tabs_new_and_close(self):
        self.win.new_document()
        self.assertEqual(self.win.page.document.title, "untitled")
        self.win.close_page()
        self.assertEqual(self.win.page.document.title, "gdb_target.c")

    def test_breakpoint_toggles_gutter_mark_and_session_state(self):
        line = line_of(self.source, "@bp-square")
        place_cursor_on(self.win, line)
        self.win.toggle_breakpoint()
        self.assertEqual(self.win.breakpoints[self.source], {line})
        marks = self.win.buffer.get_source_marks_at_line(line - 1, BREAKPOINT_CATEGORY)
        self.assertEqual(len(marks), 1)
        self.win.toggle_breakpoint()
        self.assertEqual(self.win.breakpoints[self.source], set())
        self.assertEqual(self.win.buffer.get_source_marks_at_line(line - 1, BREAKPOINT_CATEGORY), [])

    def test_find_next_selects_match(self):
        self.win.find_entry.set_text("return result")
        self.win.find_next()
        start, end = self.win.buffer.get_selection_bounds()
        self.assertEqual(self.win.buffer.get_text(start, end, True), "return result")

    def test_unsaved_buffer_is_marked_dirty_in_tab_and_status(self):
        self.win.buffer.set_text("int x;\n")
        self.assertTrue(self.win.page.dirty)
        self.assertIn("gdb_target.c *", self.win.page.tab_label.get_text())


@unittest.skipUnless(GTK_AVAILABLE and shutil.which("gdb") and shutil.which("gcc"),
                     "GTK, gdb and gcc are required")
class DebugEndToEndTests(unittest.TestCase):
    def test_breakpoint_stop_watch_continue_to_exit(self):
        with tempfile.TemporaryDirectory() as project:
            source = os.path.join(project, "gdb_target.c")
            shutil.copy(FIXTURE, source)
            binary = os.path.join(project, "target")
            subprocess.run(["gcc", "-g", "-O0", "-o", binary, source], check=True)
            os.makedirs(os.path.join(project, ".run"))
            config = runconfig.RunConfiguration(name="Debug target", type=runconfig.GDB_TYPE,
                                                factory="ogmkdev gdb")
            config.set_option("PROGRAM", binary)
            config.set_option("WORKING_DIRECTORY", project)
            runconfig.save(config, os.path.join(project, ".run", "debug-target.run.xml"))

            win = EditorWindow(source, project_dir=project)
            try:
                line = line_of(source, "@bp-square")
                place_cursor_on(win, line)
                win.toggle_breakpoint()
                win.debug_selected()
                self.assertTrue(pump_until(lambda: "stopped (breakpoint)" in win.status.get_text()),
                                win.status.get_text())
                self.assertIn(f"gdb_target.c:{line}", win.status.get_text())

                win.add_watch("v")
                self.assertTrue(pump_until(lambda: "v = 1" in win.watch_label.get_text()),
                                win.watch_label.get_text())

                # remove the breakpoint from the editor and the session, then run to the end
                place_cursor_on(win, line)
                win.toggle_breakpoint()
                time.sleep(0.5)
                win.debug_op("run")
                self.assertTrue(pump_until(lambda: "program exited" in win.status.get_text()),
                                win.status.get_text())
                self.assertIn("total=14", win.console_text())
            finally:
                win.destroy()


if __name__ == "__main__":
    unittest.main()
