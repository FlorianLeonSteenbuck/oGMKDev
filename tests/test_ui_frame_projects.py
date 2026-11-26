"""The project in the frame: the folders attached to it come back when it is opened again, and the status bar shows the
progress of a background task while it runs.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import tempfile
import unittest

from ogmkdev import projects
from ogmkdev.settings import ATTACHED_KEY, SettingsStore
from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, pump_until, write


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class ProjectFrameTests(FrameTestCase):
    def _index_done(self, frame):
        """Waits until the background index of the frame is built and delivered."""
        return pump_until(lambda: not frame._index_builder.busy, timeout=60)

    def test_opening_a_project_again_restores_the_folders_attached_to_it(self):
        with tempfile.TemporaryDirectory() as attached:
            first = self.frame()
            self.assertTrue(self._index_done(first))
            first._add_workspace_folder(attached)
            again = self.frame()
            self.assertTrue(self._index_done(again))
            self.assertIn(os.path.abspath(attached), again.project_folders)
            self.assertIn(os.path.abspath(attached), again.workspace.folders)

    def test_attached_folders_are_kept_in_the_project_settings_and_come_back_from_them(self):
        with tempfile.TemporaryDirectory() as attached:
            first = self.frame()
            self.assertTrue(self._index_done(first))
            first._add_workspace_folder(attached)
            self.assertEqual(SettingsStore(self.folder).read("project")[ATTACHED_KEY],
                             os.path.relpath(attached, self.folder))
            os.remove(projects.projects_path())  # the projects file forgets the project; the project settings do not
            again = self.frame()
            self.assertTrue(self._index_done(again))
            self.assertIn(os.path.abspath(attached), again.project_folders)

    def test_the_inspection_of_a_php_project_covers_the_attached_folders(self):
        from tests.frame_support import write

        with tempfile.TemporaryDirectory() as attached:
            write(self.folder, os.path.join("src", "Main.php"), "<?php\nnamespace App;\nuse Lib\\Util;\nclass Main {}\n")
            write(attached, os.path.join("src", "Lib", "Util.php"), "<?php\nnamespace Lib;\nclass Util {}\n")
            frame = self.frame()
            self.assertTrue(self._index_done(frame))
            frame._add_workspace_folder(attached)
            self.wait_for_index(frame, "Lib\\Util")  # the class of the attached folder is in the index now
            frame.inspect_folder()
            messages = [row[1] for row in frame.problems_store]
            self.assertFalse(any("Lib\\Util" in message and "cannot be resolved" in message for message in messages),
                             messages)

    def test_the_index_overview_shows_the_roots_and_the_folders_below_them(self):
        with tempfile.TemporaryDirectory() as attached:
            write(self.folder, os.path.join("src", "Main.py"), "class Main:\n    pass\n")
            write(attached, os.path.join("lib", "Util.py"), "class Util:\n    pass\n")
            frame = self.frame()
            self.assertTrue(self._index_done(frame))
            frame._add_workspace_folder(attached)
            self.wait_for_index(frame, "Util")
            frame.show_index_view()
            labels = [row.label for row in frame.index_view.shown]
            project = os.path.basename(self.folder)
            self.assertIn(project, labels)
            self.assertIn(f"{project}/src", labels)
            self.assertIn(os.path.basename(attached), labels)
            self.assertEqual(frame.bottom.get_nth_page(frame.bottom.get_current_page()), frame.index_view)

    def test_a_linked_project_is_part_of_the_project_and_comes_back_when_it_is_opened_again(self):
        with tempfile.TemporaryDirectory() as linked:
            write(linked, os.path.join("src", "Other.py"), "class Other:\n    pass\n")
            frame = self.frame()
            self.assertTrue(self._index_done(frame))
            frame.link_project_folder(linked)
            self.assertIn(os.path.abspath(linked), frame.project_folders)
            self.wait_for_index(frame, "Other")
            # the link is kept in the projects file; the project settings do not attach the folder
            self.assertNotIn(os.path.relpath(linked, self.folder),
                             SettingsStore(self.folder).read("project").get(ATTACHED_KEY, ""))
            again = self.frame()
            self.assertTrue(self._index_done(again))
            self.assertIn(os.path.abspath(linked), again.project_folders)
            again.unlink_project_folder(linked)
            self.assertNotIn(os.path.abspath(linked), again.project_folders)

    def test_file_menu_offers_the_projects_opened_before_and_opens_one(self):
        from gi.repository import GLib

        with tempfile.TemporaryDirectory() as earlier:
            projects.remember(earlier, [])
            frame = self.frame()
            self.assertTrue(self._index_done(frame))
            menu = frame._recent_menu
            labels = [menu.get_item_attribute_value(number, "label", None).get_string()
                      for number in range(menu.get_n_items())]
            self.assertIn(earlier, labels)
            frame.lookup_action("open-recent").activate(GLib.Variant.new_string(earlier))
            self.assertEqual(frame.folder, os.path.abspath(earlier))

    def test_the_status_bar_shows_the_progress_of_a_background_task(self):
        frame = self.frame()
        self.assertTrue(self._index_done(frame))
        progress = frame.task_progress
        progress.start("Index")
        progress.expect(4)
        progress.step()
        progress.step()
        frame._update_progress()
        self.assertTrue(frame.progress_bar.get_visible())
        self.assertEqual(frame.progress_bar.get_text(), "Index: 2 of 4 files")
        progress.finish()
        frame._update_progress()
        self.assertFalse(frame.progress_bar.get_visible())


if __name__ == "__main__":
    unittest.main()
