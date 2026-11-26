"""Crashes and criticals seen in the frame. The 'Loose files' entry must come back after the tree was rebuilt: its tree
iterator went stale, which crashed GTK. A file with umlauts and a trailing newline must take its change marks without an
Invalid offset from Howl.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import tempfile
import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, write


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class StabilityTests(FrameTestCase):
    def test_loose_files_come_back_after_the_tree_was_rebuilt(self):
        with tempfile.TemporaryDirectory() as outside:
            path = write(outside, "loose.txt", "text\n")  # outside the project folder: the file hangs loose
            frame = self.frame()
            frame.open_file(path)
            frame._sync_loose()
            self.assertIsNotNone(frame._loose_iter())
            frame._reload_project()  # clears the tree, the entry of the loose files goes with it
            self.assertIsNone(frame._loose_iter())
            frame._sync_loose()
            self.assertIsNotNone(frame._loose_iter())

    def test_a_file_with_umlauts_and_a_trailing_newline_takes_its_change_marks(self):
        path = write(self.folder, "umlaut.txt", "ä\nö\n")
        frame = self.frame(files=[path])
        # line 3 is the empty line after the last newline: its mark must stop at the end of the buffer
        self.assertTrue(frame.editors.changes(path, [(1, "changed"), (3, "added")]))


if __name__ == "__main__":
    unittest.main()
