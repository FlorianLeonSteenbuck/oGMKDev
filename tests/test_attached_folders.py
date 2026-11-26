"""The attached folders of a project as settings: their text form, the scope they are edited in, and what an empty list
means. The frame and the settings dialog use the same text, so these tests fix it without GTK."""

import os
import tempfile
import unittest

from ogmkdev.settings import (ATTACHED_KEY, SETTINGS_BY_KEY, SettingsStore, build_model, folder_list, folders_text,
                              in_scope, model_text, set_model_text)


class AttachedFoldersTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.project = os.path.join(self._directory.name, "project")
        os.makedirs(self.project)
        global_file = os.path.join(self._directory.name, "global", ".editorconfig")
        self.store = SettingsStore(self.project, global_path=global_file)
        self.setting = SETTINGS_BY_KEY[ATTACHED_KEY]

    def tearDown(self):
        self._directory.cleanup()

    def test_the_text_holds_the_folders_comma_separated_and_reads_back(self):
        text = folders_text(["../lib", "/opt/shared"])
        self.assertEqual(text, "../lib, /opt/shared")
        self.assertEqual(folder_list(text), ["../lib", "/opt/shared"])
        self.assertEqual(folder_list(" , ../a ,, "), ["../a"])
        self.assertEqual(folder_list(""), [])

    def test_the_attached_folders_are_edited_in_the_project_scope_only(self):
        self.assertTrue(in_scope(self.setting, "project"))
        self.assertFalse(in_scope(self.setting, "global"))

    def test_an_empty_list_is_written_as_a_choice_and_is_not_removed(self):
        self.store.write("project", self.setting, "")
        self.assertEqual(self.store.read("project"), {ATTACHED_KEY: ""})
        self.store.write("project", self.setting, "../lib")
        self.assertEqual(self.store.read("project"), {ATTACHED_KEY: "../lib"})

    def test_a_project_without_the_key_names_no_folders(self):
        self.assertNotIn(ATTACHED_KEY, self.store.read("project"))

    def test_the_project_settings_apply_to_the_files_of_the_attached_folders_too(self):
        lib = os.path.join(self._directory.name, "lib", "src")
        os.makedirs(lib)
        util = os.path.join(lib, "Util.php")
        with open(util, "w", encoding="utf-8") as handle:
            handle.write("<?php\n")
        self.store.apply("project", {"ogmkdev_dialect": "7.4"})
        self.assertEqual(self.store.effective_for(util).get("ogmkdev_dialect"), "7.4")

    def test_an_attached_folder_keeps_its_own_settings_over_the_project_ones(self):
        lib = os.path.join(self._directory.name, "lib", "src")
        os.makedirs(lib)
        with open(os.path.join(lib, "Util.php"), "w", encoding="utf-8") as handle:
            handle.write("<?php\n")
        with open(os.path.join(os.path.dirname(lib), ".editorconfig"), "w", encoding="utf-8") as handle:
            handle.write("root = true\n\n[*.php]\nogmkdev_dialect = 8.0\n")
        self.store.apply("project", {"ogmkdev_dialect": "7.4"})
        self.assertEqual(self.store.effective_for(os.path.join(lib, "Util.php")).get("ogmkdev_dialect"), "8.0")

    def test_the_model_holds_the_folder_text_as_it_is_set(self):
        model = build_model({ATTACHED_KEY: "../lib"})
        self.assertEqual(model_text(model, self.setting), "../lib")
        self.assertEqual(set_model_text(model, self.setting, "../lib, ../tools"), "../lib, ../tools")
        self.assertEqual(model_text(model, self.setting), "../lib, ../tools")


if __name__ == "__main__":
    unittest.main()
