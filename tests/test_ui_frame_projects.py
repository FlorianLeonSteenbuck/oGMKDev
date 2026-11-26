"""The project in the frame: the folders attached to it come back when it is opened again, and the status bar shows the
progress of a background task while it runs.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import tempfile
import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, pump_until


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
