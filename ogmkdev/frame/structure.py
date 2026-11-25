"""XML and HTML inspection in the frame: the Structure tab, and the context menu of an element.

* The Structure tab shows the elements of the file as a tree (tag, id, class); a row opens its line.
* Ctrl+right-click in the editor, on an element (in a tag or in its text), opens a menu with the element's
  CSS selectors and XPath expressions (unique, explicit, implicit, full), its id, class and tag, and its
  location. A click copies the entry to the clipboard. A plain right-click keeps the normal menu.

None of it applies to PHP files (also those with HTML in them) or when the setting
``ogmkdev_markup_inspection`` is ``off``; see :meth:`StructureMixin._markup_enabled`.
"""

from __future__ import annotations

import os
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import languages, markup, selectors  # noqa: E402
from .panels import _scrolled  # noqa: E402

MARKUP_LANGUAGES = ("xml", "svg", "html")
XML_MENU_SLOTS = 24  # the menu entries are actions xml-copy-0 .. xml-copy-23


class StructureMixin:
    """Window methods; uses ``left``, ``open_file``, ``area``, ``editors``, ``_settings_for``, ``set_status``."""

    _structure_key: Optional[tuple] = None
    _xml_texts: List[str] = []

    # ----------------------------------------------------------- the Structure tab

    def _build_structure(self) -> None:
        self.structure_store = Gtk.TreeStore(str, str, int, int)  # label, path, line, column
        self.structure_view = Gtk.TreeView(model=self.structure_store)
        self.structure_view.set_headers_visible(False)
        self.structure_view.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0))
        self.structure_view.connect("row-activated", self._on_structure_activated)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.structure_hint = Gtk.Label(label="Open an XML, SVG or HTML file (Tools > Show Structure).",
                                        xalign=0, wrap=True)
        box.append(self.structure_hint)
        box.append(_scrolled(self.structure_view))
        self.structure_box = box
        self.left.append_page(box, Gtk.Label(label="Structure"))

    def show_structure(self) -> None:
        path = self.area.current_path()
        self.refresh_structure(path)
        self.left.set_current_page(self.left.page_num(self.structure_box))

    def _markup_enabled(self, path: Optional[str]) -> bool:
        """Structure, selectors and id and file references apply to XML, SVG and HTML files only: not to
        PHP files, not to templates, and not when ``ogmkdev_markup_inspection`` is off."""
        if not path or not os.path.isfile(path):
            return False
        custom = self._settings_for(path).custom
        if custom.get("ogmkdev_markup_inspection", "on").strip().lower() == "off":
            return False
        detection = languages.detect(path, custom)
        return detection.template is None and detection.language in MARKUP_LANGUAGES

    def _follow_structure(self, path: Optional[str]) -> None:
        """Rebuilds the tree when the file changes (a save or another editor)."""
        if not path or not os.path.isfile(path):
            return
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            return
        if key != self._structure_key:
            self._structure_key = key
            self.refresh_structure(path)

    def refresh_structure(self, path: Optional[str]) -> None:
        self.structure_store.clear()
        if not path or not os.path.isfile(path):
            self.structure_hint.set_text("Open an XML, SVG or HTML file (Tools > Show Structure).")
            return
        if not self._markup_enabled(path):
            self.structure_hint.set_text(f"{os.path.basename(path)}: the XML and HTML inspection is off here")
            return
        detection = languages.detect(path, self._settings_for(path).custom)
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        found, error = markup.collect(text, html=detection.language == "html")
        parents = {}
        for element in found:
            parent = parents.get(element.depth - 1)
            iterator = self.structure_store.append(parent, [markup.label(element), path, element.line,
                                                            element.column])
            parents[element.depth] = iterator
        self.structure_view.expand_all()
        note = f" · not well-formed: {error}" if error else ""
        self.structure_hint.set_text(f"{len(found)} element(s) in {os.path.basename(path)}{note}")

    def _on_structure_activated(self, _view, path, _column) -> None:
        row = self.structure_store[self.structure_store.get_iter(path)]
        self.open_file(row[1], row[2], row[3])

    # ----------------------------------------------------------- the element menu (Ctrl+right-click)

    def _install_xml_menu(self) -> None:
        for slot in range(XML_MENU_SLOTS):
            action = Gio.SimpleAction.new(f"xml-copy-{slot}", None)
            action.connect("activate", lambda _a, _p, s=slot: self._copy_xml(s))
            self.add_action(action)
        self._xml_popover = Gtk.PopoverMenu.new_from_model(Gio.Menu())
        self._xml_popover.set_parent(self.area.root)
        self._xml_popover.set_has_arrow(False)

    def _copy_xml(self, slot: int) -> None:
        if slot >= len(self._xml_texts):
            return
        text = self._xml_texts[slot]
        provider = Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8",
                                                     GLib.Bytes.new(text.encode("utf-8")))
        Gdk.Display.get_default().get_clipboard().set_content(provider)
        self.set_status(f"copied to the clipboard: {text}")

    def show_xml_menu(self, x: float, y: float) -> None:
        """The menu for the element under the cursor, at the pointer (x, y) of the editor area."""
        status = self.editors.status()
        if not status:
            self.set_status("no editor has the focus")
            return
        path = status["path"]
        if not self._markup_enabled(path):
            self.set_status(f"the XML and HTML inspection is off for {os.path.basename(path)}")
            return
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        detection = languages.detect(path, self._settings_for(path).custom)
        found, _error = markup.collect(text, html=detection.language == "html")
        element = markup.element_at(found, text, status["line"], status["column"])
        if element is None:
            self.set_status("no element at the cursor: place it in a tag or inside the element's text")
            return
        location = f"{os.path.basename(path)}:{element.line}:{element.column}"
        model = Gio.Menu()
        self._xml_texts = []
        for label_text, copied in selectors.menu_items(found, element.index, location)[:XML_MENU_SLOTS]:
            slot = len(self._xml_texts)
            self._xml_texts.append(copied)
            model.append(label_text, f"win.xml-copy-{slot}")
        self._xml_popover.set_menu_model(model)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._xml_popover.set_pointing_to(rect)
        self._xml_popover.popup()
