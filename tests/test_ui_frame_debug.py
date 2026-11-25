"""The frame's debug session against XDebug, through the frame itself: a breakpoint set in the Howl editor
(the gutter's mark) stops the script, the local variables and the watches show in the Variables tab, a watch
added during the stop is evaluated, and stopping ends the session and clears the values.

Needs PyGObject with GTK 4, a display (run under xvfb-run), libhowl.so and php with xdebug; otherwise it is
skipped.
"""

import os
import shutil
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "xdebug_target.php")


def _xdebug_available() -> bool:
    if not shutil.which("php"):
        return False
    result = subprocess.run(["php", "-m"], capture_output=True, text=True)
    return "xdebug" in result.stdout.lower()


try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk  # noqa: E402

    from ogmkdev import runconfig  # noqa: E402
    from ogmkdev.frame.howl import LIBRARY  # noqa: E402
    from ogmkdev.frame.window import Frame  # noqa: E402

    GTK_AVAILABLE = bool(os.environ.get("DISPLAY")) and os.path.isfile(LIBRARY)
except Exception:  # pragma: no cover - reported as a skip
    GTK_AVAILABLE = False


def _line_of(path, marker):
    with open(path, encoding="utf-8") as handle:
        for number, text in enumerate(handle, 1):
            if marker in text:
                return number
    raise AssertionError(marker)


def _pump_until(predicate, timeout=30.0) -> bool:
    """Runs the GLib main loop (idle callbacks of the frame, the engine's events) until the predicate holds."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _rows(frame):
    store = frame.variables_store
    return [tuple(row[0:3]) for row in store]


@unittest.skipUnless(GTK_AVAILABLE and _xdebug_available(),
                     "GTK 4 with a display, libhowl.so, and php with xdebug are required")
class FrameXdebugTests(unittest.TestCase):
    def test_breakpoint_stop_shows_variables_and_watches_and_stop_clears_them(self):
        with tempfile.TemporaryDirectory() as folder:
            script = os.path.join(folder, "target.php")
            shutil.copy(FIXTURE, script)
            os.makedirs(os.path.join(folder, ".run"))
            config_path = os.path.join(folder, ".run", "xdebug.run.xml")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '<component name="ProjectRunConfigurationManager">\n'
                    '  <configuration default="false" name="target" type="OgmkdevXdebugConfigurationType"'
                    ' factoryName="XDebug" nameIsGenerated="false">\n'
                    f'    <option name="SCRIPT_NAME" value="{script}" />\n'
                    '    <option name="PORT" value="0" />\n'
                    '  </configuration>\n'
                    '</component>\n')
            application = Gtk.Application(application_id="org.ogmkdev.frame.test",
                                          flags=Gio.ApplicationFlags.NON_UNIQUE)
            application.register(None)
            frame = Frame(application, folder, [script], "light", "blend")
            try:
                bp_line = _line_of(script, "@bp-return")
                frame.open_file(script, bp_line, 1)
                frame.editors.command("breakpoint-toggle")
                self.assertTrue(_pump_until(lambda: (script, bp_line) in frame.editors.breakpoints()),
                                "the breakpoint is not in the editor")

                frame.start_debugging(runconfig.load(config_path))
                self.assertTrue(_pump_until(lambda: ("variable", "$sum", "5") in _rows(frame)),
                                f"the locals did not show: {_rows(frame)}")
                rows = _rows(frame)
                for expected in (("variable", "$a", "2"), ("variable", "$b", "3")):
                    self.assertIn(expected, rows)

                frame.add_watch_expression("$sum * 10")
                self.assertTrue(_pump_until(lambda: ("watch", "$sum * 10", "50") in _rows(frame)),
                                f"the watch was not evaluated: {_rows(frame)}")

                frame.stop_debugging()
                self.assertTrue(_pump_until(lambda: frame._debugger is None), "the session did not end")
                rows = _rows(frame)
                self.assertNotIn("variable", [kind for kind, _name, _value in rows])
                self.assertIn(("watch", "$sum * 10", "no debug session"), rows)
            finally:
                if frame._debugger is not None:
                    frame.stop_debugging()
                frame.destroy()


if __name__ == "__main__":
    unittest.main()
