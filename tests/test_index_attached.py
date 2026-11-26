"""The index over the folders of one project. A PHP import resolves to a class of an attached folder, and the inspections
use the settings of the editor: the global preferences as well as the project's file."""

import os
import tempfile
import unittest

from ogmkdev import editorconfig
from ogmkdev import index as index_module
from ogmkdev.settings import SettingsStore


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class AttachedFolderIndexTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        base = self._directory.name
        self.app = os.path.join(base, "app")
        self.lib = os.path.join(base, "lib")
        write(os.path.join(self.app, "src", "Main.php"),
              "<?php\nnamespace App;\nuse Lib\\Util;\nuse Lib\\Missing;\nclass Main {\n"
              "    public function run() { return Util::x(); }\n}\n")
        write(os.path.join(self.lib, "src", "Lib", "Util.php"),
              "<?php\nnamespace Lib;\nclass Util { public static function x() { return 1; } }\n")
        self.store = SettingsStore(self.app, global_path=os.path.join(base, "global", ".editorconfig"))

    def tearDown(self):
        self._directory.cleanup()

    @staticmethod
    def unresolved(found):
        return sorted(item.message for item in found if item.code == "unresolved-import")

    def test_an_import_resolves_to_a_class_of_an_attached_folder(self):
        alone = index_module.ProjectIndex([self.app]).inspect()
        self.assertEqual(self.unresolved(alone), ["import Lib\\Missing cannot be resolved in the project",
                                                  "import Lib\\Util cannot be resolved in the project"])
        together = index_module.ProjectIndex([self.app, self.lib]).inspect()
        self.assertEqual(self.unresolved(together), ["import Lib\\Missing cannot be resolved in the project"])

    def test_the_inspections_use_the_global_preferences_of_the_editor(self):
        note = os.path.join(self.app, "src", "plain.py")
        write(note, "value = 1")  # no newline at the end of the file
        # the global preference asks for a final newline; the default value would not be written to the file at all
        editorconfig.write_property(self.store.global_path, "*", "insert_final_newline", "true")
        editor = lambda path: editorconfig.settings_from_properties(self.store.effective_for(path))  # noqa: E731
        found = index_module.ProjectIndex([self.app], settings_for=editor).inspect()
        self.assertTrue(any(item.file == note and item.code == "final-newline" for item in found))
        self.store.apply("global", {"ogmkdev_diagnostic_final_newline": "off"})  # the severity switched off
        found = index_module.ProjectIndex([self.app], settings_for=editor).inspect()
        self.assertFalse(any(item.file == note and item.code == "final-newline" for item in found))


if __name__ == "__main__":
    unittest.main()
