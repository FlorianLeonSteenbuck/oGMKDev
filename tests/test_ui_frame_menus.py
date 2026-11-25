"""The menu bar of the frame: every entry names a Frame method or a Howl command, so that a menu item cannot
point at nothing, and the action names are unique.

Needs PyGObject with GTK 4; otherwise it is skipped. No display is needed: the frame is not created.
"""

import unittest

try:
    import gi

    gi.require_version("Gtk", "4.0")

    from ogmkdev.frame.menus import MENUS  # noqa: E402
    from ogmkdev.frame.window import Frame  # noqa: E402

    GTK_AVAILABLE = True
except Exception:  # pragma: no cover - reported as a skip
    GTK_AVAILABLE = False


@unittest.skipUnless(GTK_AVAILABLE, "needs PyGObject with GTK 4")
class MenuTargetTests(unittest.TestCase):
    def test_every_menu_entry_names_a_frame_method_or_a_howl_command(self):
        for title, entries in MENUS:
            for label, _name, _accelerator, target in entries:
                if target.startswith("howl:"):
                    continue
                with self.subTest(menu=title, item=label):
                    self.assertTrue(callable(getattr(Frame, target, None)), f"no Frame method {target!r}")

    def test_the_action_names_are_unique(self):
        names = [name for _title, entries in MENUS for _label, name, _accelerator, _target in entries]
        self.assertEqual(len(names), len(set(names)), "duplicate action names in the menu bar")


if __name__ == "__main__":
    unittest.main()
