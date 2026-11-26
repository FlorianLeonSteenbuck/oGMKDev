"""The Resources tab of the frame: the memory and the threads of the IDE and of the running program, and the size of the
index, as text. The frame refreshes it while the tab is shown; the lines come from ogmkdev.resources."""

from __future__ import annotations

from typing import Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class ResourcesView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_monospace(True)
        self.view.set_left_margin(8)
        self.view.set_top_margin(8)
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.view)
        self.append(scroller)

    def show(self, lines: Sequence[str]) -> None:
        self.view.get_buffer().set_text("\n".join(lines))
