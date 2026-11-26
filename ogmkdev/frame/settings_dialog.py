"""The settings dialog: the categories as a tree on the left (as deep as the schema goes), a search field above it, and
on the right the settings of the selected category, or of the search. Each setting has its control, its key and a
reset to its default. The values are edited in an OtherSettings model; Save writes them to the EditorConfig file of
the scope. A value that is not valid is refused by the model, and the dialog says why; the old value stays.

Failures are return values (see ogmkdev.outcome). Nothing here returns None: a missing value is read as its default.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from .. import settings as settings_module  # noqa: E402
from ..othersettings import Pairs, PreStoredSettings  # noqa: E402
from ..outcome import Failure  # noqa: E402
from ..settings import (Setting, SettingsStore, build_model, category_tree, in_category, model_text,  # noqa: E402
                        model_values, pairs_text, search, set_model_text)
from .panels import _scrolled  # noqa: E402

DIM_CSS = "dim-label"
Row = Tuple[Setting, Gtk.Widget, Gtk.Button]


def colour_of(text: str) -> Gdk.RGBA:
    """The colour of a "#RRGGBB" text, for the colour picker."""
    colour = Gdk.RGBA()
    colour.parse(text)
    return colour


def text_of_colour(colour: Gdk.RGBA) -> str:
    """The "#RRGGBB" text of a colour the picker chose."""
    return "#%02X%02X%02X" % (round(colour.red * 255), round(colour.green * 255), round(colour.blue * 255))


def _colour_button() -> Gtk.Widget:
    if hasattr(Gtk, "ColorDialogButton"):
        return Gtk.ColorDialogButton.new(Gtk.ColorDialog())
    return Gtk.ColorButton()  # the colour button of the older GTK 4 versions


class SettingsDialog(Gtk.Window):
    """The dialog for one scope: "global" (Preferences) or "project" (the project's .editorconfig)."""

    def __init__(self, parent: Gtk.Window, store: SettingsStore, scope: str, select: str,
                 on_saved: Callable[[Dict[str, str]], None]) -> None:
        super().__init__(title="Preferences" if scope == "global" else "Project Settings",
                         transient_for=parent, modal=True)
        self.set_default_size(860, 580)
        self.store = store
        self.scope = scope
        self.on_saved = on_saved
        values = store.read(scope)  # every section of the scope's file: a PHP setting lives in its own section
        self.model: PreStoredSettings = build_model(values)
        self._opened: Dict[str, str] = model_values(self.model)  # the values the scope held when the dialog opened
        self._rows: Dict[str, Row] = {}
        self._category = ""

        self.search = Gtk.SearchEntry(placeholder_text="Search settings")
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.set_margin_top(8)
        self.search.connect("search-changed", lambda *_args: self._show_page())
        self.tree_store = Gtk.TreeStore(str, str)  # the category name, its path
        self._fill_tree(category_tree(), None)
        self.tree = Gtk.TreeView(model=self.tree_store)
        self.tree.set_headers_visible(False)
        self.tree.append_column(Gtk.TreeViewColumn("Category", Gtk.CellRendererText(), text=0))
        self.tree.expand_all()
        self.tree.get_selection().connect("changed", self._on_category_selected)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left.append(self.search)
        left.append(_scrolled(self.tree))

        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.page.set_margin_start(12)
        self.page.set_margin_end(12)
        self.page.set_margin_top(10)
        self.heading = Gtk.Label(xalign=0)
        self.heading.add_css_class("title-3")
        self.message = Gtk.Label(xalign=0, wrap=True)
        self.message.add_css_class(DIM_CSS)
        self.page.append(self.heading)
        self.page.append(self.message)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(left)
        paned.set_end_child(_scrolled(self.page))
        paned.set_position(230)
        paned.set_vexpand(True)

        cancel = Gtk.Button(label="Cancel")
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        cancel.connect("clicked", lambda *_args: self.destroy())
        save.connect("clicked", lambda *_args: self._save_and_close())
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
        buttons.set_margin_bottom(8)
        buttons.set_margin_end(8)
        buttons.append(cancel)
        buttons.append(save)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(paned)
        box.append(buttons)
        self.set_child(box)
        self.select_category(select)

    # ------------------------------------------------------------ the tree

    def _fill_tree(self, nodes: List[Dict[str, object]], parent: Optional[Gtk.TreeIter]) -> None:
        for node in nodes:
            iterator = self.tree_store.append(parent, [str(node["name"]), str(node["path"])])
            self._fill_tree(node["children"], iterator)  # type: ignore[arg-type]

    def select_category(self, path: str) -> None:
        """Selects the category with this path; the first category when no category has it."""
        found: List[Tuple[str, Gtk.TreeIter]] = []

        def visit(model: Gtk.TreeModel, _tree_path: Gtk.TreePath, iterator: Gtk.TreeIter) -> bool:
            found.append((str(model[iterator][1]), iterator.copy()))
            return False

        self.tree_store.foreach(visit)
        if not found:
            self._category = ""
            self._show_page()
            return
        chosen = found[0][1]
        for row_path, iterator in found:
            if row_path == path:
                chosen = iterator
                break
        self.tree.get_selection().select_iter(chosen)

    def _on_category_selected(self, selection: Gtk.TreeSelection) -> None:
        model, iterator = selection.get_selected()
        self._category = str(model[iterator][1]) if iterator is not None else ""
        self.search.set_text("")
        self._show_page()

    # ------------------------------------------------------------ the page

    def _shown_settings(self) -> Tuple[str, List[Setting]]:
        """The heading and the settings the page shows: the search results, or the selected category with all its
        sub-categories."""
        query = self.search.get_text().strip()
        if query:
            return f"Search: {query}", search(query)
        if not self._category:
            return "Preferences", []
        return self._category, [s for s in settings_module.SCHEMA if in_category(s, self._category)]

    def _show_page(self) -> None:
        heading, shown = self._shown_settings()
        self.heading.set_text(heading)
        self._rows = {}
        child = self.page.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            if child is not self.heading and child is not self.message:
                self.page.remove(child)
            child = following
        for setting in shown:
            self.page.append(self._row_for(setting))
        self.message.set_text("" if shown else "No setting matches.")

    def _row_for(self, setting: Setting) -> Gtk.Widget:
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        line.set_margin_top(6)
        line.set_margin_bottom(6)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.set_hexpand(True)
        label = Gtk.Label(label=setting.label, xalign=0, wrap=True)
        key = Gtk.Label(label=f"{setting.key}   {setting.group}", xalign=0)
        key.add_css_class(DIM_CSS)
        text.append(label)
        text.append(key)
        control = self._control_for(setting)
        reset = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
        reset.add_css_class("flat")
        reset.set_tooltip_text(f"Reset to the default: {setting.default}")
        reset.connect("clicked", lambda *_args: self._reset(setting.key))
        line.append(text)
        line.append(control)
        line.append(reset)
        row: Row = (setting, control, reset)
        self._rows[setting.key] = row
        self._update_reset(row)
        return line

    def _control_for(self, setting: Setting) -> Gtk.Widget:
        current = model_text(self.model, setting)
        if setting.kind == "bool":
            check = Gtk.CheckButton(active=current == "true")
            check.connect("toggled", lambda widget: self._changed(setting, "true" if widget.get_active() else "false"))
            return check
        if setting.kind == "int":
            spin = Gtk.SpinButton.new_with_range(0, 100000, 1)
            spin.set_value(float(current))
            spin.connect("value-changed", lambda widget: self._changed(setting, str(int(widget.get_value()))))
            return spin
        if setting.kind == "choice":
            choices = list(setting.choices)
            dropdown = Gtk.DropDown.new_from_strings(choices)
            dropdown.set_selected(choices.index(current) if current in choices else 0)
            dropdown.connect("notify::selected", lambda widget, _p: self._dropdown_changed(setting, choices, widget))
            return dropdown
        if setting.kind == "color":
            button = _colour_button()
            button.set_rgba(colour_of(current))
            button.connect("notify::rgba", lambda widget, _p: self._changed(setting, text_of_colour(widget.get_rgba())))
            return button
        if setting.kind == "pairs":
            return self._pairs_control(setting)
        entry = Gtk.Entry(text=current, hexpand=True)
        entry.set_width_chars(28)
        entry.connect("changed", lambda widget: self._changed(setting, widget.get_text()))
        return entry

    def _dropdown_changed(self, setting: Setting, choices: List[str], dropdown: Gtk.DropDown) -> None:
        selected = dropdown.get_selected()
        if selected < len(choices):
            self._changed(setting, choices[selected])

    def _pairs_control(self, setting: Setting) -> Gtk.Widget:
        """The keyword and priority pairs as rows: a keyword, a priority, a button that removes the row, and a button
        that adds one. Every change puts all rows into the model as one text."""
        current = self.model.get_pairs(setting.key)
        start: Pairs = [] if isinstance(current, Failure) else current
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lines: List[Tuple[Gtk.Entry, Gtk.SpinButton, Gtk.Box]] = []

        def changed(*_args: object) -> None:
            pairs: Pairs = [(entry.get_text().strip(), int(spin.get_value())) for entry, spin, _line in lines]
            self._changed(setting, pairs_text(pairs))

        def remove(line: Gtk.Box) -> None:
            lines[:] = [row for row in lines if row[2] is not line]
            rows_box.remove(line)
            changed()

        def add(keyword: str, priority: int) -> None:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            entry = Gtk.Entry(text=keyword)
            entry.set_width_chars(16)
            spin = Gtk.SpinButton.new_with_range(0, 99, 1)
            spin.set_value(float(priority))
            delete = Gtk.Button.new_from_icon_name("list-remove-symbolic")
            delete.add_css_class("flat")
            delete.set_tooltip_text("Remove this keyword")
            line.append(entry)
            line.append(spin)
            line.append(delete)
            lines.append((entry, spin, line))
            rows_box.append(line)
            entry.connect("changed", changed)
            spin.connect("value-changed", changed)
            delete.connect("clicked", lambda *_args: remove(line))

        for keyword, priority in start:
            add(keyword, priority)
        add_button = Gtk.Button(label="Add a keyword")
        add_button.set_halign(Gtk.Align.START)
        add_button.connect("clicked", lambda *_args: add("", 1))
        box.append(rows_box)
        box.append(add_button)
        return box

    def _update_reset(self, row: Row) -> None:
        setting, _control, reset = row
        reset.set_sensitive(model_text(self.model, setting) != setting.default)

    # ------------------------------------------------------------ changes

    def _changed(self, setting: Setting, text: str) -> None:
        result = set_model_text(self.model, setting, text)
        if isinstance(result, Failure):
            self.message.set_text(str(result))
            return
        self.message.set_text("")
        if setting.key in self._rows:
            self._update_reset(self._rows[setting.key])

    def _reset(self, key: str) -> None:
        setting = settings_module.SETTINGS_BY_KEY[key]
        self._changed(setting, setting.default)
        self._show_page()  # the page is built again, so every control shows the default

    def shown_keys(self) -> List[str]:
        """The keys of the settings the page shows now, in page order."""
        return list(self._rows)

    # ------------------------------------------------------------ saving

    def values(self) -> Dict[str, str]:
        """The text of every setting as the dialog holds it."""
        return model_values(self.model)

    def save(self) -> None:
        """Writes the values that changed since the dialog opened to the scope's EditorConfig file, and reports all
        values. A value that did not change is not written, so saving without a change creates no file."""
        values = self.values()
        changed = {key: text for key, text in values.items() if text != self._opened[key]}
        self.store.apply(self.scope, changed)
        self.on_saved(values)

    def _save_and_close(self) -> None:
        self.save()
        self.destroy()
