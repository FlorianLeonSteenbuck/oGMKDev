"""KDevelop's sessions (sessionrc files) and the import of their projects as recent projects."""

import os
import tempfile
import unittest

from ogmkdev import projects
from ogmkdev.bridges import kdevelop_sessions


class KdevelopSessionTest(unittest.TestCase):
    def test_the_projects_of_each_session_are_its_folders_once_each(self):
        with tempfile.TemporaryDirectory() as base:
            session = os.path.join(base, "3f2a")
            os.makedirs(session)
            with open(os.path.join(session, "sessionrc"), "w", encoding="utf-8") as handle:
                handle.write("SessionName=Shop Work\n\n[General Options]\n"
                             "Open Projects=file:///home/a/shop/shop.kdev4,file:///home/a/my%20tool/tool.kdev4,"
                             "file:///home/a/shop/shop.kdev4\n")
            found = kdevelop_sessions.read_sessions(base)
            self.assertEqual(1, len(found))
            self.assertEqual("Shop Work", found[0].name)
            self.assertEqual(("/home/a/shop", "/home/a/my tool"), found[0].folders)

    def test_a_session_without_a_name_is_named_by_its_folder(self):
        with tempfile.TemporaryDirectory() as base:
            session = os.path.join(base, "beef")
            os.makedirs(session)
            with open(os.path.join(session, "sessionrc"), "w", encoding="utf-8") as handle:
                handle.write("[General Options]\nOpen Projects=/plain/path/proj\n")
            found = kdevelop_sessions.read_sessions(base)
            self.assertEqual("beef", found[0].name)
            self.assertEqual(("/plain/path/proj",), found[0].folders)

    def test_folders_without_sessionrc_and_a_missing_base_are_skipped(self):
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "empty"))
            self.assertEqual([], kdevelop_sessions.read_sessions(base))
            self.assertEqual([], kdevelop_sessions.read_sessions(os.path.join(base, "missing")))

    def test_the_session_base_follows_xdg_data_home(self):
        self.assertEqual(os.path.join("/data", "kdevelop", "sessions"),
                         kdevelop_sessions.session_base({"XDG_DATA_HOME": "/data"}))


class ImportRecentTest(unittest.TestCase):
    def test_folders_not_known_yet_are_added_after_the_saved_projects(self):
        with tempfile.TemporaryDirectory() as root:
            known = os.path.join(root, "known")
            new = os.path.join(root, "new")
            os.makedirs(known)
            os.makedirs(new)
            path = os.path.join(root, "projects.json")
            projects.write_projects(path, [projects.Project(known, (os.path.join(root, "lib"),), "2026-01-01T10:00:00", ())])
            self.assertEqual(1, projects.import_recent(path, [known, new, os.path.join(root, "gone")]))
            saved = projects.read_projects(path)
            self.assertEqual([known, new], [project.folder for project in saved])
            self.assertEqual((os.path.join(root, "lib"),), saved[0].attached, "the known project keeps its folders")
            self.assertEqual("", saved[1].opened)
            self.assertEqual(0, projects.import_recent(path, [new]), "nothing new: nothing is added again")


if __name__ == "__main__":
    unittest.main()
