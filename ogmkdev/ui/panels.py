"""Result panels: a flat result list, a clickable type hierarchy and a class diagram (GTK 3 widgets).

No drawing library is needed: the diagram is a grid of buttons, one column per inheritance level.
"""

from __future__ import annotations

from typing import Callable, Iterable, Tuple

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


class ResultsView(Gtk.ScrolledWindow):
    """Rows of (primary text, location text, file, line, column); activation calls back with the location."""

    def __init__(self, on_activate: Callable[[str, int, int], None], first_column: str = "Result") -> None:
        super().__init__()
        self.store = Gtk.ListStore(str, str, str, int, int)
        self.view = Gtk.TreeView(model=self.store)
        self.view.append_column(Gtk.TreeViewColumn(first_column, Gtk.CellRendererText(), text=0))
        self.view.append_column(Gtk.TreeViewColumn("Location", Gtk.CellRendererText(), text=1))
        self.view.connect("row-activated", self._activated)
        self._on_activate = on_activate
        self.add(self.view)

    def show(self, rows: Iterable[Tuple[str, str, str, int, int]]) -> int:
        self.store.clear()
        count = 0
        for row in rows:
            self.store.append(list(row))
            count += 1
        return count

    def _activated(self, _view, path, _column) -> None:
        row = self.store[path]
        self._on_activate(row[2], row[3], row[4])


class DiagramView(Gtk.ScrolledWindow):
    """Class diagram: one column per inheritance level, the selected class in the middle.

    Each class is a button that navigates to its declaration; arrows point from a type to its supertype.
    """

    def __init__(self, on_activate: Callable[[str, int, int], None]) -> None:
        super().__init__()
        from .. import diagram as _diagram
        self._diagram = _diagram
        self.grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        self.grid.set_border_width(12)
        self._on_activate = on_activate
        self.boxes: list = []
        self.edges: list = []
        self.add(self.grid)

    def show(self, tree: dict) -> None:
        for child in self.grid.get_children():
            self.grid.remove(child)
        self.boxes, self.edges, _size = self._diagram.layout(tree)
        by_name = {box.name: box for box in self.boxes}
        for box in self.boxes:
            label = box.name.rsplit("\\", 1)[-1]
            text = f"<b>{GLib.markup_escape_text(label)}</b>" if box.root else GLib.markup_escape_text(label)
            caption = Gtk.Label()
            caption.set_markup(f"{text}\n<small>{GLib.markup_escape_text(box.kind)}</small>")
            button = Gtk.Button()
            button.add(caption)
            button.set_tooltip_text(box.name)
            button.connect("clicked", lambda _b, target=box: self._activate(target))
            self.grid.attach(button, 2 * box.grid_column, box.grid_row, 1, 1)
        for edge in self.edges:
            child, parent = by_name.get(edge.child), by_name.get(edge.parent)
            if child is None or parent is None:
                continue
            arrow = Gtk.Label(label="◁──")
            self.grid.attach(arrow, 2 * min(child.grid_column, parent.grid_column) + 1, child.grid_row, 1, 1)
        self.grid.show_all()

    def _activate(self, box) -> None:
        if box.file:
            self._on_activate(box.file, box.line, box.column)


class HierarchyView(Gtk.ScrolledWindow):
    """Supertypes, subtypes and dependencies of one class as a tree; nodes with a file navigate on activation."""

    def __init__(self, on_activate: Callable[[str, int, int], None]) -> None:
        super().__init__()
        self.store = Gtk.TreeStore(str, str, int, int)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        self.view.append_column(Gtk.TreeViewColumn("Type", Gtk.CellRendererText(), text=0))
        self.view.connect("row-activated", self._activated)
        self._on_activate = on_activate
        self.add(self.view)

    def show(self, tree: dict, dependencies=()) -> None:
        self.store.clear()
        title = tree.get("name", "")
        root = self.store.append(None, [f"{title}", "", 0, 0])
        for heading, nodes in (("supertypes", tree.get("up", [])), ("subtypes", tree.get("down", []))):
            section = self.store.append(root, [heading, "", 0, 0])
            self._fill(section, nodes)
        section = self.store.append(root, ["dependencies", "", 0, 0])
        for name, file, line, column in dependencies:
            label = name if file else f"{name}  (external)"
            self.store.append(section, [label, file, line, column])
        self.view.expand_all()

    def _fill(self, parent, nodes) -> None:
        for node in nodes:
            symbol = node.get("symbol")
            file, line, column = (symbol.file, symbol.line, symbol.column) if symbol else ("", 0, 0)
            label = node["name"] if symbol else f"{node['name']}  (external)"
            child = self.store.append(parent, [label, file, line, column])
            self._fill(child, node.get("children", []))

    def _activated(self, _view, path, _column) -> None:
        row = self.store[path]
        if row[1]:
            self._on_activate(row[1], row[2], row[3])
