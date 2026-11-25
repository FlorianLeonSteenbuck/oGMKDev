import os
import shutil
import subprocess
import tempfile
import unittest

from ogmkdev import git as G
from ogmkdev import search_everywhere as S
from ogmkdev.workspace import Workspace, workspace_files


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        git(self.root, "init", "-q")
        with open(os.path.join(self.root, "a.txt"), "w") as h:
            h.write("one\n")
        git(self.root, "add", "a.txt")
        git(self.root, "commit", "-q", "-m", "first")

    def tearDown(self):
        self._tmp.cleanup()

    def labels(self):
        return {os.path.relpath(c.path, self.root): c.label for c in G.status(self.root)}

    def test_status_shows_modified_new_and_staged(self):
        with open(os.path.join(self.root, "a.txt"), "w") as h:
            h.write("two\n")
        with open(os.path.join(self.root, "b.txt"), "w") as h:
            h.write("new\n")
        with open(os.path.join(self.root, "c.txt"), "w") as h:
            h.write("staged\n")
        git(self.root, "add", "c.txt")
        self.assertEqual(self.labels(), {"a.txt": "M", "b.txt": "new", "c.txt": "A"})

    def test_stage_unstage_diff_and_commit(self):
        with open(os.path.join(self.root, "a.txt"), "w") as h:
            h.write("two\n")
        G.stage(self.root, [os.path.join(self.root, "a.txt")])
        self.assertEqual(self.labels(), {"a.txt": "M"})
        self.assertTrue([c for c in G.status(self.root) if c.staged])
        G.unstage(self.root, [os.path.join(self.root, "a.txt")])
        self.assertTrue("-one" in G.diff(self.root, os.path.join(self.root, "a.txt")) or "+two" in G.diff(
            self.root, os.path.join(self.root, "a.txt")))
        G.stage(self.root, [os.path.join(self.root, "a.txt")])
        G.commit(self.root, "update a")
        self.assertEqual(self.labels(), {})

    def test_empty_commit_message_is_refused(self):
        with self.assertRaises(G.GitError):
            G.commit(self.root, "  ")

    def test_folder_outside_a_repository_has_no_changes(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(G.status(plain), [])


class SearchTests(unittest.TestCase):
    def test_fuzzy_matching_and_ranking(self):
        self.assertIsNone(S.fuzzy_score("xyz", "Circle"))
        self.assertIsNotNone(S.fuzzy_score("crc", "Circle"))
        candidates = [S.Candidate("file", "Circle.php", "", ()), S.Candidate("file", "my-circle.php", "", ()),
                      S.Candidate("symbol", "Square", "", ())]
        ranked = S.rank(candidates, "circle")
        self.assertEqual([c.label for c in ranked], ["Circle.php", "my-circle.php"])
        self.assertEqual([c.label for c in S.rank(candidates, "", categories=["symbol"])], ["Square"])

    def test_workspace_files_skip_ignored_folders(self):
        with tempfile.TemporaryDirectory() as root:
            for rel in ("src/a.php", "vendor/lib.php", "tests/t.php"):
                os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
                open(os.path.join(root, rel), "w").close()
            workspace = Workspace.from_properties([root], {"ogmkdev_exclude": "vendor"})
            found = {os.path.relpath(p, root) for p in workspace_files(workspace)}
            self.assertEqual(found, {"src/a.php", "tests/t.php"})


if __name__ == "__main__":
    unittest.main()
