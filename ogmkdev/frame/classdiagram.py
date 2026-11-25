"""The class diagram of the Hierarchy tab (GTK 4): one column per inheritance level, the selected class in
the middle, supertypes to the left and subtypes to the right. Each class is a button that opens its
declaration; an arrow sits between a type and its supertype. The geometry comes from :mod:`ogmkdev.diagram`.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import diagram as geometry  # noqa: E402


class ClassDiagram(Gtk.ScrolledWindow):
    def __init__(self, on_activate: Callable[[str, int, int], None]) -> None:
        super().__init__()
        self.grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        for side in ("margin_start", "margin_end", "margin_top", "margin_bottom"):
            getattr(self.grid, f"set_{side}")(12)
        self.set_child(self.grid)
        self.set_vexpand(True)
        self._on_activate = on_activate
        self.boxes: list = []
        self.edges: list = []

    def show(self, tree: dict) -> None:
        child = self.grid.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.grid.remove(child)
            child = following
        self.boxes, self.edges, _size = geometry.layout(tree)
        by_name = {box.name: box for box in self.boxes}
        for box in self.boxes:
            label = box.name.rsplit("\\", 1)[-1]
            text = f"<b>{GLib.markup_escape_text(label)}</b>" if box.root else GLib.markup_escape_text(label)
            caption = Gtk.Label(xalign=0)
            caption.set_markup(f"{text}\n<small>{GLib.markup_escape_text(box.kind)}</small>")
            button = Gtk.Button()
            button.set_child(caption)
            button.set_tooltip_text(box.name)
            button.connect("clicked", lambda _button, target=box: self._activate(target))
            self.grid.attach(button, 2 * box.grid_column, box.grid_row, 1, 1)
        for edge in self.edges:
            child_box, parent_box = by_name.get(edge.child), by_name.get(edge.parent)
            if child_box is None or parent_box is None:
                continue
            arrow = Gtk.Label(label="◁──")
            self.grid.attach(arrow, 2 * min(child_box.grid_column, parent_box.grid_column) + 1,
                             child_box.grid_row, 1, 1)

    def _activate(self, box) -> None:
        if box.file:
            self._on_activate(box.file, box.line, box.column)
