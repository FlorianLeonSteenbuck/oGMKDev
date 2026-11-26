"""The Structure tab of a JavaScript or TypeScript file: the outline in the tab, a row opens the line of its name,
the outline is read when the tab is shown, and a file with a syntax error says why it has no outline.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import unittest

from gi.repository import Gtk  # noqa: E402

from tests.frame_support import FrameTestCase, GTK_AVAILABLE, SKIP_REASON, pump_until, write

SOURCE = ("export class Animal extends Base {\n"
          "  static count = 0;\n"
          "  get size() { return 1; }\n"
          "  speak() { return 1; }\n"
          "}\n"
          "export function greet(who) { return who; }\n"
          "const shout = (text) => text;\n")


def _rows(frame):
    """The labels of the Structure tab, every row and its children in tree order."""
    rows = []
    frame.structure_store.foreach(lambda model, _path, iterator: rows.append(model[iterator][0]))
    return rows


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class OutlineTabTests(FrameTestCase):
    def test_the_tab_lists_the_outline_and_a_row_opens_the_line_of_its_name(self):
        path = write(self.folder, "animal.js", SOURCE)
        frame = self.frame([path])
        self.focus(frame, path)
        frame.show_structure()
        self.assertEqual(_rows(frame), ["class Animal", "static count", "get size", "speak()",
                                        "function greet", "const shout"])
        self.assertEqual(frame.structure_hint.get_text(), "6 declaration(s) in animal.js")
        frame._on_structure_activated(frame.structure_view, Gtk.TreePath.new_from_string("1"), None)
        self.assertTrue(pump_until(lambda: (frame.editors.status() or {}).get("line") == 6))

    def test_the_outline_is_read_when_its_tab_is_shown(self):
        path = write(self.folder, "animal.js", SOURCE)
        frame = self.frame([path])
        self.focus(frame, path)
        frame._follow_structure(path)
        self.assertEqual(_rows(frame), [])  # the tab is not shown, so nothing is parsed
        frame.left.set_current_page(frame.left.page_num(frame.structure_box))
        frame._follow_structure(path)
        self.assertEqual(len(_rows(frame)), 6)

    def test_a_typescript_file_is_outlined_with_its_types(self):
        path = write(self.folder, "shape.ts", "export interface Shape { area(): number }\n")
        frame = self.frame([path])
        self.focus(frame, path)
        frame.show_structure()
        self.assertEqual(_rows(frame), ["interface Shape", "area()"])

    def test_a_file_with_a_syntax_error_says_why_it_has_no_outline(self):
        path = write(self.folder, "broken.js", "class A {\n  broken(\n}\n")
        frame = self.frame([path])
        self.focus(frame, path)
        frame.show_structure()
        self.assertEqual(_rows(frame), [])
        self.assertTrue(frame.structure_hint.get_text().startswith("broken.js: no outline, syntax error at line 3"))


if __name__ == "__main__":
    unittest.main()
