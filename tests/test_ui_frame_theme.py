"""The theme of the frame while it runs: View > Dark Theme and the colour scheme items switch the frame's
colours, the Howl theme, the marks of the View menu and the folder colours; every open frame follows.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import tempfile
import time
import unittest

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, GLib, Gtk  # noqa: E402

    from ogmkdev.frame import theme as frame_theme  # noqa: E402
    from ogmkdev.frame.howl import LIBRARY  # noqa: E402
    from ogmkdev.frame.window import Frame, theme_folder  # noqa: E402

    GTK_AVAILABLE = bool(os.environ.get("DISPLAY")) and os.path.isfile(LIBRARY)
except Exception:  # pragma: no cover - reported as a skip
    GTK_AVAILABLE = False


def _pump_until(predicate, timeout=30.0) -> bool:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return True
        time.sleep(0.02)
    return False


@unittest.skipUnless(GTK_AVAILABLE, "needs GTK 4, a display and libhowl.so")
class ThemeTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = self._directory.name
        os.mkdir(os.path.join(self.folder, "tests"))  # a test folder: its row has a role colour
        self.app = Gtk.Application(application_id="org.ogmkdev.test.theme", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self._frames = []

    def tearDown(self):
        for frame in self._frames:
            frame.close()  # stops the frame's status poll and autosave
        self._directory.cleanup()

    def _frame(self, mode="light", scheme="blend"):
        frame = Frame(self.app, self.folder, [], mode, scheme)
        self._frames.append(frame)
        frame.present()
        self.assertTrue(_pump_until(lambda: frame.editors.status() is not None, timeout=40))
        return frame

    @staticmethod
    def _state(frame, name):
        return frame.lookup_action(name).get_state()

    @staticmethod
    def _folder_colour(frame, name):
        colours = []

        def visit(model, _path, iterator):
            if model[iterator][2] == "folder" and model[iterator][0] == name:
                colours.append(model[iterator][3])
            return False

        frame.tree_store.foreach(visit)
        return colours[0]

    def test_the_view_menu_items_show_the_mode_and_the_scheme_of_the_frame(self):
        frame = self._frame("dark", "jetbrains")
        self.assertTrue(self._state(frame, "dark-theme").get_boolean())
        self.assertEqual(self._state(frame, "color-scheme").get_string(), "jetbrains")

    def test_dark_theme_switches_the_frame_and_the_howl_theme_and_back(self):
        frame = self._frame()
        frame.lookup_action("dark-theme").activate(None)
        self.assertEqual(frame.mode, "dark")
        self.assertTrue(self._state(frame, "dark-theme").get_boolean())
        # the Howl theme of the new mode and scheme is written to the frame's theme folder
        path = os.path.join(theme_folder(), "ogmkdev-dark-blend.css")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), frame_theme.howl_css("dark", "blend"))
        frame.lookup_action("dark-theme").activate(None)
        self.assertEqual(frame.mode, "light")
        self.assertFalse(self._state(frame, "dark-theme").get_boolean())

    def test_a_colour_scheme_item_selects_the_scheme(self):
        frame = self._frame()
        frame.lookup_action("color-scheme").activate(GLib.Variant.new_string("eclipse"))
        self.assertEqual(frame.scheme, "eclipse")
        self.assertEqual(self._state(frame, "color-scheme").get_string(), "eclipse")

    def test_the_folder_colours_follow_the_mode(self):
        frame = self._frame()
        self.assertEqual(self._folder_colour(frame, "tests"), frame_theme.role_colour("light", "test"))
        frame.set_theme("dark")
        self.assertEqual(self._folder_colour(frame, "tests"), frame_theme.role_colour("dark", "test"))

    def test_every_open_frame_follows_the_theme(self):
        first = self._frame()
        second = self._frame()
        first.lookup_action("dark-theme").activate(None)
        self.assertEqual(second.mode, "dark")
        self.assertTrue(self._state(second, "dark-theme").get_boolean())
        second.lookup_action("color-scheme").activate(GLib.Variant.new_string("eclipse"))
        self.assertEqual(first.scheme, "eclipse")
        self.assertEqual(self._state(first, "color-scheme").get_string(), "eclipse")

    def test_unknown_modes_and_schemes_are_refused(self):
        frame = self._frame()
        with self.assertRaises(ValueError):
            frame.set_theme("sepia")
        with self.assertRaises(ValueError):
            frame.set_theme("light", "solarized")
        self.assertEqual((frame.mode, frame.scheme), ("light", "blend"))


if __name__ == "__main__":
    unittest.main()
