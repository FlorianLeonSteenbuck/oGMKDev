"""The index as numbers per folder: each project folder (a root) and each folder directly below one, with the files, the
symbols and the references counted from the index. Without GTK."""

import os
import tempfile
import unittest

from ogmkdev import index as index_module
from ogmkdev.overview import folder_counts


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class FolderCountTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        base = self._directory.name
        self.app = os.path.join(base, "app")
        self.lib = os.path.join(base, "lib")
        write(os.path.join(self.app, "src", "Main.py"),
              "class Main:\n    def run(self):\n        return helper()\n\n\ndef helper():\n    return 1\n")
        write(os.path.join(self.app, "tests", "test_main.py"), "import src.Main\n\n\ndef test():\n    return 2\n")
        write(os.path.join(self.app, "README.py"), "value = 1\n")
        write(os.path.join(self.lib, "Util.py"), "class Util:\n    pass\n")

    def tearDown(self):
        self._directory.cleanup()

    def test_each_root_and_each_folder_below_it_is_counted(self):
        index = index_module.ProjectIndex([self.app, self.lib])
        rows = {row.label: row for row in folder_counts(index, [self.app, self.lib])}
        self.assertEqual(rows["app"].files, 3)  # every file under the root, the ones in its folders included
        self.assertTrue(rows["app"].root)
        self.assertEqual(rows["app/src"].files, 1)
        self.assertEqual(rows["app/tests"].files, 1)
        self.assertFalse(rows["app/src"].root)
        self.assertEqual(rows["lib"].files, 1)
        self.assertNotIn("lib/", " ".join(rows))  # the root has no folder below it with files
        self.assertGreater(rows["app/src"].symbols, 0)
        self.assertGreater(rows["app/src"].references, 0)
        self.assertEqual(rows["app"].symbols, rows["app/src"].symbols + rows["app/tests"].symbols)

    def test_the_folders_below_a_root_come_after_it(self):
        index = index_module.ProjectIndex([self.app])
        labels = [row.label for row in folder_counts(index, [self.app])]
        self.assertEqual(labels, ["app", "app/src", "app/tests"])


if __name__ == "__main__":
    unittest.main()
