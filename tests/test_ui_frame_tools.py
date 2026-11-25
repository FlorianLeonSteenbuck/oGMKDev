"""The tools of the frame against real files: the Git panel (stage, diff, commit), Quick Open, Search
Everywhere (files, symbols, actions, settings), implementations and the hierarchy of a class, search in files,
the folder inspection, the index after a save, and go to definition.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; the Git tests need git.
"""

import os
import shutil
import subprocess
import unittest

from ogmkdev import git as git_module
from ogmkdev import search_everywhere as search
from ogmkdev.settings import SettingsStore
from tests.frame_support import FrameTestCase, GTK_AVAILABLE, SKIP_REASON, pump_until, write
from tests.test_index import BASE, CIRCLE, PY, SHAPE, SQUARE, TS


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@unittest.skipUnless(GTK_AVAILABLE and shutil.which("git"), "needs GTK 4, a display and git")
class GitPanelTests(FrameTestCase):
    def setUp(self):
        super().setUp()
        _git(self.folder, "init", "-q")
        _git(self.folder, "config", "user.name", "Test")
        _git(self.folder, "config", "user.email", "test@example.invalid")
        write(self.folder, "a.txt", "one\n")
        _git(self.folder, "add", "a.txt")
        _git(self.folder, "commit", "-q", "-m", "first")
        write(self.folder, "b.txt", "new\n")

    def test_the_panel_lists_new_files_with_their_change(self):
        frame = self.frame()
        frame.refresh_git()
        self.assertEqual({row[2]: row[1] for row in frame.git_store}, {"b.txt": "new"})

    def test_stage_diff_and_commit_through_the_panel(self):
        frame = self.frame()
        frame.refresh_git()
        selection = frame.git_view.get_selection()
        for row in frame.git_store:
            if row[2] == "b.txt":
                selection.select_iter(row.iter)
        frame.git_stage()
        self.assertTrue(any(change.staged and change.path.endswith("b.txt")
                            for change in git_module.status(self.folder)))
        frame._show_git_diff()
        buffer = frame.git_diff.get_buffer()
        self.assertIn("+new", buffer.get_text(*buffer.get_bounds(), True))
        frame.ask_text = lambda _title, _label, on_ok: on_ok("add b")  # the message the user types
        frame.git_commit()
        log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(log.stdout.strip(), "add b")
        self.assertEqual(git_module.status(self.folder), [])

    def test_the_changes_are_coloured_by_their_kind_unless_the_setting_is_off(self):
        frame = self.frame()
        frame.refresh_git()
        colours = {row[2]: row[4] for row in frame.git_store}
        self.assertEqual(colours["b.txt"], "#2EA043")  # a new file: the colour of the added lines
        SettingsStore(self.folder).apply("project", {"ogmkdev_git_colors": "off"})
        frame.refresh_git()
        self.assertEqual({row[2]: row[4] for row in frame.git_store}["b.txt"], None)


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class SearchTests(FrameTestCase):
    def setUp(self):
        super().setUp()
        self.circle = write(self.folder, "src/Circle.php", CIRCLE)
        write(self.folder, "readme.txt", "notes\n")

    def test_quick_open_lists_only_files_and_opens_the_chosen_one(self):
        frame = self.frame()
        ranked = search.rank(frame._search_candidates(), "circ", ("file",))
        self.assertEqual(ranked[0].label, os.path.join("src", "Circle.php"))
        self.assertTrue(all(candidate.category == "file" for candidate in ranked))
        frame.activate_candidate(ranked[0])
        self.wait_for_file(frame, self.circle)

    def test_search_everywhere_finds_actions_and_runs_them(self):
        frame = self.frame()
        best = search.rank(frame._search_candidates(), "show git", ("action",))[0]
        self.assertEqual(best.label, "Tools: Show Git Changes")
        frame.activate_candidate(best)
        self.assertEqual(frame.left.get_current_page(), frame.left.page_num(frame.git_box))

    def test_search_everywhere_finds_symbols_and_opens_their_declaration(self):
        frame = self.frame()
        self.wait_for_index(frame, "App\\Circle")
        best = search.rank(frame._search_candidates(), "Circle", ("symbol",))[0]
        self.assertEqual(best.category, "symbol")
        frame.activate_candidate(best)
        self.wait_for_file(frame, self.circle)

    def test_search_everywhere_offers_the_settings_and_opens_their_group(self):
        frame = self.frame()
        best = search.rank(frame._search_candidates(), "change marks", ("setting",))[0]
        self.assertEqual(best.category, "setting")
        opened = []
        frame._settings_window = lambda group, scope="global": opened.append((group, scope))  # the dialog
        frame.activate_candidate(best)
        self.assertEqual(opened, [(best.target[1], "global")])


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class ProjectToolTests(FrameTestCase):
    def setUp(self):
        super().setUp()
        self.shape = write(self.folder, "src/Shape.php", SHAPE)
        write(self.folder, "src/Geometry/Base.php", BASE)
        self.circle = write(self.folder, "src/Circle.php", CIRCLE)
        self.square = write(self.folder, "src/Square.php", SQUARE)
        write(self.folder, "tools/animal.py", PY)
        write(self.folder, "web/store.ts", TS)

    def _short_names(self, frame):
        """The class names of the Search tab rows (``kind name`` labels), without their namespace."""
        return sorted(row[1].split(" ", 1)[1].rsplit("\\", 1)[-1] for row in frame.search_store)

    def test_find_implementations_lists_the_transitive_implementers(self):
        frame = self.frame([self.shape])
        self.wait_for_index(frame, "App\\Shape", "App\\Geometry\\Base", "App\\Circle", "App\\Square")
        self.wait_for_file(frame, self.shape)
        frame.find_implementations()
        self.assertEqual(self._short_names(frame), ["Base", "Circle", "Square"])
        self.assertEqual(frame.bottom.get_current_page(), frame.bottom.page_num(frame.search_page))
        self.assertEqual(frame.area.current_path(), self.shape)

    def test_the_hierarchy_shows_the_supertypes_and_the_subtypes(self):
        frame = self.frame([self.circle])
        self.wait_for_index(frame, "App\\Circle", "App\\Square")
        self.wait_for_file(frame, self.circle)
        frame.show_hierarchy()
        rows = []
        frame.hierarchy_store.foreach(lambda model, _path, iterator: rows.append((model[iterator][0],
                                                                                    model[iterator][1])))
        self.assertIn(("App\\Square", "subtype"), rows)
        self.assertIn(("App\\Shape", "supertype"), rows)
        self.assertEqual(frame.left.get_current_page(), frame.left.page_num(frame.hierarchy_box))

    def test_search_in_files_and_navigation_by_activation(self):
        frame = self.frame()
        frame.search_in_files("Circle")
        self.assertTrue(len(frame.search_store))
        first = frame.search_store.get_iter_first()
        target = frame.search_store[first][2]
        frame._on_search_activated(frame.search_view, frame.search_store.get_path(first), None)
        self.wait_for_file(frame, target)

    def test_the_inspection_reports_unresolved_supertypes(self):
        frame = self.frame([self.shape])
        self.wait_for_index(frame, "App\\Shape", "App\\Circle")
        frame.inspect_folder()
        messages = [row[1] for row in frame.problems_store]
        self.assertTrue(any("Countable" in message for message in messages))
        self.assertTrue(any("Reader" in message for message in messages))

    def test_a_saved_file_is_indexed_again(self):
        frame = self.frame([self.square])
        self.wait_for_index(frame, "App\\Square")
        write(self.folder, "src/Square.php", "<?php\nnamespace App;\n\nclass Square extends Triangle\n{\n}\n")
        self.assertTrue(pump_until(lambda: {s.short for s in frame.index.supertypes("App\\Square", transitive=False)}
                                   == {"Triangle"}, timeout=30))

    def test_refresh_index_picks_up_a_new_class(self):
        frame = self.frame()
        self.wait_for_index(frame, "App\\Circle")
        write(self.folder, "src/Extra.php", "<?php\nnamespace App;\nclass Extra {}\n")
        frame.refresh_index()
        self.assertTrue(pump_until(lambda: any(s.name == "App\\Extra" for s in frame.index.symbols), timeout=60))

    def test_go_to_definition_jumps_to_the_declaration(self):
        frame = self.frame([self.square])
        self.wait_for_index(frame, "App\\Circle")
        frame.ask_text = lambda _title, _label, on_ok: on_ok("App\\Circle")  # the name the user types
        frame.go_to_definition()
        self.wait_for_file(frame, self.circle)


if __name__ == "__main__":
    unittest.main()
