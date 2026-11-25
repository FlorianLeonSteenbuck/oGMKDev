"""GTK 3 editor window: EditorConfig, language detection, diagnostics, templates, run configs.

Start with the interpreter that has PyGObject installed::

    /usr/bin/python3.12 -m ogmkdev [file]

Keys: Ctrl+S saves (EditorConfig line handling applied), Ctrl+Space expands the variable-based
template whose trigger matches the word before the cursor.
"""

from __future__ import annotations

import os
from typing import List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

try:
    gi.require_version("GtkSource", "3.0")
    from gi.repository import GtkSource
except (ImportError, ValueError):
    GtkSource = None

from .. import diagnostics, editing, editorconfig, languages, runconfig, templates  # noqa: E402


class EditorWindow(Gtk.Window):
    def __init__(self, path: Optional[str] = None, project_dir: Optional[str] = None) -> None:
        super().__init__(title="ogmkdev")
        self.set_default_size(1100, 720)
        self.path: Optional[str] = None
        self.settings = editorconfig.EditorSettings()
        self.detection = languages.detect("untitled.txt")
        self.diagnostics: List[diagnostics.Diagnostic] = []
        self.registry = templates.builtin_registry()
        self.project_dir = project_dir or os.getcwd()
        self.run_configs: List[runconfig.RunConfiguration] = []

        if GtkSource is not None:
            self.buffer = GtkSource.Buffer()
            self.view = GtkSource.View.new_with_buffer(self.buffer)
            self.view.set_show_line_numbers(True)
        else:
            self.buffer = Gtk.TextBuffer()
            self.view = Gtk.TextView(buffer=self.buffer)
        self.view.set_monospace(True)
        self.view.set_auto_indent(True)
        self.buffer.connect("changed", lambda *_: self._refresh())

        scroller = Gtk.ScrolledWindow()
        scroller.add(self.view)
        self.run_list = Gtk.ListBox()
        self.run_list.connect("row-selected", self._on_run_selected)
        side = Gtk.ScrolledWindow()
        side.set_size_request(260, -1)
        side.add(self.run_list)
        self.status = Gtk.Label(xalign=0)
        self.status.set_selectable(True)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.pack1(side, False, False)
        paned.pack2(scroller, True, False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(paned, True, True, 0)
        box.pack_start(self.status, False, False, 4)
        self.add(box)
        self.connect("key-press-event", self._on_key)

        self._load_run_configs()
        if path:
            self.open_file(path)

    # ------------------------------------------------------------ files

    def open_file(self, path: str) -> None:
        self.path = os.path.abspath(path)
        with open(self.path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        self.settings = editorconfig.settings_for(self.path)
        self.detection = languages.detect_file(self.path, self.settings.custom)
        self._apply_view_settings()
        self._apply_language()
        self.buffer.set_text(text)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        self._refresh()

    def save(self) -> None:
        if not self.path:
            self.status.set_text("untitled file: nothing to save to")
            return
        with open(self.path, "wb") as handle:
            handle.write(editing.encode_for_save(self._text(), self.settings))
        self._refresh(saved=True)

    # ------------------------------------------------------- presentation

    def _text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def _apply_view_settings(self) -> None:
        s = self.settings
        self.view.set_tab_width(s.tab_width or 4)
        self.view.set_insert_spaces_instead_of_tabs(s.indent_style != "tab")
        if hasattr(self.view, "set_indent_width"):
            self.view.set_indent_width(s.indent_size or 4)
        if GtkSource is not None and s.max_line_length:
            self.view.set_show_right_margin(True)
            self.view.set_right_margin_position(s.max_line_length)

    def _apply_language(self) -> None:
        if GtkSource is None or not isinstance(self.buffer, GtkSource.Buffer):
            return
        gtk_id = languages.LANGUAGES[self.detection.language].gtk_source_id
        language = GtkSource.LanguageManager.get_default().get_language(gtk_id) if gtk_id else None
        self.buffer.set_language(language)

    def _refresh(self, saved: bool = False) -> None:
        text = self._text()
        self.diagnostics = diagnostics.analyze(text, self.detection, self.settings)
        s = self.settings
        name = os.path.basename(self.path) if self.path else "untitled"
        parts = [
            name,
            self.detection.name,
            f"indent {s.indent_style or '-'}/{s.indent_size or '-'}",
            f"tab {s.tab_width or '-'}",
            f"eol {s.end_of_line or 'lf'}",
            s.charset or "utf-8",
            diagnostics.summary(self.diagnostics),
        ]
        if saved:
            parts.insert(0, "saved")
        self.status.set_text(" · ".join(parts))

    def _load_run_configs(self) -> None:
        for child in self.run_list.get_children():
            self.run_list.remove(child)
        self.run_configs = runconfig.discover(self.project_dir)
        if not self.run_configs:
            self._add_row("no run configurations in .run/ or .idea/runConfigurations/")
        for config in self.run_configs:
            self._add_row(f"{config.name}  [{config.type}]")
        self.run_list.show_all()

    def _add_row(self, text: str) -> None:
        row = Gtk.ListBoxRow()
        row.add(Gtk.Label(label=text, xalign=0))
        self.run_list.add(row)

    def _on_run_selected(self, _list: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is None or row.get_index() >= len(self.run_configs):
            return
        config = self.run_configs[row.get_index()]
        try:
            spec = config.to_process(self.project_dir)
            self.status.set_text(f"{config.name}: {' '.join(spec.argv)} (cwd {spec.cwd})")
        except runconfig.RunConfigError as error:
            self.status.set_text(f"{config.name}: {error}")

    # ---------------------------------------------------------- editing

    def _complete(self) -> None:
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        start = cursor.copy()
        while start.backward_char():
            ch = start.get_char()
            if not (ch.isalnum() or ch == "_"):
                start.forward_char()
                break
        prefix = self.buffer.get_text(start, cursor, True)
        language = self.detection.template or self.detection.language
        matches = self.registry.complete(prefix, language, self.detection.dialect)
        if not matches:
            self.status.set_text(f"no template for '{prefix}' in {self.detection.name}")
            return
        expansion = templates.expand(matches[0])
        offset = start.get_offset()
        self.buffer.begin_user_action()
        self.buffer.delete(start, cursor)
        self.buffer.insert(self.buffer.get_iter_at_offset(offset), expansion.text)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(offset + expansion.cursor))
        self.buffer.end_user_action()

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and event.keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.save()
            return True
        if ctrl and event.keyval == Gdk.KEY_space:
            self._complete()
            return True
        return False


def main(argv: List[str]) -> int:
    path = os.path.abspath(argv[0]) if argv else None
    window = EditorWindow(path)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0
