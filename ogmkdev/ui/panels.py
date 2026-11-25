"""Result panels: a flat result list and a clickable type hierarchy (GTK 3, no editor logic)."""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Tuple

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

Location = Tuple[str, int, int]


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


class HierarchyView(Gtk.ScrolledWindow):
    """Supertypes and subtypes of one class as a tree; nodes with a file navigate on activation."""

    def __init__(self, on_activate: Callable[[str, int, int], None]) -> None:
        super().__init__()
        self.store = Gtk.TreeStore(str, str, int, int)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        self.view.append_column(Gtk.TreeViewColumn("Type", Gtk.CellRendererText(), text=0))
        self.view.connect("row-activated", self._activated)
        self._on_activate = on_activate
        self.add(self.view)

    def show(self, tree: dict) -> None:
        self.store.clear()
        title = tree.get("name", "")
        root = self.store.append(None, [f"{title}", "", 0, 0])
        for heading, nodes in (("supertypes", tree.get("up", [])), ("subtypes", tree.get("down", []))):
            section = self.store.append(root, [heading, "", 0, 0])
            self._fill(section, nodes)
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
