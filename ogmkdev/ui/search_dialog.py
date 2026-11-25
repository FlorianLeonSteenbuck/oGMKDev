"""Search Everywhere and Quick Open: a dialog whose list narrows while you type (Up/Down to move)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from .. import search_everywhere as search  # noqa: E402


class SearchDialog(Gtk.Dialog):
    def __init__(self, parent, title: str, candidates, categories, activate) -> None:
        super().__init__(title=title, transient_for=parent, modal=True, destroy_with_parent=True)
        self.set_default_size(680, 460)
        self.candidates = list(candidates)
        self.categories = categories
        self._activate = activate
        self.entry = Gtk.SearchEntry(placeholder_text="Type to filter, Enter to open, Up/Down to move")
        self.store = Gtk.ListStore(str, str, str, object)   # kind, name, where, candidate
        self.view = Gtk.TreeView(model=self.store)
        for index, heading in enumerate(("Kind", "Name", "Where")):
            self.view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
        self.entry.connect("changed", lambda *_: self.update_results())
        self.entry.connect("activate", lambda *_: self.activate_selected())
        self.entry.connect("key-press-event", self._on_entry_key)
        self.view.connect("row-activated", lambda *_: self.activate_selected())
        scroller = Gtk.ScrolledWindow()
        scroller.add(self.view)
        content = self.get_content_area()
        content.pack_start(self.entry, False, False, 6)
        content.pack_start(scroller, True, True, 0)
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        self.connect("response", lambda *_: self.destroy())
        self.update_results()

    def update_results(self) -> None:
        self.store.clear()
        for candidate in search.rank(self.candidates, self.entry.get_text(), self.categories):
            self.store.append([candidate.category, candidate.label, candidate.detail, candidate])
        if len(self.store):
            self.view.get_selection().select_path(Gtk.TreePath.new_first())

    def selected(self):
        model, iterator = self.view.get_selection().get_selected()
        return model[iterator][3] if iterator is not None else None

    def move(self, step: int) -> None:
        if not len(self.store):
            return
        _model, iterator = self.view.get_selection().get_selected()
        current = self.store.get_path(iterator).get_indices()[0] if iterator is not None else -1
        path = Gtk.TreePath.new_from_indices([min(max(current + step, 0), len(self.store) - 1)])
        self.view.get_selection().select_path(path)
        self.view.scroll_to_cell(path, None, False, 0.0, 0.0)

    def _on_entry_key(self, _entry, event) -> bool:
        if event.keyval == Gdk.KEY_Down:
            self.move(1)
            return True
        if event.keyval == Gdk.KEY_Up:
            self.move(-1)
            return True
        return False

    def activate_selected(self) -> None:
        candidate = self.selected()
        if candidate is None:
            return
        self.destroy()
        self._activate(candidate)
