"""Split panes, local history on save, autosave and the startup options (GTK, under Xvfb)."""

import os
import tempfile
import unittest

from ogmkdev.history import LocalHistory

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from ogmkdev.ui.app import EditorWindow
    GTK_AVAILABLE = bool(os.environ.get("DISPLAY"))
except Exception:  # pragma: no cover
    GTK_AVAILABLE = False


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


@unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
class PaneTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.a = write(self.root, "a.txt", "one\ntwo\n")
        self.b = write(self.root, "b.txt", "bee\n")
        previous = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.root, "data")  # the window's history lives here
        try:
            self.win = EditorWindow(self.a, project_dir=self.root)
        finally:
            if previous is None:
                os.environ.pop("XDG_DATA_HOME", None)
            else:
                os.environ["XDG_DATA_HOME"] = previous
        self.win.index.cache_path = None
        self.win.show_all()

    def tearDown(self):
        self.win.destroy()
        self._tmp.cleanup()

    def test_split_right_down_and_grids(self):
        self.assertEqual(len(self.win.notebooks), 1)
        self.win.split_right()
        self.assertEqual(len(self.win.notebooks), 2)
        self.win.split_down()
        self.assertEqual(len(self.win.notebooks), 3)
        self.win.close_active_pane()
        self.assertEqual(len(self.win.notebooks), 2)
        self.win.close_active_pane()
        self.assertEqual(len(self.win.notebooks), 1)
        self.win.split_four()
        self.assertEqual(len(self.win.notebooks), 4)
        self.win.close_active_pane()
        self.win.close_active_pane()
        self.win.close_active_pane()
        self.assertEqual(len(self.win.notebooks), 1)

    def test_six_panes_and_pages_keep_their_pane(self):
        self.win.split_six()
        self.assertEqual(len(self.win.notebooks), 6)
        page = self.win.page
        self.assertIn(page.notebook, self.win.notebooks)
        self.assertIs(page.notebook.get_nth_page(page.notebook.get_current_page()), page.scroller)

    def test_closing_a_pane_moves_its_tabs_to_the_neighbour(self):
        self.win.split_right()
        self.win.open_path(self.b)
        right = self.win.active_notebook
        self.assertIs(self.win.page.notebook, right)
        self.win.close_pane(right)
        self.assertEqual(len(self.win.notebooks), 1)
        self.assertEqual({p.document.title for p in self.win.pages}, {"a.txt", "b.txt"})
        self.assertIs(self.win.pages[1].notebook, self.win.notebooks[0])

    def test_the_last_pane_is_kept(self):
        self.win.close_active_pane()
        self.assertEqual(len(self.win.notebooks), 1)
        self.assertEqual(len(self.win.pages), 1)

    def test_save_keeps_a_local_history_outside_the_project(self):
        self.win.buffer.set_text("one\nTWO\n")
        self.win.save_current()
        self.win.buffer.set_text("one\nTWO\nthree\n")
        self.win.save_current()
        revisions = self.win.history.revisions(self.a)
        self.assertEqual([r.label for r in revisions], ["save", "save", "opened"])
        self.assertEqual(self.win.history.content(revisions[2]), "one\ntwo\n")  # the state at opening
        patch = self.win.history.patch_set(revisions)
        self.assertIn("+TWO", patch)
        self.assertIn("+three", patch)

    def test_autosave_writes_the_document_after_a_change(self):
        self.win.autosave = True
        self.win.buffer.set_text("auto\n")
        self.assertTrue(self.win.page.dirty)
        self.win._autosave(self.win.page)
        with open(self.a, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "auto\n")
        self.assertFalse(self.win.page.dirty)
        self.assertEqual(self.win.history.revisions(self.a)[0].label, "autosave")

    def test_startup_options(self):
        win = EditorWindow(self.b, project_dir=self.root, autosave=True)
        try:
            self.assertTrue(win.autosave)
        finally:
            win.destroy()
        win = EditorWindow(self.b, project_dir=self.root, autosave=False)
        try:
            self.assertFalse(win.autosave)
        finally:
            win.destroy()

    def test_clear_index_option_removes_the_cache(self):
        cache = self.win._cache_path()
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as handle:
            handle.write("{}")
        win = EditorWindow(self.b, project_dir=self.root, clear_index=True)
        try:
            self.assertFalse(os.path.exists(cache))
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main()
