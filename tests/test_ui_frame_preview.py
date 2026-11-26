"""The Preview page of the bottom panel: a Markdown or BareDown file as formatted text (headings, emphasis, code,
lists, a picture for a Markdown image), an image of the project tree as the picture itself, a note for a file that has
no preview (an SVG among them), and a page that follows the file when it is saved.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import base64
import os
import unittest

from gi.repository import Gtk  # noqa: E402

from tests.frame_support import FrameTestCase, GTK_AVAILABLE, SKIP_REASON, pump_until, write

# a one-pixel PNG
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
NOTE = ("# Shape\nSome *italic* and **bold** text with `code`.\n\n- one\n- two\n\n"
        "```php\necho 1;\n```\n\n![logo](logo.png)\n")


def _buffer_text(frame):
    buffer = frame.preview_buffer
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)


def _tag_names_at(frame, word):
    """The names of the tags on the first character of ``word`` in the preview text."""
    text = _buffer_text(frame)
    index = text.index(word)
    iterator = frame.preview_buffer.get_iter_at_offset(index)
    return {tag.get_property("name") for tag in iterator.get_tags()}


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class PreviewPageTests(FrameTestCase):
    def test_markdown_is_shown_with_its_styles_and_its_picture(self):
        path = write(self.folder, "note.md", NOTE)
        write_png = os.path.join(self.folder, "logo.png")
        with open(write_png, "wb") as handle:
            handle.write(PNG)
        frame = self.frame(files=[path])
        frame.show_preview()
        self.assertEqual(frame.preview_stack.get_visible_child_name(), "text")
        self.assertIn("Shape", _buffer_text(frame))
        self.assertIn("heading-1", _tag_names_at(frame, "Shape"))
        self.assertIn("italic", _tag_names_at(frame, "italic"))
        self.assertIn("bold", _tag_names_at(frame, "bold"))
        self.assertIn("code", _tag_names_at(frame, "code"))
        self.assertIn("code-block", _tag_names_at(frame, "echo"))
        iterator = frame.preview_buffer.get_start_iter()  # the picture sits on an anchor of the text
        anchored = False
        while True:
            anchored = anchored or iterator.get_child_anchor() is not None
            if not iterator.forward_char():
                break
        self.assertTrue(anchored)
        children = []
        child = frame.preview_text.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        self.assertTrue(any(isinstance(widget, Gtk.Picture) for widget in children))

    def test_an_image_of_the_tree_is_shown_as_the_picture_and_stays_out_of_the_editor(self):
        path = os.path.join(self.folder, "logo.png")
        with open(path, "wb") as handle:
            handle.write(PNG)
        frame = self.frame()
        frame.open_file(path)
        self.assertTrue(pump_until(lambda: frame.preview_stack.get_visible_child_name() == "image", timeout=10))
        self.assertIn("1 × 1 px", frame.preview_info.get_text())
        self.assertNotEqual(frame.area.current_path(), path)  # Howl does not open a picture

    def test_an_svg_has_no_preview_and_opens_in_the_editor(self):
        path = write(self.folder, "icon.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>\n')
        frame = self.frame()
        frame.open_file(path)
        self.wait_for_file(frame, path)
        frame.show_preview()
        self.assertEqual(frame.preview_stack.get_visible_child_name(), "note")
        self.assertIn("No preview", frame.preview_note.get_text())

    def test_the_page_follows_the_file_when_it_is_saved(self):
        path = write(self.folder, "note.md", NOTE)
        frame = self.frame(files=[path])
        frame.show_preview()
        self.assertIn("Shape", _buffer_text(frame))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# Changed\nText.\n")
        stamp = os.path.getmtime(path) + 5
        os.utime(path, (stamp, stamp))
        frame._follow_preview()
        self.assertIn("Changed", _buffer_text(frame))
        self.assertNotIn("Shape", _buffer_text(frame))


if __name__ == "__main__":
    unittest.main()
