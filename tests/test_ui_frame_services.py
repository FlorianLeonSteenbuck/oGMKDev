"""The Run tab's background service: Stop ends it with the processes it started, even when its shell has ended, and closing
the frame ends it too.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import unittest

from ogmkdev import processes, runconfig
from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase, pump_until


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class BackgroundServiceTests(FrameTestCase):
    def start_service(self):
        """Starts a service from the Run tab: its shell puts the pid of a background sleep into a file and ends."""
        pidfile = os.path.join(self._directory.name, "service.pid")
        config = runconfig.shell_configuration("service", f'sleep 300 & echo $! > "{pidfile}"')
        runconfig.save(config, runconfig.configuration_path(self.folder, "service"))
        frame = self.frame()
        frame.refresh_run()
        frame.run_view.get_selection().select_iter(frame.run_store.get_iter_first())
        frame.run_selected()
        self.assertTrue(pump_until(lambda: os.path.isfile(pidfile) and os.path.getsize(pidfile) > 0, timeout=20))
        with open(pidfile, encoding="utf-8") as handle:
            child = int(handle.read())
        self.assertTrue(pump_until(lambda: frame._process.poll() is not None, timeout=20))  # the shell has ended
        return frame, frame._process.pid, child

    def test_stop_ends_a_service_whose_shell_has_ended(self):
        frame, group, child = self.start_service()
        self.assertTrue(frame._service_running(), "the service runs on after its shell has ended")
        self.assertIn(child, processes.group_members(group))
        frame.stop_process()
        self.assertFalse(frame._service_running())
        self.assertNotIn(child, processes.group_members(group))

    def test_closing_the_frame_ends_its_service(self):
        frame, group, child = self.start_service()
        frame.close()
        self.assertNotIn(child, processes.group_members(group))


if __name__ == "__main__":
    unittest.main()
