import os
import tempfile
import unittest

from ogmkdev import settings as S
from ogmkdev.document import Document


class SettingsScopesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = os.path.join(self._tmp.name, "project")
        os.makedirs(self.project)
        self.store = S.SettingsStore(self.project, global_path=os.path.join(self._tmp.name, "global", ".editorconfig"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_global_and_project_use_the_same_keys(self):
        self.store.apply("global", {"indent_size": "2", "ogmkdev_diagnostic_php_function": "error"})
        self.store.apply("project", {"indent_size": "8"})
        self.assertEqual(self.store.read("global")["indent_size"], "2")
        self.assertEqual(self.store.read("project")["indent_size"], "8")
        props = self.store.effective_for(os.path.join(self.project, "a.txt"))
        self.assertEqual(props["indent_size"], "8")                       # project beats global
        self.assertEqual(props["ogmkdev_diagnostic_php_function"], "error")  # global still applies

    def test_file_level_config_beats_project(self):
        self.store.apply("project", {"indent_size": "8"})
        os.makedirs(os.path.join(self.project, "legacy"))
        with open(os.path.join(self.project, "legacy", ".editorconfig"), "w", encoding="utf-8") as handle:
            handle.write("[*]\nindent_size = 3\n")
        self.assertEqual(self.store.effective_for(os.path.join(self.project, "legacy", "x.txt"))["indent_size"], "3")
        self.assertEqual(self.store.effective_for(os.path.join(self.project, "y.txt"))["indent_size"], "8")

    def test_default_value_removes_the_key_so_it_is_inherited_again(self):
        self.store.apply("project", {"indent_size": "8"})
        self.store.apply("project", {"indent_size": "4"})  # default
        self.assertNotIn("indent_size", self.store.read("project"))

    def test_php_version_scope_is_written_to_the_php_section(self):
        setting = S.SETTINGS_BY_KEY["ogmkdev_dialect"]
        self.store.write("project", setting, "8.3")
        with open(self.store.path_for("project"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("[*.php]", text)
        self.assertEqual(self.store.effective_for(os.path.join(self.project, "a.php"))["ogmkdev_dialect"], "8.3")

    def test_document_uses_the_effective_settings(self):
        self.store.apply("global", {"indent_size": "2"})
        path = os.path.join(self.project, "a.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("x\n")
        document = Document.open(path, self.store.effective_for(path))
        self.assertEqual(document.settings.indent_size, 2)

    def test_error_hinting_severity_changes_diagnostics(self):
        from ogmkdev.diagnostics import analyze
        from ogmkdev.languages import Detection
        self.store.apply("project", {"ogmkdev_diagnostic_php_function": "off"})
        props = self.store.effective_for(os.path.join(self.project, "a.php"))
        from ogmkdev import editorconfig
        settings = editorconfig.settings_from_properties(props)
        found = analyze("<?php clamp(1, 2, 3);", Detection("php", "8.5", None, "extension"), settings)
        self.assertEqual(found, [])
        self.store.apply("project", {"ogmkdev_diagnostics": "off"})
        props = self.store.effective_for(os.path.join(self.project, "a.php"))
        settings = editorconfig.settings_from_properties(props)
        self.assertEqual(analyze("<?php match(1) {};", Detection("php", "7.4", None, "extension"), settings), [])


if __name__ == "__main__":
    unittest.main()
