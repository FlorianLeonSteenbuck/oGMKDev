"""Editor features: problem underlines with tooltips, colour switches, the Git panel, Quick Open and
Search Everywhere, and the local history as a patch. GUI tests need PyGObject with GTK 3, GtkSourceView 3
and a display (run under xvfb-run); the patch tests need git."""

import os
import shutil
import subprocess
import tempfile
import unittest

from ogmkdev import git as git_module
from ogmkdev import history as history_module
from ogmkdev import search_everywhere as search

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from ogmkdev.ui.app import CHANGE_COLORS, EditorWindow
    from ogmkdev.ui.search_dialog import SearchDialog
    GTK_AVAILABLE = bool(os.environ.get("DISPLAY"))
except Exception:  # pragma: no cover
    GTK_AVAILABLE = False


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class FakeView:
    """Stands in for the text view: hovering always lands on the given iterator."""

    def __init__(self, iterator):
        self.iterator = iterator

    def window_to_buffer_coords(self, _kind, x, y):
        return x, y

    def get_iter_at_location(self, _x, _y):
        return self.iterator


class FakeTooltip:
    text = None

    def set_text(self, text):
        self.text = text


class PatchTests(unittest.TestCase):
    def test_file_patch_marks_missing_final_newline(self):
        patch = history_module.file_patch("one\n", "one\ntwo", "notes.txt")
        self.assertTrue(patch.startswith("diff --git a/notes.txt b/notes.txt\n--- a/notes.txt\n+++ b/notes.txt\n"))
        self.assertIn("\\ No newline at end of file", patch)

    def test_file_patch_of_identical_text_is_empty(self):
        self.assertEqual(history_module.file_patch("same\n", "same\n", "x.txt"), "")

    def test_patch_names_are_relative_to_the_project(self):
        self.assertEqual(history_module.patch_name("/p/src/a.php", "/p"), "src/a.php")
        self.assertEqual(history_module.patch_name("/elsewhere/a.php", "/p"), "a.php")


