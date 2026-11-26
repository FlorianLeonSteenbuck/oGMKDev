"""The jump from the TODO list and the opening of files in the frame. A folder is never given to Howl; a TODO opens its file at
the line of the TODO, and a TODO whose file is gone reads the list again; Save As writes the text of the focused editor to
the file the frame names, without a prompt in Howl.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, read, write

if GTK_AVAILABLE:
    from gi.repository import Gtk


def _todo_row(frame, path):
    """The row of the TODO list that belongs to ``path``."""
    return next(index for index, row in enumerate(frame.todo_store) if row[4].path == path)


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class JumpTests(FrameTestCase):
    def test_a_folder_is_never_given_to_howl(self):
        folder = os.path.join(self.folder, "Debts")
        os.makedirs(folder)
        frame = self.frame()
        pages = len(frame.area.pages)
        frame.open_file(folder)
        self.assertEqual(len(frame.area.pages), pages)
        self.assertIn("is a folder", frame.status.get_text())

    def test_a_todo_opens_its_file_at_the_line_of_the_todo(self):
        path = write(self.folder, "todo.py", "x = 1\ny = 2\nz = 3\n# TODO: check this\n")
        other = write(self.folder, "other.py", "a = 1\n")
        frame = self.frame(files=[path, other])  # both files are open; the other one has the keyboard focus
        self.assertEqual(frame.editors.status()["path"], other)
        frame.show_todos()
        row = _todo_row(frame, path)
        frame.todo_view.grab_focus()  # a double click in the TODO list leaves the focus in the list
        frame._on_todo_activated(frame.todo_view, Gtk.TreePath.new_from_indices([row]), None)
        status = frame.editors.status()
        self.assertEqual((status["path"], status["line"]), (path, 4))
        # the other file keeps its own editor: the jump must not move its buffer to the TODO file
        self.assertEqual(frame.editors.text(other), "a = 1\n")
        self.assertEqual(frame.area.pages[frame.area.current_page()], path)

    def test_a_todo_of_a_file_that_is_gone_reads_the_list_again(self):
        path = write(self.folder, "gone.py", "# TODO: old\n")
        frame = self.frame()
        frame.show_todos()
        row = _todo_row(frame, path)
        os.remove(path)
        pages = len(frame.area.pages)
        frame._on_todo_activated(frame.todo_view, Gtk.TreePath.new_from_indices([row]), None)
        self.assertEqual(len(frame.area.pages), pages)
        self.assertEqual(len(frame.todo_store), 0)

    def test_save_as_writes_the_text_of_the_focused_editor(self):
        source = write(self.folder, "a.txt", "hello\n")
        frame = self.frame(files=[source])
        target = os.path.join(self.folder, "b.txt")
        self.assertTrue(frame.editors.save_as(target))
        self.assertEqual(read(target), "hello\n")
        self.assertEqual(frame.editors.status()["path"], target)


if __name__ == "__main__":
    unittest.main()
