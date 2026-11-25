"""ogmkdev editor window (GTK 3 + GtkSourceView 3).

Features: several documents in tabs, a project file tree, EditorConfig and language detection,
heredoc and SQL diagnostics, variable-based template completion (Ctrl+Space), breakpoints (F9),
JetBrains run configurations (Run / Debug), and GDB or XDebug debugging with watches.

Start with the interpreter that has PyGObject installed:  /usr/bin/python3.12 -m ogmkdev [path]

Keys: Ctrl+N new, Ctrl+O open, Ctrl+S save, Ctrl+W close tab, Ctrl+F find, Ctrl+Space template,
Ctrl+Z / Ctrl+Y undo / redo, F9 breakpoint, F5 run or continue, F10 step over,
F11 step into, Shift+F11 step out.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
from typing import Dict, List, Optional, Set, Tuple

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("GtkSource", "3.0")
    from gi.repository import GtkSource
except (ImportError, ValueError):
    GtkSource = None

from .. import diagnostics, highlight, languages, runconfig, templates, theme  # noqa: E402
from .. import __version__  # noqa: E402
from ..debug import DebuggerError, Exited, GdbMiDebugger, Output, Stopped, XdebugDebugger  # noqa: E402
from ..document import Document  # noqa: E402

BREAKPOINT_CATEGORY = "ogmkdev-breakpoint"
EXEC_TAG = "ogmkdev-exec"
# Languages highlighted by our own tokenizers (see ogmkdev/highlight.py), not by GtkSourceView.
OWN_HIGHLIGHT = frozenset({"ecmascript", "baredown", "sql"})
MENU_ORDER = ("File", "Edit", "View", "Run", "Debug", "Help")
# menu, label, icon name, accelerator, method name, shown in toolbar
ACTIONS = (
    ("File", "New", "document-new", "<Control>n", "new_document", True),
    ("File", "Open...", "document-open", "<Control>o", "open_dialog", True),
    ("File", "Save", "document-save", "<Control>s", "save_current", True),
    ("File", "Save As...", "document-save-as", "", "save_as", False),
    ("File", "Close Tab", "window-close", "<Control>w", "close_page", False),
    ("Edit", "Undo", "edit-undo", "<Control>z", "_undo", True),
    ("Edit", "Redo", "edit-redo", "<Control>y", "_redo", True),
    ("Edit", "Find...", "edit-find", "<Control>f", "focus_find", True),
    ("Edit", "Expand Template", "insert-text", "<Control>space", "_complete", False),
    ("Run", "Run Configuration", "media-playback-start", "", "run_selected", True),
    ("Run", "Debug Configuration", "system-run", "", "debug_selected", True),
    ("Debug", "Toggle Breakpoint", "media-record", "F9", "toggle_breakpoint", True),
    ("Debug", "Continue", "media-skip-forward", "F5", "continue_debugging", True),
    ("Debug", "Step Over", "go-next", "F10", "step_over", True),
    ("Debug", "Step Into", "go-down", "F11", "step_into", True),
    ("Debug", "Step Out", "go-up", "<Shift>F11", "step_out", True),
    ("Debug", "Stop", "media-playback-stop", "", "stop_debug", True),
)


def _tag_props(props):
    result = {}
    for key, value in props.items():
        if key == "style":
            result["style"] = Pango.Style.ITALIC
        elif key == "underline":
            result["underline"] = Pango.Underline.SINGLE
        else:
            result[key] = value
    return result


def _ui(function, *args) -> None:
    """Run ``function(*args)`` on the GTK main loop (safe to call from any thread)."""
    def run_once():
        function(*args)
        return False
    GLib.idle_add(run_once)


def _mark_attributes(color: str):
    attributes = GtkSource.MarkAttributes()
    rgba = Gdk.RGBA()
    rgba.parse(color)
    attributes.set_background(rgba)
    return attributes


class Page:
    """One open document together with its editor widgets."""

    def __init__(self, document: Document, colors) -> None:
        self.document = document
        self.dirty = False
        if GtkSource is not None:
            self.buffer = GtkSource.Buffer()
            self.view = GtkSource.View.new_with_buffer(self.buffer)
            self.view.set_show_line_numbers(True)
            self.view.set_show_line_marks(True)
            self.view.set_highlight_current_line(False)  # drawn by the current-line tag instead
        else:
            self.buffer = Gtk.TextBuffer()
            self.view = Gtk.TextView(buffer=self.buffer)
        self.view.set_monospace(True)
        self.view.set_auto_indent(True)
        self.exec_tag = self.buffer.create_tag(EXEC_TAG)
        for style in theme.STYLE_NAMES:
            self.buffer.create_tag(f"hl-{style}")
        self.apply_palette(colors)
        self.buffer.set_text(document.text)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.add(self.view)
        self.tab_label = Gtk.Label(label=document.title)
        self.apply_settings()
        self.apply_language()
        self.highlight()

    def text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def apply_settings(self) -> None:
        s = self.document.settings
        self.view.set_tab_width(s.tab_width or 4)
        self.view.set_insert_spaces_instead_of_tabs(s.indent_style != "tab")
        if hasattr(self.view, "set_indent_width"):
            self.view.set_indent_width(s.indent_size or 4)
        if GtkSource is not None and s.max_line_length:
            self.view.set_show_right_margin(True)
            self.view.set_right_margin_position(s.max_line_length)

    def apply_language(self) -> None:
        if GtkSource is None:
            return
        if self.document.detection.language in OWN_HIGHLIGHT:
            self.buffer.set_language(None)
            return
        gtk_id = languages.LANGUAGES[self.document.detection.language].gtk_source_id
        manager = GtkSource.LanguageManager.get_default()
        self.buffer.set_language(manager.get_language(gtk_id) if gtk_id else None)

    def apply_palette(self, colors) -> None:
        table = self.buffer.get_tag_table()
        for style, props in theme.tag_properties(colors).items():
            tag = table.lookup(f"hl-{style}")
            if tag is not None:
                for key, value in _tag_props(props).items():
                    tag.set_property(key, value)
        self.exec_tag.set_property("background", colors["execution"])
        if GtkSource is not None:
            self.view.set_mark_attributes(BREAKPOINT_CATEGORY, _mark_attributes(colors["breakpoint"]), 10)
        self.palette = colors

    def highlight(self) -> None:
        start, end = self.buffer.get_bounds()
        for style in theme.STYLE_NAMES:
            self.buffer.remove_tag_by_name(f"hl-{style}", start, end)
        language = self.document.detection.language
        if language in OWN_HIGHLIGHT:
            for style, first, last in highlight.spans(language, self.text()):
                self.buffer.apply_tag_by_name(f"hl-{style}", self.buffer.get_iter_at_offset(first),
                                              self.buffer.get_iter_at_offset(last))
        self.mark_current_line()

    def mark_current_line(self) -> None:
        start, end = self.buffer.get_bounds()
        self.buffer.remove_tag_by_name("hl-current-line", start, end)
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        line_start = self.buffer.get_iter_at_line(cursor.get_line())
        line_end = line_start.copy()
        line_end.forward_line()
        self.buffer.apply_tag_by_name("hl-current-line", line_start, line_end)

    def update_label(self) -> None:
        self.tab_label.set_text(self.document.title + (" *" if self.dirty else ""))


class EditorWindow(Gtk.Window):
    def __init__(self, path: Optional[str] = None, project_dir: Optional[str] = None,
                 mode: str = "light", scheme: str = "blend") -> None:
        super().__init__(title="ogmkdev")
        self.set_default_size(1280, 820)
        self.mode = mode
        self.scheme = scheme
        self.palette = theme.palette(mode, scheme)
        self._css_provider = None
        self.project_dir = os.path.abspath(project_dir or os.getcwd())
        self.registry = templates.builtin_registry()
        self.pages: List[Page] = []
        self.breakpoints: Dict[str, Set[int]] = {}
        self.status = Gtk.Label(xalign=0)  # created first: list signals may fire during setup
        self.status.set_selectable(True)
        self.run_configs: List[runconfig.RunConfiguration] = runconfig.discover(self.project_dir)
        self.debugger = None
        self.watch_exprs: List[str] = []
        self._session_bps: Dict[Tuple[str, int], int] = {}
        self._exec_line: Optional[Tuple[Page, int]] = None

        self.notebook = Gtk.Notebook(scrollable=True)
        self.notebook.connect("switch-page", lambda *_: _ui(self._update_status))

        self.tree_store = Gtk.TreeStore(str, str)
        self.tree = Gtk.TreeView(model=self.tree_store)
        self.tree.set_headers_visible(False)
        self.tree.append_column(Gtk.TreeViewColumn("Files", Gtk.CellRendererText(), text=0))
        self.tree.connect("row-activated", self._on_tree_activated)
        self.tree.connect("row-expanded", self._on_tree_expanded)
        self._populate_tree(None, self.project_dir)
        files_scroll = Gtk.ScrolledWindow()
        files_scroll.add(self.tree)

        self.run_list = Gtk.ListBox()
        self.run_list.connect("row-selected", lambda *_: self._update_status())
        run_scroll = Gtk.ScrolledWindow()
        run_scroll.add(self.run_list)
        run_buttons = Gtk.Box(spacing=4)
        for label, handler in (("Run", self.run_selected), ("Debug", self.debug_selected)):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, h=handler: h())
            run_buttons.pack_start(button, True, True, 0)
        run_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        run_box.pack_start(run_scroll, True, True, 0)
        run_box.pack_start(run_buttons, False, False, 0)
        self._load_run_list()

        left = Gtk.Notebook()
        left.append_page(files_scroll, Gtk.Label(label="Files"))
        left.append_page(run_box, Gtk.Label(label="Run"))

        self.console = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.console_buffer = self.console.get_buffer()
        console_scroll = Gtk.ScrolledWindow()
        console_scroll.add(self.console)
        self.watch_entry = Gtk.Entry(placeholder_text="watch expression, Enter to add")
        self.watch_entry.connect("activate", self._on_watch_activate)
        self.watch_label = Gtk.Label(xalign=0, yalign=0)
        self.watch_label.set_selectable(True)
        debug_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        debug_box.pack_start(self.watch_entry, False, False, 0)
        debug_box.pack_start(self.watch_label, False, False, 0)
        self.bottom = Gtk.Notebook()
        self.bottom.append_page(console_scroll, Gtk.Label(label="Console"))
        self.bottom.append_page(debug_box, Gtk.Label(label="Watches"))

        self.find_entry = Gtk.SearchEntry(placeholder_text="Find (Ctrl+F), Enter for next match")
        self.find_entry.connect("activate", lambda *_: self.find_next())

        self.menubar = self._build_menubar()
        self.toolbar = self._build_toolbar()

        center = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        center.pack1(self.notebook, True, False)
        center.pack2(self.bottom, False, False)
        main = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main.pack1(left, False, False)
        main.pack2(center, True, False)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer.pack_start(self.menubar, False, False, 0)
        outer.pack_start(self.toolbar, False, False, 0)
        outer.pack_start(main, True, True, 0)
        outer.pack_start(self.find_entry, False, False, 0)
        outer.pack_start(self.status, False, False, 2)
        self.add(outer)
        self.connect("key-press-event", self._on_key)
        self.set_theme(self.mode, self.scheme)

        if path:
            self.open_path(path)
        else:
            self.new_document()

    # ------------------------------------------------------ menus and toolbar

    def _build_menubar(self) -> Gtk.MenuBar:
        bar = Gtk.MenuBar()
        menus: Dict[str, Gtk.Menu] = {}
        for name in MENU_ORDER:
            item = Gtk.MenuItem(label=name)
            submenu = Gtk.Menu()
            item.set_submenu(submenu)
            bar.append(item)
            menus[name] = submenu
        for menu, label, _icon, accel, method, _in_toolbar in ACTIONS:
            entry = Gtk.MenuItem()
            accel_label = Gtk.AccelLabel(label=label, xalign=0.0)
            if accel:
                key, mods = Gtk.accelerator_parse(accel)
                accel_label.set_accel(key, mods)
            entry.add(accel_label)
            entry.connect("activate", lambda _item, m=method: getattr(self, m)())
            menus[menu].append(entry)
        view_menu = menus["View"]
        dark = Gtk.CheckMenuItem(label="Dark Theme")
        dark.set_active(self.mode == "dark")
        dark.connect("toggled", lambda item: self.set_theme("dark" if item.get_active() else "light"))
        view_menu.append(dark)
        view_menu.append(Gtk.SeparatorMenuItem())
        group = None
        for scheme_name in theme.SCHEMES:
            radio = Gtk.RadioMenuItem.new_with_label_from_widget(group, f"Color scheme: {scheme_name.capitalize()}")
            radio.set_active(scheme_name == self.scheme)
            radio.connect("toggled", lambda item, name=scheme_name: self.set_theme(self.mode, name)
                          if item.get_active() else None)
            view_menu.append(radio)
            group = radio
        about = Gtk.MenuItem(label="About ogmkdev")
        about.connect("activate", lambda _item: self.show_about())
        menus["Help"].append(about)
        return bar

    def _build_toolbar(self) -> Gtk.Toolbar:
        bar = Gtk.Toolbar()
        bar.set_style(Gtk.ToolbarStyle.ICONS)
        previous_menu = None
        for menu, label, icon, accel, method, in_toolbar in ACTIONS:
            if not in_toolbar:
                continue
            if previous_menu is not None and menu != previous_menu:
                bar.insert(Gtk.SeparatorToolItem(), -1)
            previous_menu = menu
            image = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR)
            button = Gtk.ToolButton(icon_widget=image, label=label)
            button.set_tooltip_text(f"{label}  ({accel})" if accel else label)
            button.connect("clicked", lambda _button, m=method: getattr(self, m)())
            bar.insert(button, -1)
        return bar

    def set_theme(self, mode: str, scheme: Optional[str] = None) -> None:
        """Switch between light and dark mode and between color schemes; no config file involved."""
        self.mode = mode
        self.scheme = scheme or self.scheme
        self.palette = theme.palette(self.mode, self.scheme)
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", self.mode == "dark")
        provider = Gtk.CssProvider()
        provider.load_from_data(theme.css(self.palette).encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if self._css_provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._css_provider)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css_provider = provider
        for page in self.pages:
            page.apply_palette(self.palette)
        self._update_status()

    def focus_find(self) -> None:
        self.find_entry.grab_focus()

    def continue_debugging(self) -> None:
        self.debug_op("run")

    def step_over(self) -> None:
        self.debug_op("step_over")

    def step_into(self) -> None:
        self.debug_op("step_into")

    def step_out(self) -> None:
        self.debug_op("step_out")

    def show_about(self) -> None:
        dialog = Gtk.AboutDialog(transient_for=self, program_name="ogmkdev", version=__version__,
                                 comments="A lightweight editor: KDevelop-derived base, GTK 3 front end.",
                                 license_type=Gtk.License.GPL_2_0)
        dialog.run()
        dialog.destroy()

    # ------------------------------------------------ compatibility accessors

    @property
    def page(self) -> Optional[Page]:
        index = self.notebook.get_current_page()
        return self.pages[index] if 0 <= index < len(self.pages) else None

    @property
    def view(self):
        return self.page.view if self.page else None

    @property
    def buffer(self):
        return self.page.buffer if self.page else None

    def _text(self) -> str:
        return self.page.text() if self.page else ""

    def console_text(self) -> str:
        start, end = self.console_buffer.get_bounds()
        return self.console_buffer.get_text(start, end, True)

    # ---------------------------------------------------------- documents

    def new_document(self) -> None:
        self._add_page(Document.new())

    def open_path(self, path: str) -> Page:
        absolute = os.path.abspath(path)
        for index, page in enumerate(self.pages):
            if page.document.path == absolute:
                self.notebook.set_current_page(index)
                return page
        return self._add_page(Document.open(absolute))

    def _add_page(self, document: Document) -> Page:
        page = Page(document, self.palette)

        def on_mark_set(*_args) -> None:
            page.mark_current_line()
            self._update_status()
        page.buffer.connect("changed", lambda *_: self._on_changed(page))
        page.buffer.connect("mark-set", on_mark_set)
        self.pages.append(page)
        self.notebook.append_page(page.scroller, page.tab_label)
        self.notebook.set_tab_reorderable(page.scroller, True)
        self.notebook.show_all()
        self.notebook.set_current_page(len(self.pages) - 1)
        for line in self.breakpoints.get(document.path or "", ()):
            self._add_breakpoint_mark(page, line)
        self._update_status()
        return page

    def _on_changed(self, page: Page) -> None:
        page.dirty = True
        page.document.text = page.text()
        page.document.analyze()
        page.highlight()
        page.update_label()
        self._update_status()

    def save(self) -> None:
        self.save_current()

    def save_current(self) -> None:
        page = self.page
        if page is None:
            return
        if page.document.path is None:
            self.save_as()
            return
        page.document.text = page.text()
        try:
            page.document.save()
        except OSError as error:
            self.status.set_text(f"save failed: {error}")
            return
        self._after_save(page)

    def save_as(self) -> None:
        page = self.page
        if page is None:
            return
        dialog = Gtk.FileChooserDialog(title="Save as", parent=self, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dialog.set_current_folder(self.project_dir)
        dialog.set_current_name(page.document.title)
        response = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and filename:
            page.document.text = page.text()
            page.document.save(filename)
            self._after_save(page)

    def _after_save(self, page: Page) -> None:
        page.dirty = False
        page.apply_settings()
        page.apply_language()
        page.highlight()
        page.update_label()
        self._update_status(saved=True)

    def open_dialog(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Open", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        dialog.set_current_folder(self.project_dir)
        filename = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        if filename:
            self.open_path(filename)

    def close_page(self) -> None:
        index = self.notebook.get_current_page()
        if not 0 <= index < len(self.pages):
            return
        page = self.pages.pop(index)
        if self._exec_line and self._exec_line[0] is page:
            self._exec_line = None
        self.notebook.remove_page(index)
        self._update_status()

    # -------------------------------------------------------- file tree

    def _populate_tree(self, parent, folder: str) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in (".editorconfig", ".run"):
                continue
            if entry.name == "__pycache__":
                continue
            node = self.tree_store.append(parent, [entry.name, entry.path])
            if entry.is_dir(follow_symlinks=False):
                self.tree_store.append(node, ["", ""])  # placeholder, replaced on expand

    def _on_tree_expanded(self, _view, node, _path) -> None:
        first = self.tree_store.iter_children(node)
        if first is not None and self.tree_store[first][1] == "":
            self.tree_store.remove(first)
            self._populate_tree(node, self.tree_store[node][1])

    def _on_tree_activated(self, view, path, _column) -> None:
        target = self.tree_store[self.tree_store.get_iter(path)][1]
        if not target:
            return
        if os.path.isdir(target):
            view.collapse_row(path) if view.row_expanded(path) else view.expand_row(path, False)
        else:
            self.open_path(target)

    # ------------------------------------------------------ run / debug

    def _load_run_list(self) -> None:
        for child in self.run_list.get_children():
            self.run_list.remove(child)
        if not self.run_configs:
            self._add_run_row("no run configurations in .run/ or .idea/runConfigurations/")
        for config in self.run_configs:
            self._add_run_row(f"{config.name}  [{config.type}]")
        self.run_list.show_all()
        if self.run_configs:
            self.run_list.select_row(self.run_list.get_row_at_index(0))

    def _add_run_row(self, text: str) -> None:
        row = Gtk.ListBoxRow()
        row.add(Gtk.Label(label=text, xalign=0))
        self.run_list.add(row)

    def _selected_config(self) -> Optional[runconfig.RunConfiguration]:
        row = self.run_list.get_selected_row()
        if row is None or row.get_index() >= len(self.run_configs):
            return None
        return self.run_configs[row.get_index()]

    def _expand(self, value: str) -> str:
        return value.replace("$PROJECT_DIR$", self.project_dir)

    def run_selected(self) -> None:
        config = self._selected_config()
        if config is None:
            self.status.set_text("select a run configuration first")
            return
        if config.type in (runconfig.GDB_TYPE, runconfig.XDEBUG_TYPE):
            self.debug_selected()
            return
        try:
            spec = config.to_process(self.project_dir)
        except runconfig.RunConfigError as error:
            self.status.set_text(str(error))
            return
        self._console_write("$ " + " ".join(shlex.quote(arg) for arg in spec.argv) + "\n")
        try:
            process = subprocess.Popen(spec.argv, cwd=spec.cwd, env=spec.env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, errors="replace")
        except OSError as error:
            self.status.set_text(f"cannot start {spec.argv[0]}: {error}")
            return
        threading.Thread(target=self._pipe_to_console, args=(process,), daemon=True).start()

    def _pipe_to_console(self, process: subprocess.Popen, *, label: str = "exit") -> None:
        for line in process.stdout:
            _ui(self._console_write, line)
        code = process.wait()
        _ui(self._console_write, f"[{label} {code}]\n")

    def debug_selected(self) -> None:
        if self.debugger is not None:
            self.status.set_text("a debug session is already running")
            return
        config = self._selected_config()
        if config is None:
            self.status.set_text("select a run configuration first")
            return
        try:
            if config.type == runconfig.GDB_TYPE:
                debugger, launch = self._gdb_session(config)
            elif config.type == runconfig.XDEBUG_TYPE:
                debugger, launch = self._xdebug_session(config)
            else:
                self.status.set_text(f"{config.name}: type {config.type} cannot be debugged")
                return
        except (runconfig.RunConfigError, ValueError, OSError) as error:
            self.status.set_text(f"{config.name}: {error}")
            return
        self.debugger = debugger
        self._session_bps.clear()
        debugger.on_event(lambda event: _ui(self._on_debug_event, debugger, event))
        self.status.set_text(f"debugging {config.name} ...")
        threading.Thread(target=self._session_main, args=(debugger, launch), daemon=True).start()

    def _gdb_session(self, config):
        program = self._expand(config.option("PROGRAM", "") or "")
        if not program:
            raise runconfig.RunConfigError(f"{config.name}: PROGRAM is empty")
        args = shlex.split(config.option("ARGUMENTS", "") or "")
        cwd = self._expand(config.option("WORKING_DIRECTORY", "$PROJECT_DIR$") or self.project_dir)
        return GdbMiDebugger(program, args, cwd), None

    def _xdebug_session(self, config):
        script = self._expand(config.option("SCRIPT_NAME", "") or "")
        if not script:
            raise runconfig.RunConfigError(f"{config.name}: SCRIPT_NAME is empty")
        debugger = XdebugDebugger(port=int(config.option("PORT", "0") or "0"))
        port = debugger.listen()
        launch = ["php", "-d", "xdebug.mode=debug", "-d", "xdebug.start_with_request=yes",
                  "-d", "xdebug.client_host=127.0.0.1", "-d", f"xdebug.client_port={port}", script]
        return debugger, launch

    def _session_main(self, debugger, launch) -> None:
        """Worker thread: start the engine, install breakpoints, resume."""
        try:
            if launch:
                process = subprocess.Popen(launch, cwd=self.project_dir, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, errors="replace")
                threading.Thread(target=self._pipe_to_console, args=(process,),
                                 kwargs={"label": "php exit"}, daemon=True).start()
            debugger.start()
            for path, lines in list(self.breakpoints.items()):
                for line in sorted(lines):
                    self._session_bps[(path, line)] = debugger.add_breakpoint(path, line).id
            debugger.run()
        except (DebuggerError, OSError) as error:
            _ui(self._session_failed, debugger, str(error))

    def _session_failed(self, debugger, message: str) -> None:
        self.status.set_text(f"debug session failed: {message}")
        if self.debugger is debugger:
            self._end_session(debugger)

    def _on_debug_event(self, debugger, event) -> None:
        if isinstance(event, Output):
            self._console_write(event.text if event.text.endswith("\n") else event.text + "\n")
        elif isinstance(event, Stopped):
            location = event.location
            if location and location.file and location.line:
                self._show_execution_line(location.file, location.line)
                where = f"{os.path.basename(location.file)}:{location.line}"
            else:
                where = "unknown location"
            self.status.set_text(f"stopped ({event.reason}) at {where}")
            self._refresh_watches()
        elif isinstance(event, Exited):
            self._clear_execution_line()
            code = "" if event.code is None else f", exit code {event.code}"
            self.status.set_text(f"program exited{code}")
            if self.debugger is debugger:
                self._end_session(debugger)

    def debug_op(self, operation: str) -> None:
        debugger = self.debugger
        if debugger is None:
            self.status.set_text("no debug session: press Debug first")
            return
        self._run_async(getattr(debugger, operation))

    def stop_debug(self) -> None:
        if self.debugger is not None:
            self._end_session(self.debugger)
            self.status.set_text("debug session stopped")

    def _end_session(self, debugger) -> None:
        if self.debugger is debugger:
            self.debugger = None
        self._clear_execution_line()
        self._session_bps.clear()
        threading.Thread(target=debugger.stop, daemon=True).start()

    def _run_async(self, function, on_done=None) -> None:
        def worker():
            try:
                result = function()
            except Exception as error:  # report every backend failure in the status bar
                _ui(self.status.set_text, f"error: {error}")
                return
            if on_done is not None:
                _ui(on_done, result)
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------- watches

    def _on_watch_activate(self, entry: Gtk.Entry) -> None:
        expression = entry.get_text().strip()
        entry.set_text("")
        if expression:
            self.add_watch(expression)

    def add_watch(self, expression: str) -> None:
        self.watch_exprs.append(expression)
        self._refresh_watches()

    def _refresh_watches(self) -> None:
        debugger = self.debugger
        if debugger is None or not self.watch_exprs:
            self._render_watches({})
            return
        expressions = list(self.watch_exprs)

        def evaluate():
            values = {}
            for expression in expressions:
                try:
                    values[expression] = debugger.evaluate(expression)
                except DebuggerError as error:
                    values[expression] = f"<error: {error}>"
            return values
        self._run_async(evaluate, self._render_watches)

    def _render_watches(self, values: Dict[str, str]) -> None:
        lines = [f"{expr} = {values.get(expr, '(not evaluated)')}" for expr in self.watch_exprs]
        self.watch_label.set_text("\n".join(lines) if lines else "no watches")

    # ---------------------------------------------------- breakpoints

    def toggle_breakpoint(self) -> None:
        page = self.page
        if page is None:
            return
        path = page.document.path
        if path is None:
            self.status.set_text("save the file before setting breakpoints")
            return
        cursor = page.buffer.get_iter_at_mark(page.buffer.get_insert())
        line = cursor.get_line() + 1
        lines = self.breakpoints.setdefault(path, set())
        debugger = self.debugger
        if line in lines:
            lines.discard(line)
            self._remove_breakpoint_marks(page, line)
            bp_id = self._session_bps.pop((path, line), None)
            if debugger is not None and bp_id is not None:
                self._run_async(lambda: debugger.remove_breakpoint(bp_id))
        else:
            lines.add(line)
            self._add_breakpoint_mark(page, line)
            if debugger is not None:
                def install():
                    return debugger.add_breakpoint(path, line).id
                self._run_async(install, lambda bp_id: self._session_bps.__setitem__((path, line), bp_id))
        self._update_status()

    def _add_breakpoint_mark(self, page: Page, line: int) -> None:
        if GtkSource is None:
            return
        last = max(page.buffer.get_line_count() - 1, 0)
        page.buffer.create_source_mark(None, BREAKPOINT_CATEGORY,
                                       page.buffer.get_iter_at_line(min(max(line - 1, 0), last)))

    def _remove_breakpoint_marks(self, page: Page, line: int) -> None:
        if GtkSource is None:
            return
        for mark in page.buffer.get_source_marks_at_line(line - 1, BREAKPOINT_CATEGORY):
            page.buffer.delete_mark(mark)

    def _show_execution_line(self, path: str, line: int) -> None:
        page = self.open_path(path)
        self._clear_execution_line()
        start, end = self._line_bounds(page, line)
        page.buffer.apply_tag(page.exec_tag, start, end)
        self._exec_line = (page, line)
        page.buffer.place_cursor(start)
        page.view.scroll_to_iter(start, 0.2, False, 0.0, 0.0)

    def _clear_execution_line(self) -> None:
        if self._exec_line is None:
            return
        page, line = self._exec_line
        self._exec_line = None
        start, end = self._line_bounds(page, line)
        page.buffer.remove_tag(page.exec_tag, start, end)

    @staticmethod
    def _line_bounds(page: Page, line: int):
        last = max(page.buffer.get_line_count() - 1, 0)
        start = page.buffer.get_iter_at_line(min(max(line - 1, 0), last))
        end = start.copy()
        end.forward_line()
        return start, end

    # ----------------------------------------------------- editing aids

    def _complete(self) -> None:
        page = self.page
        if page is None:
            return
        buffer = page.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        start = cursor.copy()
        while start.backward_char():
            if not (start.get_char().isalnum() or start.get_char() == "_"):
                start.forward_char()
                break
        prefix = buffer.get_text(start, cursor, True)
        detection = page.document.detection
        matches = self.registry.complete(prefix, detection.template or detection.language, detection.dialect)
        if not matches:
            self.status.set_text(f"no template for '{prefix}' in {detection.name}")
            return
        expansion = templates.expand(matches[0])
        offset = start.get_offset()
        buffer.begin_user_action()
        buffer.delete(start, cursor)
        buffer.insert(buffer.get_iter_at_offset(offset), expansion.text)
        buffer.place_cursor(buffer.get_iter_at_offset(offset + expansion.cursor))
        buffer.end_user_action()

    def find_next(self) -> None:
        page = self.page
        needle = self.find_entry.get_text()
        if page is None or not needle:
            return
        buffer = page.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        found = cursor.forward_search(needle, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
        if found is None:
            found = buffer.get_start_iter().forward_search(needle, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
        if found is None:
            self.status.set_text(f"'{needle}' not found")
            return
        match_start, match_end = found
        buffer.select_range(match_end, match_start)
        page.view.scroll_to_iter(match_start, 0.2, False, 0.0, 0.0)

    def _undo(self) -> None:
        page = self.page
        if page and hasattr(page.buffer, "undo") and page.buffer.can_undo():
            page.buffer.undo()

    def _redo(self) -> None:
        page = self.page
        if page and hasattr(page.buffer, "redo") and page.buffer.can_redo():
            page.buffer.redo()

    def _console_write(self, text: str) -> None:
        self.console_buffer.insert(self.console_buffer.get_end_iter(), text)
        mark = self.console_buffer.create_mark(None, self.console_buffer.get_end_iter(), False)
        self.console.scroll_mark_onscreen(mark)

    # ----------------------------------------------------- status and keys

    def _update_status(self, saved: bool = False) -> None:
        page = self.page
        if page is None:
            self.status.set_text("no file open")
            return
        document = page.document
        buffer = page.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        s = document.settings
        parts = [
            ("saved: " if saved else "") + document.title + (" *" if page.dirty else ""),
            f"{cursor.get_line() + 1}:{cursor.get_line_offset() + 1}",
            document.detection.name,
            f"indent {s.indent_style or '-'}/{s.indent_size or '-'}",
            f"eol {s.end_of_line or 'lf'}",
            diagnostics.summary(document.diagnostics),
        ]
        self.status.set_text(" · ".join(parts))

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        key = event.keyval
        if ctrl and key in (Gdk.KEY_s, Gdk.KEY_S):
            self.save_current()
        elif ctrl and key in (Gdk.KEY_n, Gdk.KEY_N):
            self.new_document()
        elif ctrl and key in (Gdk.KEY_o, Gdk.KEY_O):
            self.open_dialog()
        elif ctrl and key in (Gdk.KEY_w, Gdk.KEY_W):
            self.close_page()
        elif ctrl and key in (Gdk.KEY_f, Gdk.KEY_F):
            self.find_entry.grab_focus()
        elif ctrl and key == Gdk.KEY_space:
            self._complete()
        elif ctrl and key in (Gdk.KEY_z, Gdk.KEY_Z) and not shift:
            self._undo()
        elif ctrl and (key in (Gdk.KEY_y, Gdk.KEY_Y) or (shift and key in (Gdk.KEY_z, Gdk.KEY_Z))):
            self._redo()
        elif key == Gdk.KEY_F9:
            self.toggle_breakpoint()
        elif key == Gdk.KEY_F5:
            self.debug_op("run") if self.debugger is not None else self.debug_selected()
        elif key == Gdk.KEY_F10:
            self.debug_op("step_over")
        elif key == Gdk.KEY_F11:
            self.debug_op("step_out" if shift else "step_into")
        else:
            return False
        return True


def main(argv: List[str]) -> int:
    """Usage: python -m ogmkdev [--dark|--light] [--scheme blend|jetbrains|eclipse] [file-or-folder]"""
    mode, scheme, paths = "light", "blend", []
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--dark":
            mode = "dark"
        elif arg == "--light":
            mode = "light"
        elif arg == "--scheme" and args:
            scheme = args.pop(0)
        else:
            paths.append(arg)
    if scheme not in theme.SCHEMES:
        print(f"unknown color scheme {scheme!r}; choose from {', '.join(theme.SCHEMES)}")
        return 2
    target = os.path.abspath(paths[0]) if paths else None
    if target and os.path.isdir(target):
        window = EditorWindow(None, project_dir=target, mode=mode, scheme=scheme)
    else:
        window = EditorWindow(target, project_dir=os.path.dirname(target) if target else None,
                              mode=mode, scheme=scheme)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0