@unittest.skipUnless(shutil.which("git"), "git is required")
class HistoryPatchTests(unittest.TestCase):
    def test_exported_history_applies_with_git_apply(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as target:
            store = history_module.LocalHistory(os.path.join(root, "history"))
            path = os.path.join(root, "notes.txt")
            store.snapshot(path, "one\n", "opened")
            store.snapshot(path, "one\ntwo\n", "save")
            patch = os.path.join(root, "history.patch")
            store.extract_patch(store.revisions(path), patch, root)
            with open(patch, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("diff --git a/notes.txt b/notes.txt", text)
            self.assertIn("+two", text)
            with open(os.path.join(target, "notes.txt"), "w", encoding="utf-8") as handle:
                handle.write("one\n")
            result = subprocess.run(["git", "apply", "--check", patch], cwd=target, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
class EditorFeatureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        self.bad = os.path.join(self.project, "bad.js")
        with open(self.bad, "w", encoding="utf-8") as handle:
            handle.write("let x = ;\n")
        self.win = EditorWindow(self.bad, project_dir=self.project)

    def tearDown(self):
        self.win.destroy()
        self._tmp.cleanup()

    def test_problem_is_underlined_and_its_message_is_the_tooltip(self):
        page = self.win.page
        self.assertTrue(page.diagnostic_tags)
        problem = page.document.diagnostics[0]
        start = page.buffer.get_iter_at_line(problem.line - 1)
        start.forward_chars(problem.column - 1)
        tooltip = FakeTooltip()
        self.assertTrue(page._on_query_tooltip(FakeView(start), 0, 0, False, tooltip))
        self.assertIn(problem.code, tooltip.text)
        self.assertIn(problem.message, tooltip.text)

    def test_colour_switches_turn_off_underlines_marks_and_syntax_colours(self):
        page = self.win.page
        page.buffer.set_text("let y = 1;\n")
        self.assertTrue(page.change_marks)
        self.win.settings_store.apply("project", {"ogmkdev_diagnostic_marks": "off",
                                                  "ogmkdev_syntax_highlight": "off",
                                                  "ogmkdev_change_marks": "off"})
        self.win._refresh_settings_all()
        self.assertEqual(page.diagnostic_tags, {})
        self.assertEqual(page.change_marks, [])
        self.assertFalse(page.buffer.get_highlight_syntax())

    def test_change_mark_colour_comes_from_settings(self):
        self.win.settings_store.apply("project", {"ogmkdev_change_color_added": "#FF0000"})
        self.win._refresh_settings_all()
        self.assertIsNotNone(self.win.page)
        self.assertNotEqual(CHANGE_COLORS["added"], "#FF0000")


@unittest.skipUnless(GTK_AVAILABLE and shutil.which("git"), "GTK and git are required")
class GitPanelTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.name", "Test")
        _git(self.repo, "config", "user.email", "test@example.invalid")
        with open(os.path.join(self.repo, "a.txt"), "w", encoding="utf-8") as handle:
            handle.write("one\n")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-q", "-m", "first")
        with open(os.path.join(self.repo, "b.txt"), "w", encoding="utf-8") as handle:
            handle.write("new\n")
        self.win = EditorWindow(None, project_dir=self.repo)
        self.win.show_all()
        self.win.refresh_git()

    def tearDown(self):
        self.win.destroy()
        self._tmp.cleanup()

    def select(self, name):
        for row in self.win.git_store:
            if row[2] == name:
                self.win.git_view.get_selection().unselect_all()
                self.win.git_view.get_selection().select_iter(row.iter)
                return
        self.fail(f"{name} is not in the Git panel")

    def test_panel_lists_new_files_and_colours_them(self):
        self.select("b.txt")
        labels = {row[2]: row[1] for row in self.win.git_store}
        self.assertEqual(labels, {"b.txt": "new"})
        self.assertEqual(self.win._node_color(os.path.join(self.repo, "b.txt"), "source"), CHANGE_COLORS["added"])

    def test_stage_diff_and_commit_through_the_panel(self):
        self.select("b.txt")
        self.win.git_stage()
        self.assertTrue(any(c.staged and c.path.endswith("b.txt") for c in git_module.status(self.repo)))
        self.assertIn("+new", self.win.git_diff.get_buffer().get_text(
            *self.win.git_diff.get_buffer().get_bounds(), True))
        self.win._prompt = lambda _title, _label: "add b"
        self.win.git_commit()
        log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(log.stdout.strip(), "add b")
        self.assertEqual(git_module.status(self.repo), [])


@unittest.skipUnless(GTK_AVAILABLE, "PyGObject/GTK 3 and a display are required")
class SearchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name
        os.makedirs(os.path.join(self.project, "src"))
        open(os.path.join(self.project, "src", "Circle.php"), "w").close()
        open(os.path.join(self.project, "readme.txt"), "w").close()
        self.win = EditorWindow(None, project_dir=self.project)
        self.win.show_all()

    def tearDown(self):
        self.win.destroy()
        self._tmp.cleanup()

    def test_quick_open_lists_only_files_and_opens_the_chosen_one(self):
        chosen = []
        dialog = SearchDialog(self.win, "Quick Open", self.win._search_candidates(), ("file",), chosen.append)
        dialog.entry.set_text("circ")
        self.assertEqual(dialog.store[0][1], os.path.join("src", "Circle.php"))
        self.assertTrue(all(row[0] == "file" for row in dialog.store))
        dialog.activate_selected()
        self.assertEqual(chosen[0].target, ("file", os.path.join(self.project, "src", "Circle.php")))
        self.win.activate_candidate(chosen[0])
        self.assertEqual(self.win.page.document.title, "Circle.php")

    def test_search_everywhere_finds_actions_and_runs_them(self):
        candidates = self.win._search_candidates()
        best = search.rank(candidates, "show git", ("action",))[0]
        self.assertEqual(best.label, "Project: Show Git Changes")
        self.win.activate_candidate(best)
        self.assertEqual(self.win.left.get_current_page(), self.win.left_pages["Git"])

    def test_search_everywhere_offers_settings_and_symbols_categories(self):
        candidates = self.win._search_candidates()
        self.assertTrue(search.rank(candidates, "change marks", ("setting",)))
        self.assertTrue(all(c.category == "setting" for c in search.rank(candidates, "", ("setting",))))


if __name__ == "__main__":
    unittest.main()
