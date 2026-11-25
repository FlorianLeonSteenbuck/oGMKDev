"""Panels of the frame: History (local history of the open file, patch sets), Hierarchy and Watches
(placeholders until their backend is wired), Problems, Search in files."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..history import LocalHistory  # noqa: E402
from ..workspace import workspace_files  # noqa: E402
from .panels import _scrolled, _text_view  # noqa: E402

MAX_RESULTS = 500


def _list(headings) -> tuple:
    store = Gtk.ListStore(*([str] * len(headings)), object)
    view = Gtk.TreeView(model=store)
    for index, heading in enumerate(headings):
        view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
    return store, view


class ToolsMixin:
    """Window methods of the panels; uses ``left``, ``bottom``, ``area``, ``folder``, ``set_status``."""

    # --------------------------------------------------------- Hierarchy

    def _build_hierarchy(self) -> None:
        self.hierarchy_store, self.hierarchy_view = _list(("Name", "Kind", "File"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label="Place the cursor on a class, then Tools > Show Type Hierarchy.", xalign=0,
                             wrap=True))
        box.append(_scrolled(self.hierarchy_view))
        self.left.append_page(box, Gtk.Label(label="Hierarchy"))

    # ----------------------------------------------------------- History

    def _build_history(self) -> None:
        self.local_history = LocalHistory()
        self._history_path: Optional[str] = None
        self._revisions: Dict[str, object] = {}
        self.hist_store = Gtk.ListStore(str, str, str, str)  # label, when, size, revision id
        self.hist_view = Gtk.TreeView(model=self.hist_store)
        selection = self.hist_view.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        selection.connect("changed", lambda *_: self._show_history_diff())
        for index, heading in enumerate(("Label", "When", "Size")):
            self.hist_view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
        self.hist_diff = _text_view()
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_start_child(_scrolled(self.hist_view))
        paned.set_end_child(_scrolled(self.hist_diff))
        paned.set_position(200)
        paned.set_vexpand(True)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, handler in (("Extract patch set...", self.extract_patch_set),
                               ("Revert to selected", self.revert_to_selected)):
            button = Gtk.Button(label=label)
            button.set_hexpand(True)
            button.connect("clicked", lambda _b, h=handler: h())
            buttons.append(button)
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.history_box.append(buttons)
        self.history_box.append(paned)
        self.left.append_page(self.history_box, Gtk.Label(label="History"))

    def track_history(self, path: Optional[str]) -> None:
        """Keeps a snapshot of the open file each time it changes on disk (saves), and shows its history."""
        if not path or not os.path.isfile(path):
            return
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            return
        seen = getattr(self, "_mtimes", None)
        if seen is None:
            seen = self._mtimes = {}
        previous = seen.get(path)
        changed = previous != stamp
        if changed:
            seen[path] = stamp
            with open(path, encoding="utf-8", errors="replace") as handle:
                self.local_history.snapshot(path, handle.read(), "opened" if previous is None else "save")
        if changed or path != self._history_path:
            self._history_path = path
            self.refresh_history()

    def refresh_history(self) -> None:
        if not hasattr(self, "hist_store"):
            return
        self.hist_store.clear()
        self._revisions = {}
        if not self._history_path:
            self.hist_diff.get_buffer().set_text("open a file to see its history")
            return
        for revision in reversed(self.local_history.revisions(self._history_path)):
            self._revisions[revision.id] = revision
            self.hist_store.append([revision.label, revision.when, str(revision.size), revision.id])
        if len(self.hist_store):
            self.hist_view.get_selection().select_path(self.hist_store.get_path(self.hist_store.get_iter_first()))

    def _selected_revisions(self) -> list:
        if not hasattr(self, "hist_view"):
            return []
        model, paths = self.hist_view.get_selection().get_selected_rows()
        return [self._revisions[model[path][3]] for path in paths if model[path][3] in self._revisions]

    def _show_history_diff(self) -> None:
        if not self._history_path:
            return
        selected = self._selected_revisions()
        if not selected:
            self.hist_diff.get_buffer().set_text("")
            return
        if len(selected) == 1:
            with open(self._history_path, encoding="utf-8", errors="replace") as handle:
                current = handle.read()
            text = LocalHistory.diff(self.local_history.content(selected[0]), current,
                                     f"revision {selected[0].when}", "current")
        else:
            text = self.local_history.patch_set(selected, self.folder)
        self.hist_diff.get_buffer().set_text(text or "no differences")

    def extract_patch_set(self) -> None:
        if not self._history_path:
            self.set_status("open a file first")
            return
        revisions = self._selected_revisions() or list(self._revisions.values())
        if not revisions:
            self.set_status("no revisions to extract")
            return
        self._patch_native = Gtk.FileChooserNative.new("Extract Patch Set", self, Gtk.FileChooserAction.SAVE,
                                                       "Save", "Cancel")
        self._patch_native.set_current_name(os.path.basename(self._history_path) + ".patch")
        self._patch_native.connect("response", lambda native, response: self._write_patch(native, response,
                                                                                         revisions))
        self._patch_native.show()

    def _write_patch(self, native, response, revisions) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file():
            filename = native.get_file().get_path()
            self.local_history.extract_patch(revisions, filename, self.folder)
            self.set_status(f"patch set of {len(revisions)} revision(s) written to {filename}")

    def revert_to_selected(self) -> None:
        selected = self._selected_revisions()
        if not self._history_path or len(selected) != 1:
            self.set_status("select exactly one revision to revert to")
            return
        content = self.local_history.content(selected[0])
        with open(self._history_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.editors.command("buffer-reload")
        self.set_status(f"reverted to {selected[0].when} (written to the file and reloaded)")

    # --------------------------------------------------------- Watches

    def _build_watches(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.watch_entry = Gtk.Entry(placeholder_text="watch expression (the debugger is not wired yet)")
        self.watch_label = Gtk.Label(xalign=0)
        box.append(self.watch_entry)
        box.append(self.watch_label)
        self.bottom.append_page(box, Gtk.Label(label="Watches"))

    # -------------------------------------------------- Problems, Search

    def _build_problems(self) -> None:
        self.problems_store, self.problems_view = _list(("Severity", "Message", "Where"))
        self.bottom.append_page(_scrolled(self.problems_view), Gtk.Label(label="Problems"))

    def _build_search(self) -> None:
        self.search_store, self.search_view = _list(("Where", "Text"))
        self.search_view.connect("row-activated", self._on_search_activated)
        self.search_page = _scrolled(self.search_view)
        self.bottom.append_page(self.search_page, Gtk.Label(label="Search"))

    def search_in_files(self, text: Optional[str] = None) -> None:
        term = (text if text is not None else self.find_entry.get_text()).strip()
        if not term:
            self.set_status("type a text in the search field below the editors")
            return
        needle = term.lower()
        self.search_store.clear()
        found = 0
        for path in workspace_files(self.workspace):
            try:
                with open(path, encoding="utf-8") as handle:
                    lines = handle.readlines()
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(lines, 1):
                if needle in line.lower():
                    found += 1
                    if found <= MAX_RESULTS:
                        where = f"{os.path.relpath(path, self.folder)}:{number}"
                        self.search_store.append([where, line.strip()[:200], path])
        self.bottom.set_current_page(self.bottom.page_num(self.search_page))
        self.set_status(f"{found} match(es) for {term!r}")

    def _on_search_activated(self, _view, path, _column) -> None:
        row = self.search_store[self.search_store.get_iter(path)]
        where = row[0]
        target = row[len(row) - 1]
        line = int(where.rsplit(":", 1)[1]) if where.rsplit(":", 1)[-1].isdigit() else 1
        self.open_file(target, line, 1)

    def focus_find(self) -> None:
        self.find_entry.grab_focus()
