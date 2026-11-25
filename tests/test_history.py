import os
import shutil
import subprocess
import tempfile
import time
import unittest

from ogmkdev import history as H


class LocalHistoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.history = H.LocalHistory(os.path.join(self._tmp.name, "data"))
        self.path = os.path.join(self._tmp.name, "project", "a.txt")

    def tearDown(self):
        self._tmp.cleanup()

    def test_snapshots_are_stored_outside_the_project_and_not_duplicated(self):
        first = self.history.snapshot(self.path, "one\n")
        self.assertIsNotNone(first)
        self.assertIsNone(self.history.snapshot(self.path, "one\n"))  # same as latest: no new revision
        self.assertFalse(os.path.exists(os.path.dirname(self.path)))  # the project folder is untouched
        self.assertEqual(self.history.content(first), "one\n")

    def test_revisions_are_newest_first_with_labels(self):
        self.history.snapshot(self.path, "one\n", "save")
        time.sleep(0.002)
        self.history.snapshot(self.path, "two\n", "autosave")
        revisions = self.history.revisions(self.path)
        self.assertEqual([r.label for r in revisions], ["autosave", "save"])
        self.assertEqual(self.history.content(revisions[0]), "two\n")

    def test_patch_set_combines_consecutive_diffs(self):
        self.history.snapshot(self.path, "a\nb\n")
        time.sleep(0.002)
        self.history.snapshot(self.path, "a\nB\n")
        time.sleep(0.002)
        self.history.snapshot(self.path, "a\nB\nc\n")
        patch = self.history.patch_set(self.history.revisions(self.path))
        self.assertIn("-b\n+B\n", patch)
        self.assertIn("+c\n", patch)
        destination = os.path.join(self._tmp.name, "out", "change.patch")
        self.history.extract_patch(self.history.revisions(self.path), destination)
        with open(destination, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), patch)

    def test_changed_lines_mark_added_modified_and_deleted(self):
        marks = H.changed_lines("a\nb\nc\nd\n", "a\nB\nc\nd\ne\n")
        self.assertEqual(marks, {2: "modified", 5: "added"})
        self.assertEqual(H.changed_lines("a\nb\nc\n", "a\nc\n"), {2: "deleted"})
        self.assertEqual(H.changed_lines("same\n", "same\n"), {})

    def test_diff_shows_both_sides(self):
        diff = H.LocalHistory.diff("x\n", "y\n", "old", "new")
        self.assertIn("--- old", diff)
        self.assertIn("+++ new", diff)
        self.assertIn("-x\n+y\n", diff)


class PatchTests(unittest.TestCase):
    def test_file_patch_marks_missing_final_newline(self):
        patch = H.file_patch("one\n", "one\ntwo", "notes.txt")
        self.assertTrue(patch.startswith("diff --git a/notes.txt b/notes.txt\n--- a/notes.txt\n+++ b/notes.txt\n"))
        self.assertIn("\\ No newline at end of file", patch)

    def test_file_patch_of_identical_text_is_empty(self):
        self.assertEqual(H.file_patch("same\n", "same\n", "x.txt"), "")

    def test_patch_names_are_relative_to_the_project(self):
        self.assertEqual(H.patch_name("/p/src/a.php", "/p"), "src/a.php")
        self.assertEqual(H.patch_name("/elsewhere/a.php", "/p"), "a.php")


@unittest.skipUnless(shutil.which("git"), "git is required")
class HistoryPatchTests(unittest.TestCase):
    def test_exported_history_applies_with_git_apply(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as target:
            store = H.LocalHistory(os.path.join(root, "history"))
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


if __name__ == "__main__":
    unittest.main()
