"""The settings dialog: the category tree and the search, the controls of the types, a value that is refused with its
reason, the reset to the default, and saving. The dialog writes only to the scope it is given. These tests use a
project folder and a global file in a temporary folder, never the user's own settings."""

import os
import tempfile
import unittest

from ogmkdev.settings import PHP_VERSIONS, SettingsStore
from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, pump_until

if GTK_AVAILABLE:
    from gi.repository import Gtk

    from ogmkdev.frame.settings_dialog import SettingsDialog, colour_of

TODO_DEFAULT = "FIXME:1,XXX:2,HACK:2,TODO:3,NOTE:5"


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class SettingsDialogTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.project = os.path.join(self._directory.name, "project")
        os.makedirs(self.project)
        self.global_file = os.path.join(self._directory.name, "global", ".editorconfig")
        self.store = SettingsStore(self.project, global_path=self.global_file)
        self.parent = Gtk.Window()
        self.addCleanup(self.parent.destroy)
        self.saved = []

    def tearDown(self):
        self._directory.cleanup()

    def open_dialog(self, scope="project", select=""):
        dialog = SettingsDialog(self.parent, self.store, scope, select, self.saved.append)
        self.addCleanup(dialog.destroy)
        return dialog

    @staticmethod
    def pairs_rows(dialog):
        """The rows of the TODO keyword editor, each as (keyword entry, priority spin, remove button, row box)."""
        box = dialog._rows["ogmkdev_todo_keywords"][1]
        rows = []
        line = box.get_first_child().get_first_child()
        while line is not None:
            entry = line.get_first_child()
            spin = entry.get_next_sibling()
            remove = spin.get_next_sibling()
            rows.append((entry, spin, remove, line))
            line = line.get_next_sibling()
        return rows

    def test_the_categories_form_a_tree_as_deep_as_their_paths(self):
        dialog = self.open_dialog()
        paths = []
        dialog.tree_store.foreach(lambda model, _path, iterator: paths.append(model[iterator][1]) or False)
        self.assertIn("Editor / Indentation", paths)
        self.assertIn("Diagnostics / PHP", paths)
        self.assertIn("Colors / Changes", paths)

    def test_a_category_shows_its_own_settings_and_those_of_its_sub_categories(self):
        dialog = self.open_dialog(select="Diagnostics")
        keys = dialog.shown_keys()
        self.assertIn("ogmkdev_diagnostic_php_function", keys)
        self.assertIn("ogmkdev_diagnostic_css_braces", keys)
        self.assertNotIn("indent_size", keys)
        dialog.select_category("Diagnostics / PHP")
        self.assertEqual(sorted(dialog.shown_keys()),
                         ["ogmkdev_diagnostic_php_function", "ogmkdev_diagnostic_php_partial_application"])

    def test_the_search_finds_settings_in_every_category(self):
        dialog = self.open_dialog()
        dialog.search.set_text("php")
        # the search entry searches a moment after the text changed, so the main loop runs until the results are there
        self.assertTrue(pump_until(lambda: "ogmkdev_diagnostic_php_function" in dialog.shown_keys(), timeout=10))
        keys = dialog.shown_keys()
        self.assertIn("ogmkdev_dialect", keys)
        self.assertNotIn("indent_size", keys)

    def test_a_value_that_is_not_valid_is_refused_with_its_reason_and_the_old_value_stays(self):
        dialog = self.open_dialog(select="TODO")
        keyword = self.pairs_rows(dialog)[0][0]
        keyword.set_text("1X")
        self.assertIn("KEYWORD:PRIORITY", dialog.message.get_text())
        self.assertEqual(dialog.values()["ogmkdev_todo_keywords"], TODO_DEFAULT)
        keyword.set_text("BUGS")
        self.assertEqual(dialog.message.get_text(), "")
        self.assertEqual(dialog.values()["ogmkdev_todo_keywords"], "BUGS:1,XXX:2,HACK:2,TODO:3,NOTE:5")

    def test_a_keyword_is_added_and_removed_with_its_row(self):
        dialog = self.open_dialog(select="TODO")
        self.assertEqual(len(self.pairs_rows(dialog)), 5)
        dialog._rows["ogmkdev_todo_keywords"][1].get_last_child().emit("clicked")  # "Add a keyword"
        rows = self.pairs_rows(dialog)
        self.assertEqual(len(rows), 6)
        rows[-1][0].set_text("BUG")
        self.assertEqual(dialog.values()["ogmkdev_todo_keywords"], TODO_DEFAULT + ",BUG:1")
        rows[0][2].emit("clicked")  # removes FIXME
        self.assertEqual(dialog.values()["ogmkdev_todo_keywords"], "XXX:2,HACK:2,TODO:3,NOTE:5,BUG:1")

    def test_a_colour_is_chosen_with_the_picker_and_kept_in_capitals(self):
        dialog = self.open_dialog(select="Colors / Changes")
        dialog._rows["ogmkdev_change_color_added"][1].set_rgba(colour_of("#112233"))
        self.assertEqual(dialog.values()["ogmkdev_change_color_added"], "#112233")

    def test_reset_puts_back_the_default_and_rebuilds_the_page(self):
        dialog = self.open_dialog(select="Editor / Indentation")
        dialog._rows["indent_size"][1].set_value(2)
        self.assertEqual(dialog.values()["indent_size"], "2")
        dialog._rows["indent_size"][2].emit("clicked")
        self.assertEqual(dialog.values()["indent_size"], "4")
        self.assertEqual(dialog._rows["indent_size"][1].get_value(), 4)

    def test_saving_writes_the_changed_value_to_the_project_file_only(self):
        dialog = self.open_dialog(scope="project", select="Editor / Indentation")
        dialog._rows["indent_size"][1].set_value(2)
        dialog.save()
        self.assertEqual(SettingsStore(self.project).read("project"), {"indent_size": "2"})
        self.assertFalse(os.path.exists(self.global_file))
        self.assertEqual(self.saved[-1]["indent_size"], "2")

    def test_saving_without_a_change_creates_no_file(self):
        dialog = self.open_dialog(scope="project")
        dialog.save()
        self.assertFalse(os.path.exists(os.path.join(self.project, ".editorconfig")))

    def test_a_php_setting_of_the_global_file_is_shown_from_its_own_section(self):
        os.makedirs(os.path.dirname(self.global_file))
        with open(self.global_file, "w", encoding="utf-8") as handle:
            handle.write(f"[*.php]\nogmkdev_dialect = {PHP_VERSIONS[0]}\n")
        dialog = self.open_dialog(scope="global", select="Languages / PHP")
        self.assertEqual(dialog.values()["ogmkdev_dialect"], PHP_VERSIONS[0])


if __name__ == "__main__":
    unittest.main()
