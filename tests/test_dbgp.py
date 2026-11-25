import os
import shutil
import subprocess
import unittest

from ogmkdev.debug import Exited, Stopped, XdebugDebugger

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _xdebug_available() -> bool:
    if not shutil.which("php"):
        return False
    result = subprocess.run(["php", "-m"], capture_output=True, text=True)
    return "xdebug" in result.stdout.lower()


def _line_of(path, marker):
    with open(path, encoding="utf-8") as handle:
        for number, text in enumerate(handle, 1):
            if marker in text:
                return number
    raise AssertionError(marker)


@unittest.skipUnless(_xdebug_available(), "php with xdebug is required")
class XdebugIntegrationTests(unittest.TestCase):
    def test_breakpoint_eval_step_and_end_of_script(self):
        source = os.path.join(FIXTURES, "xdebug_target.php")
        dbg = XdebugDebugger(port=0, timeout=30)
        port = dbg.listen()
        proc = subprocess.Popen(
            ["php", "-d", "xdebug.mode=debug", "-d", "xdebug.start_with_request=yes",
             "-d", "xdebug.client_host=127.0.0.1", "-d", f"xdebug.client_port={port}", source],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            dbg.start()
            self.assertEqual(dbg.init_info.get("language"), "PHP")
            bp_line = _line_of(source, "@bp-return")
            bp = dbg.add_breakpoint(source, bp_line)
            dbg.run()
            stop = dbg.wait_event(lambda e: isinstance(e, Stopped), 30)
            self.assertEqual((stop.reason, stop.breakpoint_id), ("breakpoint", bp.id))
            self.assertEqual(stop.location.line, bp_line)
            self.assertEqual(os.path.realpath(stop.location.file), os.path.realpath(source))
            self.assertEqual(dbg.evaluate("$a"), "2")
            self.assertEqual(dbg.evaluate("$sum"), "5")
            self.assertEqual(dbg.watch_values(), {})
            dbg.add_watch("$sum + 1")
            self.assertEqual(dbg.watch_values(), {"$sum + 1": "6"})

            dbg.remove_breakpoint(bp.id)
            dbg.step_over()
            step = dbg.wait_event(lambda e: isinstance(e, Stopped), 30)
            self.assertEqual(step.reason, "step")
            self.assertGreater(step.location.line, bp_line)

            dbg.run()
            done = dbg.wait_event(lambda e: isinstance(e, Exited), 30)
            self.assertIsNone(done.code)
            out, _ = proc.communicate(timeout=30)
            self.assertIn("total=5", out)
        finally:
            dbg.stop()
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
