"""The Index tab of the frame: the index as bars per folder. Each project folder is a row, and each folder directly below one
too. The bars of the files, the symbols and the references are scaled to the largest value of their column, and each bar
shows its number. The numbers come from ogmkdev.overview."""

from __future__ import annotations

from typing import List, Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from ..overview import FolderCount  # noqa: E402

COUNTS = (("files", "Files"), ("symbols", "Symbols"), ("references", "References"))
BAR_WIDTH = 180


class IndexView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.shown: List[FolderCount] = []  # the rows the view shows now, in order
        self.summary = Gtk.Label(xalign=0)
        self.summary.add_css_class("dim-label")
        self.grid = Gtk.Grid(column_spacing=14, row_spacing=6)
        for margin in ("start", "end", "top", "bottom"):
            getattr(self.grid, f"set_margin_{margin}")(8)
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.grid)
        self.append(self.summary)
        self.append(scroller)

    def show(self, counts: Sequence[FolderCount]) -> None:
        """Puts the rows into the grid: the folder, then a bar and its number for each count."""
        self.shown = list(counts)
        child = self.grid.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.grid.remove(child)
            child = following
        roots = sum(1 for row in self.shown if row.root)
        self.summary.set_text(f"{roots} project folder(s), {len(self.shown) - roots} folder(s) below them")
        for column, heading in enumerate(("Folder",) + tuple(title for _key, title in COUNTS)):
            label = Gtk.Label(label=heading, xalign=0)
            label.add_css_class("heading")
            self.grid.attach(label, column, 0, 1, 1)
        largest = {key: max([getattr(row, key) for row in self.shown] + [1]) for key, _title in COUNTS}
        for number, row in enumerate(self.shown, 1):
            name = Gtk.Label(xalign=0)
            text = GLib.markup_escape_text(row.label)
            name.set_markup(f"<b>{text}</b>" if row.root else text)
            name.set_tooltip_text(row.folder)
            self.grid.attach(name, 0, number, 1, 1)
            for column, (key, _title) in enumerate(COUNTS, 1):
                self.grid.attach(self._bar(getattr(row, key), largest[key]), column, number, 1, 1)

    @staticmethod
    def _bar(value: int, top: int) -> Gtk.Widget:
        cell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar = Gtk.LevelBar()
        bar.set_min_value(0)
        bar.set_max_value(top)
        bar.set_value(value)
        bar.set_size_request(BAR_WIDTH, -1)
        bar.set_valign(Gtk.Align.CENTER)
        number = Gtk.Label(label=str(value), xalign=1)
        number.set_width_chars(6)
        cell.append(bar)
        cell.append(number)
        return cell
