"""Folder rules of the workspace (ogmkdev_folder_rules, the Custom settings): a rule names a folder by a pattern and gives it
a role. The first rule that matches wins and beats the default names; none keeps a folder without a role."""

import os
import tempfile
import unittest

from ogmkdev.workspace import Workspace


class FolderRulesTest(unittest.TestCase):
    def test_rules_name_folders_by_pattern_and_beat_the_default_names(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("client_api", "ui_kit", "tests", "build", "spec_cases"):
                os.makedirs(os.path.join(root, name))
            workspace = Workspace.from_properties(
                [root], {"ogmkdev_folder_rules": "*_api=build; ui_*=assets; tests=none; spec_*=test"})
            self.assertEqual("build", workspace.role(os.path.join(root, "client_api")))
            self.assertEqual("assets", workspace.role(os.path.join(root, "ui_kit")))
            self.assertIsNone(workspace.role(os.path.join(root, "tests")), "none beats the default test name")
            self.assertEqual("build", workspace.role(os.path.join(root, "build")), "the default still applies")
            self.assertEqual("test", workspace.role(os.path.join(root, "spec_cases")))

    def test_entries_that_do_not_parse_are_skipped(self):
        workspace = Workspace.from_properties([], {"ogmkdev_folder_rules": "broken; x=unknown; =test; ok=source"})
        self.assertEqual((("ok", "source"),), workspace.rules)

    def test_without_rules_the_default_names_decide(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "tests"))
            workspace = Workspace.from_properties([root], {})
            self.assertEqual("test", workspace.role(os.path.join(root, "tests")))


if __name__ == "__main__":
    unittest.main()
