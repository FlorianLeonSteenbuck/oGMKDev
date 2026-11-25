"""Set-up shared by the frame tests: a GTK 4 application, a temporary project folder, the frames a test opens
(closed afterwards), and waiting for the GLib main loop. Each test has its own data and cache folders, so the
local history and the index cache of the frame never touch the user's.

The frame needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; GTK_AVAILABLE tells.
This module is not a test module (its name has no test_ prefix).
"""

import os
import tempfile
import time
import unittest

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk  # noqa: E402

    from ogmkdev.frame.howl import LIBRARY  # noqa: E402
    from ogmkdev.frame.window import Frame  # noqa: E402

    GTK_AVAILABLE = bool(os.environ.get("DISPLAY")) and os.path.isfile(LIBRARY)
except Exception:  # pragma: no cover - reported as a skip
    GTK_AVAILABLE = False

SKIP_REASON = "needs GTK 4, a display and libhowl.so"
APPLICATION_ID = "org.ogmkdev.test.frame"


def pump_until(predicate, timeout=30.0) -> bool:
    """Runs the GLib main loop until ``predicate`` holds or the timeout passes."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return True
        time.sleep(0.02)
    return False


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def line_of(path, marker):
    with open(path, encoding="utf-8") as handle:
        for number, text in enumerate(handle, 1):
            if marker in text:
                return number
    raise AssertionError(marker)


def walk(widget):
    """The widget and all its descendants."""
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


class FrameTestCase(unittest.TestCase):
    """A project folder (``self.folder``), the frames a test opens, and the data and cache folders of the test."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self._directory.name, "project")
        os.makedirs(self.folder)
        self._data = tempfile.TemporaryDirectory()
        self._cache = tempfile.TemporaryDirectory()
        self._environment = {name: os.environ.get(name) for name in ("XDG_DATA_HOME", "XDG_CACHE_HOME")}
        os.environ["XDG_DATA_HOME"] = self._data.name  # the local history of the frames goes here
        os.environ["XDG_CACHE_HOME"] = self._cache.name  # the index cache goes here
        self.app = Gtk.Application(application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self._frames = []

    def tearDown(self):
        for frame in self._frames:
            frame.close()  # stops the frame's status poll and autosave
        for name, value in self._environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._data.cleanup()
        self._cache.cleanup()
        self._directory.cleanup()

    def frame(self, files=(), mode="light", scheme="blend", autosave=None, clear_index=False):
        """A frame on the project folder with ``files`` open, shown and running (its Howl editors are up)."""
        frame = Frame(self.app, self.folder, list(files), mode, scheme, autosave=autosave, clear_index=clear_index)
        self._frames.append(frame)
        frame.present()
        self.assertTrue(pump_until(lambda: frame.editors.status() is not None, timeout=40))
        return frame

    def wait_for_index(self, frame, *names):
        """Until the frame's index knows every class of ``names`` (full names, as the index keeps them)."""
        known = lambda: all(any(symbol.name == name for symbol in frame.index.symbols) for name in names)
        self.assertTrue(pump_until(known, timeout=90), f"the index does not know {names}")

    def wait_for_file(self, frame, path):
        """Until the open file of the frame is ``path`` (the tab that is shown)."""
        self.assertTrue(pump_until(lambda: frame.area.current_path() == path, timeout=10),
                        f"{path} is not the open file")

    def focus(self, frame, path):
        """Makes the Howl editor of ``path`` the current one: the one that commands and the status line act on.
        Howl is one process, so an editor of an earlier test may still hold the focus."""
        frame.open_file(path)
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("path") == path, timeout=10),
                        f"{path} is not the current editor")
