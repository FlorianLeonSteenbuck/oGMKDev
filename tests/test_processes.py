"""The process group of a background service: a service whose shell has ended still has members, and ending the group ends
them all. Without GTK; the processes are real ones (sleep), started in their own session as the Run tab starts them."""

import os
import subprocess
import tempfile
import unittest

from ogmkdev import processes


class ProcessGroupTests(unittest.TestCase):
    def test_a_service_whose_shell_has_ended_is_still_a_member_until_the_group_is_ended(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile = os.path.join(folder, "pid")
            shell = subprocess.Popen(["/bin/sh", "-c", f'sleep 300 & echo $! > "{pidfile}"'], start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            shell.wait(timeout=30)  # the shell has ended; the sleep goes on in the background
            with open(pidfile, encoding="utf-8") as handle:
                child = int(handle.read())
            self.assertIn(child, processes.group_members(shell.pid))
            self.assertTrue(processes.terminate_group(shell.pid))
            self.assertEqual(processes.group_members(shell.pid), [])

    def test_a_group_without_members_has_ended_already(self):
        self.assertEqual(processes.group_members(2 ** 22 + 3), [])
        self.assertTrue(processes.terminate_group(2 ** 22 + 3))


if __name__ == "__main__":
    unittest.main()
