"""The Preview page of the bottom panel: a Markdown or BareDown file as formatted text, an image file as the picture
itself. The page shows the saved text of the focused editor's file, or an image the project tree opened, and follows
the file while it is shown. A file without a preview (an SVG among them) gets a note: an SVG is text and stays in
the editor.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from .. import preview  # noqa: E402
from .panels import _scrolled  # noqa: E402

NOTE_NO_PREVIEW = ("No preview for this file. Markdown (.md), BareDown (.bd) and image files (PNG, JPEG, GIF, BMP, "
                   "WebP, TIFF, ICO) have one; an SVG is text and stays in the editor.")
NOTE_NO_FILE = "Open a Markdown, BareDown or image file to see its preview."
HEADING_SCALE = {1: 1.8, 2: 1.5, 3: 1.3, 4: 1.15, 5: 1.05, 6: 1.0}
IMAGE_WIDTH = 480  # an image in a Markdown text is at most this wide


def _rgba(red: float, green: float, blue: float, alpha: float) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red, color.green, color.blue, color.alpha = red, green, blue, alpha
    return color


# the look of the text: a tag per style, applied by name; the colours are translucent, so both themes read them
TAG_STYLES: Dict[str, Dict[str, object]] = {
    "bold": {"weight": 700},
    "italic": {"style": Pango.Style.ITALIC},
    "code": {"family": "monospace", "background-rgba": _rgba(0.5, 0.5, 0.5, 0.18)},
    "code-block": {"family": "monospace", "background-rgba": _rgba(0.5, 0.5, 0.5, 0.14),
                   "pixels-above-lines": 4, "pixels-below-lines": 4},
    "link": {"foreground": "#3b7dd8", "underline": Pango.Underline.SINGLE},
    "note": {"style": Pango.Style.ITALIC, "foreground": "#888888"},
    "rule": {"foreground": "#888888", "justification": Gtk.Justification.CENTER},
}


class PreviewMixin:
    """Window methods of the Preview page; uses ``bottom``, ``area`` and ``set_status``."""

    _preview_key: Optional[tuple] = None  # (path, modification time) of what the page shows
    _preview_pin: Optional[Tuple[str, Optional[str]]] = None  # an image the tree opened, and the editor it was opened with

    def _build_preview(self) -> None:
        self.preview_info = Gtk.Label(xalign=0)
        self.preview_info.set_margin_start(8)
        self.preview_info.set_margin_top(4)
        self.preview_text = Gtk.TextView(editable=False, cursor_visible=False)
        self.preview_text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.preview_text.set_left_margin(16)
        self.preview_text.set_right_margin(16)
        self.preview_text.set_top_margin(8)
        self.preview_text.set_bottom_margin(8)
        self.preview_buffer = self.preview_text.get_buffer()
        self.preview_picture = Gtk.Picture()
        self.preview_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview_note = Gtk.Label(wrap=True, xalign=0)
        self.preview_note.set_margin_start(8)
        self.preview_stack = Gtk.Stack()
        self.preview_stack.add_named(_scrolled(self.preview_text), "text")
        self.preview_stack.add_named(_scrolled(self.preview_picture), "image")
        self.preview_stack.add_named(self.preview_note, "note")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(self.preview_info)
        self.preview_stack.set_vexpand(True)
        box.append(self.preview_stack)
        self.preview_box = box
        self.bottom.append_page(box, Gtk.Label(label="Preview"))

    # ------------------------------------------------------------ showing

    def show_preview(self) -> None:
        """Tools > Show Preview: the Preview page, with the file of the focused editor."""
        self._preview_pin = None
        self._preview_key = None
        self._refresh_preview()
        self.bottom.set_current_page(self.bottom.page_num(self.preview_box))

    def preview_image(self, path: str) -> None:
        """An image the project tree opened: the Preview page shows it, and the focused editor stays as it is."""
        self._preview_pin = (path, self.area.current_path())
        self._preview_key = None
        self._refresh_preview()
        self.bottom.set_current_page(self.bottom.page_num(self.preview_box))

    def _follow_preview(self) -> None:
        """Called on every poll: while the page is shown, it follows the file and its saves."""
        if self.bottom.get_current_page() == self.bottom.page_num(self.preview_box):
            self._refresh_preview()

    def _preview_path(self) -> Optional[str]:
        pin = self._preview_pin
        if pin is not None:
            if pin[1] == self.area.current_path():
                return pin[0]
            self._preview_pin = None  # another editor is focused: the image was opened next to the earlier one
        return self.area.current_path()

    def _refresh_preview(self) -> None:
        path = self._preview_path()
        key = None
        if path and os.path.isfile(path):
            try:
                key = (path, os.path.getmtime(path))
            except OSError:
                key = None
        if key == self._preview_key and key is not None:
            return
        self._preview_key = key
        if not path:
            self.preview_info.set_text("")
            self._show_note(NOTE_NO_FILE)
            return
        kind = preview.kind_of(path)
        if kind is None or not os.path.isfile(path):
            self.preview_info.set_text(os.path.basename(path))
            self._show_note(NOTE_NO_PREVIEW)
        elif kind == "image":
            self._show_image(path)
        else:
            self._show_text(path, kind)

    def _show_note(self, text: str) -> None:
        self.preview_note.set_text(text)
        self.preview_stack.set_visible_child_name("note")

    def _show_image(self, path: str) -> None:
        try:
            texture = Gdk.Texture.new_from_filename(path)
        except GLib.Error as error:
            self.preview_info.set_text(os.path.basename(path))
            self._show_note(f"Cannot show {os.path.basename(path)}: {error.message}")
            return
        self.preview_picture.set_paintable(texture)
        self.preview_info.set_text(f"{os.path.basename(path)}   {texture.get_width()} × {texture.get_height()} px")
        self.preview_stack.set_visible_child_name("image")

    def _show_text(self, path: str, kind: str) -> None:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:  # the file went away between the check and the read
            self._show_note(NOTE_NO_FILE)
            return
        self.preview_info.set_text(os.path.basename(path))
        self._render(preview.blocks_of(kind, text), os.path.dirname(path))
        self.preview_stack.set_visible_child_name("text")

    # ------------------------------------------------------------ drawing the blocks

    def _tag(self, name: str, properties: Optional[Dict[str, object]] = None) -> Gtk.TextTag:
        """The text tag of a name, created with its properties the first time it is needed."""
        table = self.preview_buffer.get_tag_table()
        tag = table.lookup(name)
        if tag is None:
            tag = self.preview_buffer.create_tag(name)
            for key, value in (properties or {}).items():
                tag.set_property(key, value)
        return tag

    def _style_tag(self, name: str) -> Gtk.TextTag:
        return self._tag(name, TAG_STYLES[name])

    def _insert(self, text: str, tags: List[Gtk.TextTag]) -> None:
        self.preview_buffer.insert_with_tags(self.preview_buffer.get_end_iter(), text, *tags)

    def _block_tags(self, block: preview.Block) -> List[Gtk.TextTag]:
        """The margins of a block: its quote depth, and for an item its nesting and a hanging indent for the bullet."""
        item = block.kind in ("bullet", "ordered")
        left = 24 * block.quote + 20 * block.depth + (24 if item else 0)
        hanging = -14 if item else 0
        if not left and not hanging:
            return []
        return [self._tag(f"margin-{left}-{hanging}", {"left-margin": left, "indent": hanging})]

    def _span_tags(self, span: preview.Span) -> List[Gtk.TextTag]:
        tags: List[Gtk.TextTag] = []
        if span.image:
            tags.append(self._style_tag("note"))
            return tags
        if span.code:
            tags.append(self._style_tag("code"))
        if span.bold:
            tags.append(self._style_tag("bold"))
        if span.italic:
            tags.append(self._style_tag("italic"))
        if span.target:
            tags.append(self._style_tag("link"))
        return tags

    def _render(self, blocks: List[preview.Block], base: str) -> None:
        """Writes the blocks into the text view; an image of a Markdown text is a picture placed in the text."""
        self.preview_buffer.set_text("")  # also takes out the pictures of the text before
        ordered = 0  # the number of the last ordered item; a Markdown item keeps its own number
        for block in blocks:
            if block.kind == "ordered":
                ordered = block.number or ordered + 1
            else:
                ordered = 0
            margin = self._block_tags(block)
            if block.kind == "heading":
                level = min(max(block.level, 1), 6)
                heading = self._tag(f"heading-{level}", {"scale": HEADING_SCALE[level], "weight": 700,
                                                         "pixels-above-lines": 12, "pixels-below-lines": 4})
                self._spans(block.spans, margin + [heading])
                self._insert("\n", margin)
            elif block.kind in ("paragraph", "quote"):
                self._spans(block.spans, margin)
                self._insert("\n\n", margin)
            elif block.kind == "bullet":
                self._insert("•  ", margin)
                self._spans(block.spans, margin)
                self._insert("\n", margin)
            elif block.kind == "ordered":
                self._insert(f"{ordered}.  ", margin)
                self._spans(block.spans, margin)
                self._insert("\n", margin)
            elif block.kind == "code":
                self._insert(block.text + "\n\n", margin + [self._style_tag("code-block")])
            elif block.kind == "rule":
                self._insert("─" * 48 + "\n\n", [self._style_tag("rule")])
            elif block.kind == "image":
                self._image(block, base, margin)

    def _spans(self, spans: Tuple[preview.Span, ...], margin: List[Gtk.TextTag]) -> None:
        for span in spans:
            self._insert(span.text, margin + self._span_tags(span))

    def _image(self, block: preview.Block, base: str, margin: List[Gtk.TextTag]) -> None:
        source = os.path.join(base, block.target)
        extension = os.path.splitext(source)[1].lower()
        if extension in preview.IMAGE_EXTENSIONS and os.path.isfile(source):
            width, height = IMAGE_WIDTH, -1
            try:
                texture = Gdk.Texture.new_from_filename(source)
                scale = min(1.0, IMAGE_WIDTH / max(texture.get_width(), 1))
                width, height = int(texture.get_width() * scale), int(texture.get_height() * scale)
            except GLib.Error:
                pass
            anchor = self.preview_buffer.create_child_anchor(self.preview_buffer.get_end_iter())
            picture = Gtk.Picture.new_for_filename(source)
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_size_request(width, height)
            self.preview_text.add_child_at_anchor(picture, anchor)
            self._insert("\n\n", margin)
            return
        label = f"[SVG image: {block.target}]" if extension == ".svg" else f"[image: {block.text or block.target}]"
        self._insert(label + "\n\n", margin + [self._style_tag("note")])
