"""The start window: it offers the projects opened last, and the owner receives the folder that is chosen.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import tempfile
import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class StartWindowTests(FrameTestCase):
    def test_choosing_a_row_or_the_selected_one_reports_its_folder(self):
        from ogmkdev.frame.start import StartWindow

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            chosen = []
            window = StartWindow(self.app, [first, second], {first: "2026-11-25T10:00:00"}, chosen.append)
            window.present()
            self.assertEqual(window.list.get_selected_row().get_index(), 0)  # the first row is selected at the start
            window.choose(1)
            self.assertEqual(chosen, [second])
            window.list.select_row(window.list.get_row_at_index(0))
            window._choose_selected()
            self.assertEqual(chosen, [second, first])
            window.destroy()


if __name__ == "__main__":
    unittest.main()
