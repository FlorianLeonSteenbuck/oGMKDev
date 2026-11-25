"""The panes of the frame (split right, down, four and six; closing a pane keeps its files), the local history
of a saved file (kept outside the project), the autosave and index options at start, and the clear-index option.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import unittest
from unittest import mock

from ogmkdev import indexbuild
from ogmkdev.frame.analysis import _cache_path
from ogmkdev.frame.window import Frame
from tests.frame_support import FrameTestCase, GTK_AVAILABLE, SKIP_REASON, pump_until, write


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class PaneTests(FrameTestCase):
    def setUp(self):
        super().setUp()
        self.a = write(self.folder, "a.txt", "one\ntwo\n")
        self.b = write(self.folder, "b.txt", "bee\n")

    def test_split_right_down_and_four_panes_and_closing_them(self):
        frame = self.frame([self.a])
        self.assertEqual(len(frame.area.panes), 1)
        frame.split_right()
        self.assertEqual(len(frame.area.panes), 2)
        frame.split_down()
        self.assertEqual(len(frame.area.panes), 3)
        frame.close_active_pane()
        self.assertEqual(len(frame.area.panes), 2)
        frame.close_active_pane()
        self.assertEqual(len(frame.area.panes), 1)
        frame.split_four()
        self.assertEqual(len(frame.area.panes), 4)
        for _ in range(3):
            frame.close_active_pane()
        self.assertEqual(len(frame.area.panes), 1)

    def test_six_panes_and_the_open_file_stays_open(self):
        frame = self.frame([self.a])
        frame.split_six()
        self.assertEqual(len(frame.area.panes), 6)
        self.assertIn(self.a, frame.editors.files())

    def test_closing_a_pane_keeps_the_files_open_in_the_neighbour(self):
        frame = self.frame([self.a])
        frame.split_right()
        frame.open_file(self.b)
        self.wait_for_file(frame, self.b)
        frame.close_active_pane()
        self.assertEqual(len(frame.area.panes), 1)
        self.assertTrue({self.a, self.b} <= set(frame.editors.files()))  # Howl may hold buffers of earlier tests

    def test_the_last_pane_is_kept(self):
        frame = self.frame([self.a])
        frame.close_active_pane()
        self.assertEqual(len(frame.area.panes), 1)
        self.wait_for_file(frame, self.a)

    def test_saving_keeps_a_local_history_outside_the_project(self):
        frame = self.frame([self.a])
        self.focus(frame, self.a)
        frame.editors.insert_before(self.a, 1, "zero\n")
        frame.editors.command("save")
        self.assertTrue(pump_until(lambda: "save" in [r.label for r in frame.local_history.revisions(self.a)],
                                   timeout=15))
        revisions = frame.local_history.revisions(self.a)
        self.assertEqual(revisions[-1].label, "opened")  # the state when the file was first seen
        self.assertEqual(frame.local_history.content(revisions[-1]), "one\ntwo\n")
        self.assertIn("+zero", frame.local_history.patch_set(revisions))
        self.assertFalse(frame.local_history.base.startswith(self.folder))

    def test_the_autosave_setting_is_read_at_start_and_can_be_forced(self):
        self.assertTrue(self.frame([self.b], autosave=True).autosave_enabled)
        self.assertFalse(self.frame([self.b], autosave=False).autosave_enabled)

    def test_clear_index_removes_the_cached_index_before_the_index_is_built(self):
        cache = _cache_path(self.folder)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as handle:
            handle.write("{}")
        # the index is built on a worker thread: the check is made when the build is requested, which the
        # frame does after it has dropped the cache
        exists_when_requested = []
        original = indexbuild.IndexBuilder.request

        def request(builder, *args, **kwargs):
            exists_when_requested.append(os.path.exists(cache))
            return original(builder, *args, **kwargs)

        with mock.patch.object(indexbuild.IndexBuilder, "request", request):
            frame = Frame(self.app, self.folder, [self.b], "light", "blend", clear_index=True)
        self._frames.append(frame)
        self.assertTrue(exists_when_requested)
        self.assertFalse(any(exists_when_requested))


if __name__ == "__main__":
    unittest.main()
