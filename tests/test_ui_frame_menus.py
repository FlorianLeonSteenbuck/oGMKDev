"""The menu bar and the toolbar of the frame: every entry names a Frame method or a Howl command, the action
names are unique, the menus offer the items of the former GTK 3 window, and every toolbar icon exists in the
icon theme of the frame.

The target tests need PyGObject with GTK 4 only; the icon test needs a display and libhowl.so as well.
"""

import unittest

from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase

try:
    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gdk, Gtk  # noqa: E402

    from ogmkdev.frame.menus import MENUS  # noqa: E402
    from ogmkdev.frame.window import TOOLBAR, Frame  # noqa: E402

    MENUS_AVAILABLE = True
except Exception:  # pragma: no cover - reported as a skip
    MENUS_AVAILABLE = False


def _menu_labels(title):
    for menu_title, entries in MENUS:
        if menu_title == title:
            return [label for label, *_rest in entries]
    raise AssertionError(title)


@unittest.skipUnless(MENUS_AVAILABLE, "needs PyGObject with GTK 4")
class MenuTargetTests(unittest.TestCase):
    def test_every_menu_and_toolbar_entry_names_a_frame_method_or_a_howl_command(self):
        targets = [(title, label, target) for title, entries in MENUS for label, _name, _acc, target in entries]
        targets += [("toolbar", tooltip, target) for item in TOOLBAR if item not in (None, "spacer")
                    for _icon, tooltip, target in [item]]
        for title, label, target in targets:
            if target.startswith("howl:"):
                continue
            with self.subTest(menu=title, item=label):
                self.assertTrue(callable(getattr(Frame, target, None)), f"no Frame method {target!r}")

    def test_the_action_names_are_unique(self):
        names = [name for _title, entries in MENUS for _label, name, _accelerator, _target in entries]
        self.assertEqual(len(names), len(set(names)), "duplicate action names in the menu bar")

    def test_the_menus_offer_the_items_of_the_former_gtk3_window(self):
        self.assertIn("Save", _menu_labels("File"))
        self.assertIn("Toggle Breakpoint", _menu_labels("Run"))
        self.assertIn("Find...", _menu_labels("Edit"))
        self.assertIn("Local History", _menu_labels("Edit"))
        self.assertIn("Show Git Changes", _menu_labels("Tools"))
        self.assertIn("About", _menu_labels("Help"))


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class ToolbarIconTests(FrameTestCase):
    def test_every_toolbar_icon_resolves_in_the_icon_theme_of_the_frame(self):
        self.frame()  # the frame sets its icon theme
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        # GTK draws the symbolic variant of a name the theme has only in that form (as Adwaita does)
        missing = [icon for item in TOOLBAR if item not in (None, "spacer")
                   for icon, _tooltip, _target in [item]
                   if not (theme.has_icon(icon) or theme.has_icon(icon + "-symbolic"))]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
