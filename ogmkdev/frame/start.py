"""The start window: the projects opened last, offered when the frame starts without a folder and without files.

The window only reports the folder that was chosen. The owner makes the frame for it and closes the window: a window that
closes first, as the last one of the application, would end the application before the frame exists.
"""

from __future__ import annotations

import os
from typing import Callable, List, Mapping, Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

APP_TITLE = "oGMKDev"


class StartWindow(Gtk.ApplicationWindow):
    """One row per folder: its name, its path and the time it was opened last. Enter or a double click opens the row,
    Open Folder... chooses another folder, Cancel closes the window without a choice."""

    def __init__(self, application: Gtk.Application, folders: Sequence[str], opened: Mapping[str, str],
                 on_chosen: Callable[[str], None]) -> None:
        super().__init__(application=application, title=APP_TITLE)
        self.set_default_size(640, 420)
        self._folders: List[str] = list(folders)
        self._on_chosen = on_chosen
        self._native = None  # the folder chooser while it is open

        heading = Gtk.Label(label="Open a project", xalign=0)
        heading.add_css_class("title-3")
        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for folder in self._folders:
            self.list.append(self._row(folder, opened.get(folder, "")))
        self.list.connect("row-activated", lambda _list, row: self.choose(row.get_index()))
        if self._folders:
            self.list.select_row(self.list.get_row_at_index(0))
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.list)

        other = Gtk.Button(label="Open Folder...")
        other.connect("clicked", lambda _button: self._open_other())
        open_selected = Gtk.Button(label="Open")
        open_selected.add_css_class("suggested-action")
        open_selected.connect("clicked", lambda _button: self._choose_selected())
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _button: self.destroy())
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
        for button in (other, cancel, open_selected):
            buttons.append(button)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for margin in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{margin}")(12)
        box.append(heading)
        box.append(scroller)
        box.append(buttons)
        self.set_child(box)

    def _row(self, folder: str, opened: str) -> Gtk.ListBoxRow:
        line = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for margin in ("start", "end", "top", "bottom"):
            getattr(line, f"set_margin_{margin}")(6)
        name = Gtk.Label(xalign=0)
        name.set_markup(f"<b>{GLib.markup_escape_text(os.path.basename(folder.rstrip(os.sep)) or folder)}</b>")
        where = folder + (f"   opened {opened.replace('T', ' ')}" if opened else "")
        path = Gtk.Label(label=where, xalign=0)
        path.add_css_class("dim-label")
        line.append(name)
        line.append(path)
        row = Gtk.ListBoxRow()
        row.set_child(line)
        return row

    def choose(self, index: int) -> None:
        """Hands the folder of row ``index`` to the owner."""
        if 0 <= index < len(self._folders):
            self._on_chosen(self._folders[index])

    def _choose_selected(self) -> None:
        row = self.list.get_selected_row()
        if row is not None:
            self.choose(row.get_index())

    def _open_other(self) -> None:
        native = Gtk.FileChooserNative.new("Open Folder", self, Gtk.FileChooserAction.SELECT_FOLDER, "Open", "Cancel")
        self._native = native  # kept until the dialog answers
        native.connect("response", self._on_other_response)
        native.show()

    def _on_other_response(self, native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            self._on_chosen(native.get_file().get_path())
        self._native = None
