import os
import tempfile
import unittest

from ogmkdev.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self._tmp.name, "shop")
        self.other = os.path.join(self._tmp.name, "lib")
        self.props = {"ogmkdev_source_roots": "src,app", "ogmkdev_test_roots": "tests",
                      "ogmkdev_exclude": "vendor,build/cache,.git"}
        self.workspace = Workspace.from_properties([self.folder, self.other], self.props)

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *parts):
        return os.path.join(self.folder, *parts)

    def test_source_test_and_other_kinds(self):
        self.assertEqual(self.workspace.kind(self.p("src", "Shop.php")), "source")
        self.assertEqual(self.workspace.kind(self.p("tests", "ShopTest.php")), "test")
        self.assertEqual(self.workspace.kind(self.p("docs", "a.md")), "other")  # not in a source root

    def test_test_folder_name_matches_anywhere(self):
        self.assertEqual(self.workspace.kind(self.p("src", "tests", "x.php")), "test")

    def test_excluded_folders_are_not_in_the_workspace(self):
        self.assertTrue(self.workspace.is_excluded(self.p("vendor", "lib.php")))
        self.assertTrue(self.workspace.is_excluded(self.p("build", "cache", "x.o")))
        self.assertFalse(self.workspace.is_excluded(self.p("build", "x.o")))  # only build/cache is ignored
        self.assertEqual(self.workspace.kind(self.p(".git", "HEAD")), "excluded")

    def test_several_project_folders(self):
        self.assertEqual(self.workspace.folder_of(os.path.join(self.other, "src", "a.py")),
                         (os.path.abspath(self.other), "src/a.py"))
        self.assertIsNone(self.workspace.folder_of(os.path.join(self._tmp.name, "elsewhere.txt")))

    def test_defaults_without_roots_treat_everything_as_source(self):
        plain = Workspace.from_properties([self.folder], {})
        self.assertEqual(plain.kind(self.p("anything", "a.php")), "source")
        self.assertEqual(plain.kind(self.p("spec", "a.php")), "test")


if __name__ == "__main__":
    unittest.main()
