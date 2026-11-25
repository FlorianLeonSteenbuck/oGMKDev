"""The editor of the frame: the project tree opens files, new editors and closing a tab, breakpoints in the
gutter, the modified mark, the problems of a file and their hints, and the EditorConfig line handling on save.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import unittest

from ogmkdev.settings import SettingsStore
from tests.frame_support import (FrameTestCase, GTK_AVAILABLE, SKIP_REASON, line_of, pump_until, read, write)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "gdb_target.c")


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class EditorTests(FrameTestCase):
    def _tree_path(self, frame, path):
        found = []
        frame.tree_store.foreach(lambda model, tree_path, iterator:
                                 found.append(tree_path.copy()) if model[iterator][1] == path else None)
        return found[0]

    def test_tree_lists_project_files_and_activation_opens_them(self):
        source = write(self.folder, "gdb_target.c", read(FIXTURE))
        notes = write(self.folder, "notes.txt", "hello\n")
        frame = self.frame([source])
        names = []
        frame.tree_store.foreach(lambda model, _path, iterator: names.append(model[iterator][0]))
        self.assertIn("gdb_target.c", names)
        self.assertIn("notes.txt", names)
        frame._on_row_activated(frame.tree, self._tree_path(frame, notes), None)
        self.wait_for_file(frame, notes)
        # Howl is one process: the buffers of earlier tests may be open too, so only the two files are checked
        self.assertIn(source, frame.editors.files())
        self.assertIn(notes, frame.editors.files())

    def test_a_new_editor_is_untitled_and_closing_the_tab_returns_to_the_file(self):
        source = write(self.folder, "gdb_target.c", read(FIXTURE))
        frame = self.frame([source])
        frame.new_editor()
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("path") == "untitled"),
                        frame.editors.status())
        frame.close_tab()
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("path") == source))

    def test_breakpoint_toggles_gutter_mark_and_session_state(self):
        source = write(self.folder, "gdb_target.c", read(FIXTURE))
        frame = self.frame([source])
        line = line_of(source, "@bp-square")
        frame.open_file(source, line, 1)
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("line") == line))
        frame.editors.command("breakpoint-toggle")
        self.assertTrue(pump_until(lambda: (source, line) in frame.editors.breakpoints()))
        frame.editors.command("breakpoint-toggle")
        self.assertTrue(pump_until(lambda: (source, line) not in frame.editors.breakpoints()))

    def test_unsaved_buffer_is_marked_modified_in_the_status_line(self):
        source = write(self.folder, "gdb_target.c", read(FIXTURE))
        frame = self.frame([source])
        self.focus(frame, source)
        frame.editors.insert_before(source, 1, "int x;\n")
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("modified") is True))
        self.assertTrue(pump_until(lambda: "modified" in frame.position.get_text()), frame.position.get_text())

    def test_a_syntax_error_is_listed_in_the_problems_tab(self):
        path = write(self.folder, "bad.php", "<?php\n$s = <<<HEREDOC\nhello\nENDDOC;\n")
        frame = self.frame([path])
        self.assertTrue(pump_until(lambda: len(frame.problems_store) == 1))
        self.assertEqual(frame.problems_store[0][0], "error")

    def test_a_problem_is_hinted_in_the_editor_with_its_message(self):
        path = write(self.folder, "bad.js", "let x = ;\n")
        frame = self.frame([path])
        hints = []
        frame.editors.hints = lambda hinted_path, rows: hints.append(rows) or True  # the rows Howl shows
        frame.refresh_problems(path)
        self.assertTrue(hints[-1])
        line, _start, _end, _kind, message = hints[-1][0]
        self.assertEqual(line, 1)
        self.assertEqual(message.replace(" [", "  ["), frame.problems_store[0][1])

    def test_switching_the_diagnostic_marks_off_removes_the_hints_but_not_the_problems(self):
        path = write(self.folder, "bad.js", "let x = ;\n")
        frame = self.frame([path])
        hints = []
        frame.editors.hints = lambda hinted_path, rows: hints.append(rows) or True
        SettingsStore(self.folder).apply("project", {"ogmkdev_diagnostic_marks": "off"})
        frame.refresh_problems(path)
        self.assertEqual(hints[-1], [])
        self.assertTrue(frame.problems_store)

    def test_saving_applies_the_editorconfig_line_handling(self):
        write(self.folder, ".editorconfig",
              "root = true\n[*]\ntrim_trailing_whitespace = true\ninsert_final_newline = true\n")
        path = write(self.folder, "ok.txt", "line  \n\n")
        frame = self.frame([path])
        self.focus(frame, path)
        frame.editors.insert_before(path, 1, "top  \n")
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("modified") is True))
        frame.editors.command("save")
        self.assertTrue(pump_until(lambda: read(path) == "top\nline\n", timeout=15), repr(read(path)))
        # the focused buffer reloads the written text, so it is no longer modified
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("modified") is False, timeout=15))


if __name__ == "__main__":
    unittest.main()
