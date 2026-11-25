"""Edit > Export History as Patch in the frame: every revision of the open file's local history, as one
git-style patch. The local history is kept in a temporary folder (XDG_DATA_HOME) for the test.

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

    from ogmkdev.frame.howl import LIBRARY  # noqa: E402
    from ogmkdev.frame.window import Frame  # noqa: E402

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


class _Chooser:
    """Stands in for the file chooser: its response hands over the file it was given."""

    def __init__(self, path):
        self._file = Gio.File.new_for_path(path)

    def get_file(self):
        return self._file


@unittest.skipUnless(GTK_AVAILABLE, "needs GTK 4, a display and libhowl.so")
class ExportHistoryPatchTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = self._directory.name
        self._old_data_home = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = os.path.join(self.folder, "data")  # the frame's history goes here
        self.shop = os.path.join(self.folder, "Shop.php")
        with open(self.shop, "w", encoding="utf-8") as handle:
            handle.write("<?php\nclass Shop {}\n")
        self.app = Gtk.Application(application_id="org.ogmkdev.test.history", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.app.register(None)
        self.frame = Frame(self.app, self.folder, [self.shop], "light", "blend")
        self.frame.present()
        self.assertTrue(_pump_until(lambda: self.frame.editors.status() is not None, timeout=40))
        # the frame takes the first revision of the file when it sees it
        self.assertTrue(_pump_until(lambda: len(self.frame.local_history.revisions(self.shop)) == 1, timeout=10))

    def tearDown(self):
        self.frame.close()  # stops the frame's status poll
        if self._old_data_home is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._old_data_home
        self._directory.cleanup()

    def test_a_file_without_a_change_has_nothing_to_export(self):
        self.frame.export_history_patch()
        self.assertEqual(self.frame.status.get_text(), "the history has no change to export yet")

    def test_the_patch_holds_the_diff_of_each_change(self):
        self.frame.local_history.snapshot(self.shop, "<?php\nclass Shop { }\n", "save")
        revisions = self.frame.local_history.revisions(self.shop)
        self.assertGreaterEqual(len(revisions), 2)
        destination = os.path.join(self.folder, "shop.patch")
        self.frame._write_patch(_Chooser(destination), Gtk.ResponseType.ACCEPT, revisions)
        with open(destination, encoding="utf-8") as handle:
            patch = handle.read()
        self.assertIn("-class Shop {}", patch)
        self.assertIn("+class Shop { }", patch)

    def test_local_history_shows_the_revisions_of_the_open_file_in_the_history_tab(self):
        self.frame.show_local_history()
        self.assertEqual(self.frame.left.get_current_page(), self.frame.left.page_num(self.frame.history_box))
        self.assertEqual(len(self.frame.hist_store), len(self.frame.local_history.revisions(self.shop)))


if __name__ == "__main__":
    unittest.main()
