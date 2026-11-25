"""Analysis in the frame: Problems (diagnostics of the open file, inspections of the folder), the
index (hierarchy, definitions, implementations), and the preferences dialog. Uses the backend
modules diagnostics, index, settings and editorconfig; no GUI code there."""

from __future__ import annotations

import hashlib
import os
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import diagnostics, editorconfig, index as index_module, languages  # noqa: E402
from .. import settings as settings_module  # noqa: E402
from ..settings import SettingsStore  # noqa: E402
from .panels import _scrolled  # noqa: E402


def _cache_path(folder: str) -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    digest = hashlib.sha1(os.path.abspath(folder).encode("utf-8")).hexdigest()
    return os.path.join(base, "ogmkdev", "index", digest + ".json")


class AnalysisMixin:
    """Window methods; uses ``workspace``, ``folder``, ``area``, ``bottom``, ``left``, ``open_file``."""

    # ----------------------------------------------------------- settings

    def _settings_for(self, path: Optional[str]) -> editorconfig.EditorSettings:
        properties = SettingsStore(self.folder).effective_for(path or self.folder)
        return editorconfig.settings_from_properties(properties)

    # ---------------------------------------------------------- problems

    def _set_problems(self, rows: List[tuple]) -> None:
        self.problems_store.clear()
        for severity, message, where, target in rows:
            self.problems_store.append([severity, message, where, target])

    def refresh_problems(self, path: Optional[str] = None) -> None:
        """Diagnostics of the open file (errors, warnings, hints), shown in the Problems tab."""
        if not hasattr(self, "problems_store"):
            return
        path = path or self.area.current_path()
        if not path or not os.path.isfile(path):
            self._set_problems([])
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            return
        detection = languages.detect(path, self._settings_for(path).custom)
        found = diagnostics.analyze(text, detection, self._settings_for(path))
        rows = [(item.severity, f"{item.message}  [{item.code}]",
                 f"{os.path.relpath(path, self.folder)}:{item.line}:{item.column}", (path, item.line))
                for item in found]
        self._set_problems(rows)

    def inspect_folder(self) -> None:
        """Inspections of the whole folder: unused and unresolved imports, missing methods, supertypes."""
        self._ensure_index()
        found = self.index.inspect()
        rows = [(item.severity, f"{item.message}  [{item.code}]",
                 f"{os.path.relpath(item.file, self.folder)}:{item.line}:{item.column}", (item.file, item.line))
                for item in found]
        self._set_problems(rows)
        self.bottom.set_current_page(self.bottom.page_num(self.problems_view.get_parent()))
        self.set_status(f"{len(rows)} inspection(s) in the folder")

    def _on_problem_activated(self, _view, path, _column) -> None:
        row = self.problems_store[self.problems_store.get_iter(path)]
        target = row[3]
        if isinstance(target, tuple):
            self.open_file(target[0], target[1], 1)

    # ------------------------------------------------------------- index

    def _ensure_index(self) -> None:
        if getattr(self, "index", None) is None:
            self.index = index_module.ProjectIndex(self.workspace.folders, cache_path=_cache_path(self.folder),
                                                   excluded=self.workspace.is_excluded)
            self.index.refresh()

    def refresh_index(self) -> None:
        self._ensure_index()
        counts = self.index.refresh()
        self.set_status(f"index refreshed: {counts}")

    def clear_index(self) -> None:
        self.index = None
        path = _cache_path(self.folder)
        if os.path.isfile(path):
            os.remove(path)
        self._ensure_index()
        self.set_status("index cleared and rebuilt")

    def _current_class(self) -> Optional[str]:
        path = self.area.current_path()
        if not path:
            return None
        self._ensure_index()
        for symbol in self.index.symbols:
            if symbol.file == path and symbol.kind in ("class", "interface", "trait", "enum"):
                return symbol.name
        return None

    def show_hierarchy(self) -> None:
        """The supertypes and subtypes of the first class in the open file, in the Hierarchy tab."""
        name = self._current_class()
        if not name:
            self.set_status("no class in the open file")
            return
        tree = self.index.hierarchy(name)
        self.hierarchy_store.clear()

        def add(parent, nodes, direction):
            for node in nodes:
                symbol = node.get("symbol")
                label = node.get("name", "")
                where = f"{os.path.relpath(symbol.file, self.folder)}:{symbol.line}" if symbol else ""
                iterator = self.hierarchy_store.append(parent, [label, direction, where,
                                                                (symbol.file, symbol.line) if symbol else None])
                add(iterator, node.get("children", []), direction)

        root = self.hierarchy_store.append(None, [name, "class", "", None])
        add(root, tree.get("up", []), "supertype")
        add(root, tree.get("down", []), "subtype")
        self.hierarchy_view.expand_all()
        self.left.set_current_page(self.left.page_num(self.hierarchy_box))
        self.set_status(f"hierarchy of {name}")

    def _on_hierarchy_activated(self, _view, path, _column) -> None:
        row = self.hierarchy_store[self.hierarchy_store.get_iter(path)]
        target = row[3]
        if isinstance(target, tuple):
            self.open_file(target[0], target[1], 1)

    def _show_symbols(self, title: str, symbols) -> None:
        self.search_store.clear()
        for symbol in symbols:
            where = f"{os.path.relpath(symbol.file, self.folder)}:{symbol.line}"
            self.search_store.append([where, f"{symbol.kind} {symbol.name}", symbol.file])
        self.bottom.set_current_page(self.bottom.page_num(self.search_page))
        self.set_status(f"{len(symbols)} {title}")

    def go_to_definition(self) -> None:
        self._ensure_index()
        self.ask_text("Go to definition", "Name of the class, function or method:", self._definitions_of)

    def _definitions_of(self, name: str) -> None:
        symbols = self.index.definitions(name)
        if len(symbols) == 1:
            self.open_file(symbols[0].file, symbols[0].line, symbols[0].column or 1)
        else:
            self._show_symbols(f"definition(s) of {name}", symbols)

    def find_implementations(self) -> None:
        self._ensure_index()
        name = self._current_class()
        if not name:
            self.ask_text("Find implementations", "Name of the class or interface:", self._implementations_of)
            return
        self._implementations_of(name)

    def _implementations_of(self, name: str) -> None:
        self._ensure_index()
        self._show_symbols(f"implementation(s) of {name}", self.index.subtypes(name))

    # ---------------------------------------------------------- settings

    def open_global_settings(self) -> None:
        self._settings_window(None)

    def open_diagnostic_settings(self) -> None:
        self._settings_window("Diagnostics")

    def _settings_window(self, only_group: Optional[str]) -> None:
        store = SettingsStore(self.folder)
        values = store.global_properties()
        window = Gtk.Window(title="Preferences", transient_for=self, modal=True)
        window.set_default_size(560, 520)
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(12)
        widgets = {}
        row = 0
        group_name = None
        for setting in settings_module.SCHEMA:
            if only_group and setting.group != only_group:
                continue
            if setting.group != group_name:
                group_name = setting.group
                heading = Gtk.Label(label=group_name, xalign=0)
                heading.add_css_class("heading")
                grid.attach(heading, 0, row, 2, 1)
                row += 1
            grid.attach(Gtk.Label(label=setting.label, xalign=0, wrap=True), 0, row, 1, 1)
            current = values.get(setting.key, setting.default)
            widget = self._setting_widget(setting, current)
            widgets[setting.key] = (setting, widget)
            grid.attach(widget, 1, row, 1, 1)
            row += 1
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        cancel.connect("clicked", lambda *_: window.destroy())

        def apply_values(*_args) -> None:
            new = {key: self._widget_value(setting, widget) for key, (setting, widget) in widgets.items()}
            store.apply("global", new)
            window.destroy()
            self.refresh_problems()
            self.set_status("preferences saved")

        save.connect("clicked", apply_values)
        buttons.append(cancel)
        buttons.append(save)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(_scrolled(grid))
        box.append(buttons)
        window.set_child(box)
        window.present()

    @staticmethod
    def _setting_widget(setting, current: str) -> Gtk.Widget:
        if setting.kind == "choice":
            choices = list(setting.choices)
            dropdown = Gtk.DropDown.new_from_strings(choices)
            dropdown.set_selected(choices.index(current) if current in choices else 0)
            return dropdown
        if setting.kind == "bool":
            switch = Gtk.Switch()
            switch.set_active(current == "true")
            switch.set_halign(Gtk.Align.START)
            return switch
        if setting.kind == "int":
            spin = Gtk.SpinButton.new_with_range(0, 1000, 1)
            try:
                spin.set_value(float(current))
            except ValueError:
                pass
            return spin
        entry = Gtk.Entry()
        entry.set_text(current)
        return entry

    @staticmethod
    def _widget_value(setting, widget: Gtk.Widget) -> str:
        if setting.kind == "choice":
            return setting.choices[widget.get_selected()]
        if setting.kind == "bool":
            return "true" if widget.get_active() else "false"
        if setting.kind == "int":
            return str(int(widget.get_value()))
        return widget.get_text().strip()
