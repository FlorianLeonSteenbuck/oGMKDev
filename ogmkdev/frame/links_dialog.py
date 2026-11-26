"""The Linked Projects dialog: the projects linked to the current one. A link brings the linked project's folder into the
current project, now and whenever the current project is opened again. The links are kept in the projects file, the JSON
configuration of the program; a link does not change the other project.

The dialog gets its list and its actions from the frame. Failures are return values (see ogmkdev.outcome); the dialog
shows them.
"""

from __future__ import annotations

from typing import Callable, List, Union

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..outcome import Failure  # noqa: E402


class LinksDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, linked: Callable[[], List[str]],
                 link: Callable[[str], Union[str, Failure]], unlink: Callable[[str], Union[str, Failure]]) -> None:
        super().__init__(title="Linked Projects", transient_for=parent, modal=True)
        self.set_default_size(640, 360)
        self._linked = linked
        self._link = link
        self._unlink = unlink
        self._folders: List[str] = []  # the folder of each row, in row order
        self._native = None  # the folder chooser while it is open

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.list)
        explanation = Gtk.Label(xalign=0, wrap=True)
        explanation.set_text("A linked project's folder is part of this project whenever this project is opened.")
        self.message = Gtk.Label(xalign=0, wrap=True)
        self.message.add_css_class("dim-label")
        add = Gtk.Button(label="Link a Project...")
        add.connect("clicked", lambda _button: self._choose())
        remove = Gtk.Button(label="Unlink")
        remove.connect("clicked", lambda _button: self._unlink_selected())
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda _button: self.destroy())
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
        for button in (add, remove, close):
            buttons.append(button)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for margin in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{margin}")(12)
        box.append(explanation)
        box.append(scroller)
        box.append(self.message)
        box.append(buttons)
        self.set_child(box)
        self.reload()

    def reload(self) -> None:
        """Lists the folders of the linked projects."""
        while (row := self.list.get_row_at_index(0)) is not None:
            self.list.remove(row)
        self._folders = list(self._linked())
        for folder in self._folders:
            label = Gtk.Label(label=folder, xalign=0)
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            row = Gtk.ListBoxRow()
            row.set_child(label)
            self.list.append(row)
        if not self._folders:
            self.message.set_text("No project is linked to this one.")

    def _choose(self) -> None:
        native = Gtk.FileChooserNative.new("Link a Project", self, Gtk.FileChooserAction.SELECT_FOLDER, "Link", "Cancel")
        self._native = native  # kept until the dialog answers
        native.connect("response", self._on_chosen)
        native.show()

    def _on_chosen(self, native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            self._report(self._link(native.get_file().get_path()), "linked")
        self._native = None

    def _unlink_selected(self) -> None:
        row = self.list.get_selected_row()
        if row is None or row.get_index() >= len(self._folders):
            self.message.set_text("Select the project to unlink.")
            return
        self._report(self._unlink(self._folders[row.get_index()]), "unlinked")

    def _report(self, result: Union[str, Failure], done: str) -> None:
        self.message.set_text(str(result) if isinstance(result, Failure) else f"Project {done}.")
        self.reload()
