"""Panels of the frame: History (local history of the open file, patch sets), Hierarchy and Watches
(placeholders until their backend is wired), Problems, Search in files."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import htmldoc  # noqa: E402
from .. import editing, languages, organize  # noqa: E402
from .classdiagram import ClassDiagram  # noqa: E402
from .theme import palette_for  # noqa: E402
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
        self.hierarchy_store = Gtk.TreeStore(str, str, str, object)  # name, kind, where, (file, line)
        self.hierarchy_view = Gtk.TreeView(model=self.hierarchy_store)
        for index, heading in enumerate(("Name", "Kind", "File")):
            self.hierarchy_view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
        self.hierarchy_view.connect("row-activated", self._on_hierarchy_activated)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label="Place the cursor on a class, then Tools > Show Type Hierarchy.", xalign=0,
                             wrap=True))
        self.class_diagram = ClassDiagram(lambda path, line, column: self.open_file(path, line, column))
        self.class_diagram.set_palette(palette_for(self.mode, self.scheme))
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)  # the tree above, the diagram below
        paned.set_start_child(_scrolled(self.hierarchy_view))
        paned.set_end_child(self.class_diagram)
        paned.set_position(240)
        paned.set_vexpand(True)
        box.append(paned)
        self.hierarchy_box = box
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

    def organize_imports(self) -> None:
        """Edit > Organize Imports: the use statements of the open PHP file are merged, sorted and the unused
        ones dropped. The file is saved first and rewritten; the Howl buffer then reloads it."""
        info = self.editors.status()
        path = info["path"] if info else None
        if not path or not os.path.isfile(path):
            self.set_status("open a PHP file first")
            return
        if languages.detect_file(path).language != "php":
            self.set_status("organise imports works on PHP files")
            return
        self.editors.command("save")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        organised = organize.organize(text)
        if organised == text:
            self.set_status("imports are already organised")
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(organised)
        self.editors.command("buffer-reload")
        self.set_status("imports organised")

    def _apply_save_settings(self, path: str) -> Optional[float]:
        """The EditorConfig line handling of a saved file (trailing whitespace, final newline, line endings,
        charset): the file is written again when it differs, and the focused buffer reloads it. Returns the
        modification time of the rewritten file, None when nothing changed or the file is not UTF-8 text."""
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        settings = self._settings_for(path)
        if settings.charset == "utf-8-bom":
            text = text.removeprefix("﻿")  # encode_for_save writes the byte order mark itself
        encoded = editing.encode_for_save(text, settings)
        if encoded == raw:
            return None
        with open(path, "wb") as handle:
            handle.write(encoded)
        info = self.editors.status()
        if info and info["path"] == path:
            self.editors.command("buffer-reload")
        return os.path.getmtime(path)

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
            if previous is not None:  # a save: the EditorConfig line handling applies to what was written
                seen[path] = self._apply_save_settings(path) or stamp
            with open(path, encoding="utf-8", errors="replace") as handle:
                self.local_history.snapshot(path, handle.read(), "opened" if previous is None else "save")
            # a saved file is indexed again, so definitions and the hierarchy follow the change
            if previous is not None and getattr(self, "index", None) is not None:
                self.index.invalidate(path)
        if changed or path != self._history_path:
            self._history_path = path
            self.refresh_history()
            self.refresh_problems(path)

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

    def show_local_history(self) -> None:
        """Edit > Local History: the History tab of the left panel, with the revisions of the open file."""
        self._history_path = self.area.current_path()
        self.refresh_history()
        self.left.set_current_page(self.left.page_num(self.history_box))

    def export_history_patch(self) -> None:
        """Edit > Export History as Patch: every revision of the open file's local history, as one patch."""
        path = self.area.current_path()
        if not path:
            self.set_status("the file has no history yet")
            return
        revisions = self.local_history.revisions(path)
        if len(revisions) < 2:
            self.set_status("the history has no change to export yet")
            return
        self._patch_native = Gtk.FileChooserNative.new("Export History as Patch", self,
                                                       Gtk.FileChooserAction.SAVE, "Save", "Cancel")
        self._patch_native.set_current_name(os.path.basename(path) + ".patch")
        self._patch_native.connect("response", lambda native, response: self._write_patch(native, response,
                                                                                         revisions))
        self._patch_native.show()

    def export_documentation(self) -> None:
        """Asks for a folder and writes the declarations of the index with their doc comments there as HTML."""
        self._ensure_index()
        self._docs_native = Gtk.FileChooserNative.new("Export Documentation", self,
                                                      Gtk.FileChooserAction.SELECT_FOLDER, "Export", "Cancel")
        self._docs_native.connect("response", self._write_documentation)
        self._docs_native.show()

    def _write_documentation(self, native, response) -> None:
        if response != Gtk.ResponseType.ACCEPT or not native.get_file():
            return
        folder = native.get_file().get_path()
        result = htmldoc.export(self.index, folder, title=os.path.basename(self.folder) or "Documentation")
        self.set_status(f"documentation: {result.declarations} declarations, {result.documented} with a doc "
                        f"comment, written to {folder} (open index.html)")

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
        """The local variables of the stopped program and the watch expressions, in one table (see
        DebugMixin). A watch is typed in the entry and stays in the list across sessions."""
        self._watch_list: List[str] = []
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.watch_entry = Gtk.Entry(placeholder_text="watch expression (Enter adds it)", hexpand=True)
        self.watch_entry.connect("activate", self._on_watch_activate)
        remove = Gtk.Button(label="Remove Watch")
        remove.connect("clicked", self._on_remove_watch)
        row.append(self.watch_entry)
        row.append(remove)
        self.variables_store, self.variables_view = _list(("Kind", "Name", "Value"))
        box.append(row)
        box.append(_scrolled(self.variables_view))
        self.bottom.append_page(box, Gtk.Label(label="Variables"))

    def _on_watch_activate(self, entry: Gtk.Entry) -> None:
        expression = entry.get_text().strip()
        entry.set_text("")
        if expression:
            self.add_watch_expression(expression)

    def _on_remove_watch(self, _button: Gtk.Button) -> None:
        model, iterator = self.variables_view.get_selection().get_selected()
        if iterator is None or model[iterator][0] != "watch":
            self.set_status("select a watch in the Variables tab to remove it")
            return
        self.remove_watch_expression(model[iterator][1])

    # -------------------------------------------------- Problems, Search

    def _build_problems(self) -> None:
        self.problems_store, self.problems_view = _list(("Severity", "Message", "Where"))
        self.problems_view.connect("row-activated", self._on_problem_activated)
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
        target = row[2]  # the file of the match (the store keeps it in its object column)
        line = int(where.rsplit(":", 1)[1]) if where.rsplit(":", 1)[-1].isdigit() else 1
        self.open_file(target, line, 1)

    def focus_find(self) -> None:
        self.find_entry.grab_focus()
