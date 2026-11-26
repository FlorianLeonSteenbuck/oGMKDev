"""The index build of the frame: closing the window shuts its builder down, so no build starts afterwards.

Needs PyGObject with GTK 4 and a display (run under xvfb-run); otherwise it is skipped.
"""

import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class IndexBuildTests(FrameTestCase):
    def test_closing_the_frame_shuts_the_index_builder_down(self):
        frame = self.frame()
        frame._request_index_build("test")
        builder = frame._index_builder
        frame.close()
        self.assertTrue(builder.closed)
        builder.request([self.folder])
        self.assertFalse(builder.busy)


if __name__ == "__main__":
    unittest.main()
