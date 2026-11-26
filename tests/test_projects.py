"""The projects file: the folders attached to a project come back when it is opened again, the most recent project comes
first, and a file that cannot be read is not overwritten."""

import json
import os
import tempfile
import unittest

from ogmkdev import projects
from ogmkdev.outcome import Failure


class ProjectsFileTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self._directory.name, "config")  # the file goes there
        self.app = os.path.join(self._directory.name, "app")
        self.lib = os.path.join(self._directory.name, "lib")
        os.makedirs(self.app)
        os.makedirs(self.lib)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._previous
        self._directory.cleanup()

    def test_a_project_comes_back_with_its_attached_folders(self):
        self.assertEqual(projects.attached_folders(self.app), [])
        self.assertIsInstance(projects.remember(self.app, [self.lib]), str)
        self.assertEqual(projects.attached_folders(self.app), [self.lib])

    def test_a_folder_that_is_gone_is_not_restored(self):
        projects.remember(self.app, [self.lib])
        os.rmdir(self.lib)
        self.assertEqual(projects.attached_folders(self.app), [])

    def test_the_most_recent_project_comes_first_and_each_is_kept_once(self):
        other = os.path.join(self._directory.name, "other")
        os.makedirs(other)
        projects.remember(self.app, [])
        projects.remember(other, [])
        projects.remember(self.app, [self.lib])
        found = projects.read_projects(projects.projects_path())
        self.assertEqual([project.folder for project in found], [self.app, other])
        self.assertEqual(found[0].attached, (self.lib,))

    def test_a_file_that_cannot_be_read_is_not_overwritten(self):
        path = projects.projects_path()
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self.assertIsInstance(projects.remember(self.app, [self.lib]), Failure)
        self.assertIsInstance(projects.attached_folders(self.app), Failure)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{ not json")

    def test_recent_projects_leave_out_the_open_one_and_the_gone_ones(self):
        other = os.path.join(self._directory.name, "other")
        gone = os.path.join(self._directory.name, "gone")
        os.makedirs(other)
        os.makedirs(gone)
        projects.remember(gone, [])
        projects.remember(other, [])
        projects.remember(self.app, [])
        os.rmdir(gone)
        self.assertEqual([project.folder for project in projects.recent_projects(exclude=self.app)], [other])
        self.assertEqual([project.folder for project in projects.recent_projects()], [self.app, other])

    def test_recent_projects_stop_at_the_limit_and_the_most_recent_comes_first(self):
        folders = []
        for number in range(3):
            path = os.path.join(self._directory.name, f"p{number}")
            os.makedirs(path)
            folders.append(path)
            projects.remember(path, [])
        self.assertEqual([project.folder for project in projects.recent_projects(limit=2)], [folders[2], folders[1]])

    def test_start_choices_list_each_folder_once_and_the_current_one_after_the_recent(self):
        self.assertEqual(projects.start_choices(["/a", "/b"], "/b"), ["/a", "/b"])
        self.assertEqual(projects.start_choices(["/a"], "/c"), ["/a", "/c"])
        self.assertEqual(projects.start_choices(["/a", "/a"], ""), ["/a"])
        self.assertEqual(projects.start_choices([], ""), [])

    def test_a_link_comes_back_when_the_project_is_opened_again_and_can_be_removed(self):
        other = os.path.join(self._directory.name, "other")
        os.makedirs(other)
        projects.remember(self.app, [])
        self.assertIsInstance(projects.link_project(self.app, other), str)
        self.assertEqual(projects.linked_folders(self.app), [other])
        projects.remember(self.app, [])  # opening the project again keeps its links
        self.assertEqual(projects.linked_folders(self.app), [other])
        self.assertIsInstance(projects.unlink_project(self.app, other), str)
        self.assertEqual(projects.linked_folders(self.app), [])

    def test_a_project_cannot_be_linked_to_itself_and_a_gone_link_is_not_restored(self):
        gone = os.path.join(self._directory.name, "gone")
        os.makedirs(gone)
        projects.remember(self.app, [])
        self.assertIsInstance(projects.link_project(self.app, self.app), Failure)
        projects.link_project(self.app, gone)
        os.rmdir(gone)
        self.assertEqual(projects.linked_folders(self.app), [])

    def test_an_entry_of_another_shape_is_skipped(self):
        path = projects.projects_path()
        os.makedirs(os.path.dirname(path))
        content = {"projects": [42, {"folder": 7}, {"folder": self.app, "attached": [self.lib]}]}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(content, handle)
        found = projects.read_projects(path)
        self.assertEqual([project.folder for project in found], [self.app])


if __name__ == "__main__":
    unittest.main()
