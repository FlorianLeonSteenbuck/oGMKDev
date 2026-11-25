"""The editor area of the frame: panes (Gtk.Notebook) split right, down, into four or six; every
tab is one Howl editor (see howl.py). A file that is already open is shown in its tab again."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402


class Slot(Gtk.Box):
    """A place in the layout that holds one child: a pane or a split (Gtk.Paned)."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.content: Optional[Gtk.Widget] = None

    def detach(self) -> None:
        """Takes the child out of the slot (it can then be put into another slot)."""
        if self.content is not None:
            self.remove(self.content)
            self.content = None

    def set_content(self, widget: Gtk.Widget) -> None:
        self.detach()
        self.content = widget
        widget.set_hexpand(True)
        widget.set_vexpand(True)
        self.append(widget)


class EditorArea:
    def __init__(self, frame) -> None:
        self.frame = frame
        self.root = Slot()
        self.panes: List[Gtk.Notebook] = []
        self.pages: Dict[Gtk.Widget, Optional[str]] = {}   # Howl page widget -> file path
        self.active: Optional[Gtk.Notebook] = None
        self.slots: Dict[Gtk.Notebook, Slot] = {}
        first = self._new_pane()
        self.root.set_content(first)
        self.slots[first] = self.root
        self.active = first

    # ------------------------------------------------------------- panes

    def _new_pane(self) -> Gtk.Notebook:
        notebook = Gtk.Notebook()
        notebook.set_scrollable(True)
        notebook.set_group_name("ogmkdev-editors")
        notebook.connect("page-removed", self._on_page_removed)
        notebook.connect("switch-page", self._on_switch_page)
        click = Gtk.GestureClick()
        click.connect("pressed", lambda *_: self._activate(notebook))
        notebook.add_controller(click)
        self.panes.append(notebook)
        return notebook

    def _activate(self, notebook: Gtk.Notebook) -> None:
        self.active = notebook

    def _new_slot(self, content: Gtk.Widget) -> Slot:
        slot = Slot()
        slot.set_content(content)
        return slot

    def split(self, orientation: Gtk.Orientation) -> Gtk.Notebook:
        """Splits the active pane; the new pane becomes the active one."""
        base = self.active
        slot = self.slots[base]
        slot.detach()                       # the pane leaves its slot before it moves
        paned = Gtk.Paned(orientation=orientation)
        paned.set_wide_handle(True)
        base_slot = self._new_slot(base)
        new = self._new_pane()
        new_slot = self._new_slot(new)
        self.slots[base] = base_slot
        self.slots[new] = new_slot
        paned.set_start_child(base_slot)
        paned.set_end_child(new_slot)
        slot.set_content(paned)
        # the new split starts halfway (the size is only known once the window is laid out)
        def halve(orientation=orientation, paned=paned):
            size = paned.get_allocated_height() if orientation == Gtk.Orientation.VERTICAL \
                else paned.get_allocated_width()
            if size > 0:
                paned.set_position(size // 2)
                return False
            return True
        GLib.timeout_add(100, halve)
        self.active = new
        return new

    def split_right(self) -> None:
        self.split(Gtk.Orientation.HORIZONTAL)

    def split_down(self) -> None:
        self.split(Gtk.Orientation.VERTICAL)

    def split_four(self) -> None:
        if len(self.panes) == 1:
            self.split_right()
            for pane in list(self.panes):
                self.active = pane
                self.split_down()

    def split_six(self) -> None:
        if len(self.panes) == 1:
            self.split_right()
            self.split_right()
            for pane in list(self.panes):
                self.active = pane
                self.split_down()

    def close_active_pane(self) -> bool:
        """Closes the active pane (its tabs go with it) when more than one pane is open."""
        if len(self.panes) <= 1:
            return False
        pane = self.active
        slot = self.slots.pop(pane)
        parent = slot.get_parent()
        self.panes.remove(pane)
        pane_parent = parent if isinstance(parent, Gtk.Paned) else None
        if pane_parent is None:
            return False
        sibling = pane_parent.get_start_child() if pane_parent.get_end_child() is slot else pane_parent.get_end_child()
        grand = pane_parent.get_parent()
        pane_parent.set_start_child(None)
        pane_parent.set_end_child(None)
        grand_slot = grand if isinstance(grand, Slot) else None
        if grand_slot is None:
            return False
        keep = sibling
        if isinstance(keep, Slot):
            content = keep.content
            keep.content = None
            keep.remove(content)
            grand_slot.set_content(content)
            self.slots = {pane_widget: (grand_slot if s is keep else s) for pane_widget, s in self.slots.items()}
        self.active = self.panes[0]
        return True

    # ------------------------------------------------------------- tabs

    def open(self, path: Optional[str] = None) -> Optional[Gtk.Widget]:
        """Shows ``path`` in its tab, or opens a new Howl editor for it in the active pane."""
        if path:
            for page, known in self.pages.items():
                if known == path:
                    notebook = self._notebook_of(page)
                    notebook.set_current_page(notebook.page_num(page))
                    self.active = notebook
                    return page
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.set_hexpand(True)
        page.set_vexpand(True)
        if not self.frame.editors.add(page, path):
            return None
        if path:
            self.frame.publish_templates(path)
        title = os.path.basename(path) if path else "untitled"
        tab = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tab.append(Gtk.Label(label=title))
        close = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close.add_css_class("flat")
        close.connect("clicked", lambda *_: self._close_page(page))
        tab.append(close)
        notebook = self.active
        notebook.append_page(page, tab)
        notebook.set_tab_reorderable(page, True)
        notebook.set_current_page(notebook.page_num(page))
        self.pages[page] = path
        if path:
            # the state the file is opened in is the baseline: a save that comes before the next poll is still seen
            self.frame.track_history(path)
        return page

    def _notebook_of(self, page: Gtk.Widget) -> Optional[Gtk.Notebook]:
        for notebook in self.panes:
            if notebook.page_num(page) >= 0:
                return notebook
        return None

    def _close_page(self, page: Gtk.Widget) -> None:
        notebook = self._notebook_of(page)
        if notebook is not None:
            # Howl releases the editor while its widgets are still in the page
            self.frame.editors.close(page)
            notebook.remove_page(notebook.page_num(page))

    def _on_switch_page(self, _notebook: Gtk.Notebook, page: Gtk.Widget, _index: int) -> None:
        """The editor of the tab that becomes current gets the keyboard focus, so Howl follows the tab. It is
        given once GTK has finished the switch: GTK would otherwise move the focus back while it works."""
        GLib.idle_add(self._focus_page, page)

    def _focus_page(self, page: Gtk.Widget) -> bool:
        self.frame.editors.focus(page)
        return False

    def _on_page_removed(self, notebook: Gtk.Notebook, child: Gtk.Widget, _index: int) -> None:
        self.pages.pop(child, None)
        if notebook.get_n_pages() == 0 and len(self.panes) > 1:
            self.active = notebook
            self.close_active_pane()

    def current_page(self) -> Optional[Gtk.Widget]:
        """The tab that is shown in the active pane (its page widget), None when there is none."""
        notebook = self.active
        if notebook is None or notebook.get_n_pages() == 0:
            return None
        return notebook.get_nth_page(notebook.get_current_page())

    def current_path(self) -> Optional[str]:
        notebook = self.active
        if notebook is None or notebook.get_n_pages() == 0:
            return None
        return self.pages.get(notebook.get_nth_page(notebook.get_current_page()))

    def count(self) -> int:
        return len(self.pages)
