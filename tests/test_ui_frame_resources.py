"""The Resources tab of the frame: the IDE, the index and the program the Run tab started, with its pid."""

import subprocess
import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, pump_until


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class ResourcesTabTests(FrameTestCase):
    def text_of(self, frame):
        buffer = frame.resources_view.view.get_buffer()
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, False)

    def test_the_tab_shows_the_ide_the_index_and_no_program_until_one_runs(self):
        frame = self.frame()
        frame.show_resources_view()
        text = self.text_of(frame)
        self.assertIn("oGMKDev (process", text)
        self.assertIn("Running program: none", text)
        self.assertIn("Index:", text)
        self.assertEqual(frame.bottom.get_nth_page(frame.bottom.get_current_page()), frame.resources_view)

    def test_a_program_started_by_the_run_tab_is_named_while_it_runs(self):
        frame = self.frame()
        process = subprocess.Popen(["sleep", "30"], start_new_session=True)  # as the Run tab starts a service
        self.addCleanup(process.kill)
        frame._process = process
        frame.refresh_resources_view()
        self.assertIn(f"Running program (process {process.pid}, sleep)", self.text_of(frame))


if __name__ == "__main__":
    unittest.main()
