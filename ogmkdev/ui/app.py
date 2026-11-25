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

import hashlib
import os
import shlex
import subprocess
import threading
from typing import Dict, List, Optional, Set, Tuple

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("GtkSource", "3.0")
    from gi.repository import GtkSource
except (ImportError, ValueError):
    GtkSource = None

from .. import diagnostics, editorconfig, highlight, languages, organize, runconfig, templates, theme  # noqa: E402
from ..index import ProjectIndex  # noqa: E402
from .. import settings as settings_module  # noqa: E402
from ..settings import SettingsStore  # noqa: E402
from ..workspace import Workspace  # noqa: E402
from ..history import LocalHistory, changed_lines  # noqa: E402
from .. import keymap as keymap_module  # noqa: E402
from .panels import DiagramView, HierarchyView, ResultsView  # noqa: E402
from .. import __version__  # noqa: E402
from ..debug import DebuggerError, Exited, GdbMiDebugger, Output, Stopped, XdebugDebugger  # noqa: E402
from ..document import Document  # noqa: E402

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.svg")
BREAKPOINT_CATEGORY = "ogmkdev-breakpoint"
EXEC_TAG = "ogmkdev-exec"
# Languages highlighted by our own tokenizers (see ogmkdev/highlight.py), not by GtkSourceView.
OWN_HIGHLIGHT = frozenset({"ecmascript", "baredown", "sql", "php"})
MENU_ORDER = ("File", "Edit", "View", "Project", "Settings", "Run", "Debug", "Help")
CHANGE_CATEGORIES = {"added": "ogmkdev-added", "modified": "ogmkdev-modified", "deleted": "ogmkdev-deleted"}
CHANGE_COLORS = {"added": "#3FB950", "modified": "#58A6FF", "deleted": "#F85149"}
AUTOSAVE_SECONDS = 2
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
    ("Project", "Search in Files...", "edit-find", "<Control><Shift>f", "search_in_files", False),
    ("Project", "Find Implementations", "go-down", "<Control><Alt>b", "find_implementations", True),
    ("Project", "Go to Definition", "go-jump", "<Control>b", "go_to_definition", True),
    ("Edit", "Organize Imports", "format-justify-left", "<Control><Alt>o", "organize_imports", False),
    ("Edit", "Local History", "document-open-recent", "<Control><Alt>h", "show_local_history", False),
    ("Edit", "Extract Patch Set...", "", "", "extract_patch_set", False),
    ("View", "Split Right", "", "<Control><Alt>r", "split_right", False),
    ("View", "Split Down", "", "<Control><Alt>d", "split_down", False),
    ("View", "Split into Four", "", "<Control><Alt>4", "split_four", False),
    ("View", "Split into Six", "", "<Control><Alt>6", "split_six", False),
    ("View", "Close Pane", "window-close", "<Control><Alt>w", "close_active_pane", False),
    ("Project", "Clear Index and Rebuild", "view-refresh", "", "clear_index", False),
    ("Project", "Show Type Hierarchy", "go-jump", "<Control>h", "show_hierarchy", True),
    ("Project", "Inspect Project", "dialog-warning", "", "inspect_project", True),
    ("Project", "Refresh Index", "view-refresh", "", "refresh_index", False),
    ("Project", "Open Folder...", "folder-open", "<Control><Shift>o", "open_folder", False),
    ("Project", "Project Settings...", "document-properties", "", "open_project_settings", False),
    ("Project", "Add Folder to Workspace...", "folder-new", "", "add_folder_to_workspace", False),
    ("Settings", "Preferences...", "preferences-system", "", "open_global_settings", False),
    ("Settings", "Error Hinting...", "dialog-warning", "", "open_diagnostic_settings", False),
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
        self.notebook = None           # the pane (Gtk.Notebook) that shows this page
        self.baseline = document.text  # last saved text; changed lines are marked against it
        self.change_marks: list = []
        self.autosave_id = 0
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
            for kind, category in CHANGE_CATEGORIES.items():
                self.view.set_mark_attributes(category, _mark_attributes(CHANGE_COLORS[kind]), 9)
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
        if self.document.settings.custom.get("ogmkdev_current_line", "true") == "false":
            return
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        line_start = self.buffer.get_iter_at_line(cursor.get_line())
        line_end = line_start.copy()
        line_end.forward_line()
        self.buffer.apply_tag_by_name("hl-current-line", line_start, line_end)

    def update_change_marks(self) -> None:
        """Gutter marks for lines added, modified or deleted since the last save."""
        if GtkSource is None:
            return
        for mark in self.change_marks:
            self.buffer.delete_mark(mark)
        self.change_marks = []
        if self.document.path is None:
            return
        last = max(self.buffer.get_line_count() - 1, 0)
        for line, kind in changed_lines(self.baseline, self.text()).items():
            iterator = self.buffer.get_iter_at_line(min(max(line - 1, 0), last))
            self.change_marks.append(self.buffer.create_source_mark(None, CHANGE_CATEGORIES[kind], iterator))

    def update_label(self) -> None:
        self.tab_label.set_text(self.document.title + (" *" if self.dirty else ""))


class EditorWindow(Gtk.Window):
    def __init__(self, path: Optional[str] = None, project_dir: Optional[str] = None,
                 mode: str = "light", scheme: str = "blend", autosave: Optional[bool] = None,
                 clear_index: bool = False) -> None:
        super().__init__(title="ogmkdev")
        self.set_default_size(1280, 820)
        self._set_logo()
        self.mode = mode
        self.scheme = scheme
        self.palette = theme.palette(mode, scheme)
        self._css_provider = None
        self.project_dir = os.path.abspath(project_dir or os.getcwd())
        self.registry = templates.builtin_registry()
        self.pages: List[Page] = []
        self.history = LocalHistory()
        self._autosave_flag = autosave
        self.autosave = bool(autosave)
        self.breakpoints: Dict[str, Set[int]] = {}
        self.status = Gtk.Label(xalign=0)  # created first: list signals may fire during setup
        self.status.set_selectable(True)
        self.run_configs: List[runconfig.RunConfiguration] = runconfig.discover(self.project_dir)
        self.settings_store = SettingsStore(self.project_dir)
        self.project_folders: List[str] = [self.project_dir]
        if self._autosave_flag is None:
            self.autosave = self.settings_store.value("ogmkdev_autosave") == "on"
        self._apply_keymap()
        if clear_index:
            self._remove_index_cache()
        self._apply_workspace()
        self.connect("destroy", self._save_index)
        self.debugger = None
        self.watch_exprs: List[str] = []
        self._session_bps: Dict[Tuple[str, int], int] = {}
        self._exec_line: Optional[Tuple[Page, int]] = None

        self.editor_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.notebooks: List[Gtk.Notebook] = []
        self.active_notebook = self._new_notebook()
        self.editor_area.pack_start(self.active_notebook, True, True, 0)

        self.tree_store = Gtk.TreeStore(str, str, str)
        self.tree = Gtk.TreeView(model=self.tree_store)
        self.tree.set_headers_visible(False)
        self.tree.append_column(Gtk.TreeViewColumn("Files", Gtk.CellRendererText(), text=0, foreground=2))
        self.tree.connect("row-activated", self._on_tree_activated)
        self.tree.connect("row-expanded", self._on_tree_expanded)
        self._rebuild_tree()
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

        self.search_view = ResultsView(self.navigate, "Result")
        self.problems_view = ResultsView(self.navigate, "Problem")
        self.hierarchy_view = HierarchyView(self.navigate)
        self.diagram_view = DiagramView(self.navigate)
        hierarchy_tabs = Gtk.Notebook()
        hierarchy_tabs.append_page(self.hierarchy_view, Gtk.Label(label="Tree"))
        hierarchy_tabs.append_page(self.diagram_view, Gtk.Label(label="Diagram"))
        self.hierarchy_tabs = hierarchy_tabs
        left = Gtk.Notebook()
        left.append_page(files_scroll, Gtk.Label(label="Files"))
        left.append_page(run_box, Gtk.Label(label="Run"))
        left.append_page(hierarchy_tabs, Gtk.Label(label="Hierarchy"))
        left.append_page(self._build_history_panel(), Gtk.Label(label="History"))
        self.left = left
        self.left_pages = {"Files": 0, "Run": 1, "Hierarchy": 2, "History": 3}

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
        self.bottom.append_page(self.problems_view, Gtk.Label(label="Problems"))
        self.bottom.append_page(self.search_view, Gtk.Label(label="Search"))
        self.bottom_pages = {"Console": 0, "Watches": 1, "Problems": 2, "Search": 3}

        self.find_entry = Gtk.SearchEntry(placeholder_text="Find (Ctrl+F), Enter for next match")
        self.find_entry.connect("activate", lambda *_: self.find_next())

        self.menubar = self._build_menubar()
        self.toolbar = self._build_toolbar()

        center = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        center.pack1(self.editor_area, True, False)
        center.pack2(self.bottom, False, False)
        main = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main.pack1(left, False, False)
        main.pack2(center, True, False)
        main.set_position(400)
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
            if menu == "Run" and previous_menu != "Run":
                spacer = Gtk.SeparatorToolItem()  # run and debug controls sit at the right edge
                spacer.set_draw(False)
                spacer.set_expand(True)
                bar.insert(spacer, -1)
            elif previous_menu is not None and menu != previous_menu:
                bar.insert(Gtk.SeparatorToolItem(), -1)
            previous_menu = menu
            image = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.SMALL_TOOLBAR)
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

    def _set_logo(self) -> None:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(LOGO_PATH, 64, 64)
            self.set_icon(pixbuf)
        except GLib.Error:
            pass

    def focus_find(self) -> None:
        self.find_entry.grab_focus()

    def continue_debugging(self) -> None:
        if self.debugger is None:
            self.debug_selected()
        else:
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
        widget = self.active_notebook.get_nth_page(self.active_notebook.get_current_page())
        return next((p for p in self.pages if p.scroller is widget), None)

    @property
    def notebook(self) -> Gtk.Notebook:
        return self.active_notebook

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
        for page in self.pages:
            if page.document.path == absolute:
                notebook = page.notebook
                notebook.set_current_page(notebook.page_num(page.scroller))
                self._activate_notebook(notebook)
                return page
        return self._add_page(Document.open(absolute, self.settings_store.effective_for(absolute)))

    def _add_page(self, document: Document) -> Page:
        page = Page(document, self.palette)

        def on_mark_set(*_args) -> None:
            page.mark_current_line()
            self._update_status()
        page.buffer.connect("changed", lambda *_: self._on_changed(page))
        page.buffer.connect("mark-set", on_mark_set)
        self.pages.append(page)
        notebook = self.active_notebook
        notebook.append_page(page.scroller, page.tab_label)
        notebook.set_tab_reorderable(page.scroller, True)
        notebook.set_tab_detachable(page.scroller, True)
        notebook.show_all()
        notebook.set_current_page(notebook.page_num(page.scroller))
        page.notebook = notebook
        for line in self.breakpoints.get(document.path or "", ()):
            self._add_breakpoint_mark(page, line)
        page.update_change_marks()
        if document.path:
            self.history.snapshot(document.path, document.text, "opened")  # keeps external edits too
        self._update_status()
        return page

    def _on_changed(self, page: Page) -> None:
        page.dirty = True
        page.document.text = page.text()
        page.document.analyze()
        page.highlight()
        page.update_label()
        page.update_change_marks()
        self._update_status()
        self._schedule_autosave(page)

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

    def _after_save(self, page: Page, label: str = "save") -> None:
        if page.document.path:
            self.index.invalidate(page.document.path)
            self.history.snapshot(page.document.path, page.text(), label)
        page.baseline = page.text()
        page.dirty = False
        page.apply_settings()
        page.apply_language()
        page.highlight()
        page.update_label()
        page.update_change_marks()
        self._update_status(saved=True)
        self.refresh_history()

    def open_dialog(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Open", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        dialog.set_current_folder(self.project_dir)
        filename = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        if filename:
            self.open_path(filename)

    def close_page(self) -> None:
        page = self.page
        if page is None:
            return
        notebook = page.notebook
        self.pages.remove(page)
        if self._exec_line and self._exec_line[0] is page:
            self._exec_line = None
        notebook.remove_page(notebook.page_num(page.scroller))
        self._update_status()

    # -------------------------------------------------------- file tree

    def _tree_color(self, kind: str) -> str:
        return self.palette["string"] if kind == "test" else self.palette["foreground"]

    def _populate_tree(self, parent, folder: str) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in (".editorconfig", ".run"):
                continue
            if entry.name == "__pycache__" or self.workspace.is_excluded(entry.path):
                continue
            color = self._tree_color(self.workspace.kind(entry.path))
            node = self.tree_store.append(parent, [entry.name, entry.path, color])
            if entry.is_dir(follow_symlinks=False):
                self.tree_store.append(node, ["", "", color])  # placeholder, replaced on expand

    def _rebuild_tree(self) -> None:
        """One top-level node per workspace folder; ignored folders are not listed."""
        self.tree_store.clear()
        for folder in self.workspace.folders:
            node = self.tree_store.append(None, [os.path.basename(folder) or folder, folder,
                                                 self._tree_color("source")])
            self._populate_tree(node, folder)
            self.tree.expand_row(self.tree_store.get_path(node), False)

    def _apply_workspace(self) -> None:
        """Workspace and index from the folders and the effective settings (no tree update)."""
        props = self.settings_store.effective_for(os.path.join(self.project_dir, "_"))
        self.workspace = Workspace.from_properties(self.project_folders, props)
        self.index = ProjectIndex(self.workspace.folders, cache_path=self._cache_path(),
                                  excluded=self.workspace.is_excluded)

    def add_folder_to_workspace(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Add Folder to Workspace", parent=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
        folder = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        if folder and os.path.abspath(folder) not in self.project_folders:
            self.project_folders.append(os.path.abspath(folder))
            self._apply_workspace()
            self._rebuild_tree()
            self.status.set_text(f"workspace: {len(self.project_folders)} folder(s)")

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
            character = start.get_char()
            if not (character.isalnum() or character in "_-"):
                start.forward_char()
                break
        prefix = buffer.get_text(start, cursor, True)
        matches = self._registry_for(page).complete(prefix)
        if not matches:
            self.status.set_text(f"no template for '{prefix}' in {page.document.detection.name}")
            return
        start_offset, cursor_offset = start.get_offset(), cursor.get_offset()
        if len(matches) == 1:
            self._insert_template(page, start_offset, cursor_offset, matches[0])
        else:
            self._show_template_popover(page, start_offset, cursor_offset, matches)

    @staticmethod
    def _registry_for(page: Page) -> templates.TemplateRegistry:
        detection = page.document.detection
        return templates.registry_for(detection.language, detection.dialect,
                                      page.document.settings.custom, detection.template)

    @staticmethod
    def _insert_template(page: Page, start_offset: int, cursor_offset: int, template) -> None:
        buffer = page.buffer
        expansion = templates.expand(template)
        buffer.begin_user_action()
        buffer.delete(buffer.get_iter_at_offset(start_offset), buffer.get_iter_at_offset(cursor_offset))
        buffer.insert(buffer.get_iter_at_offset(start_offset), expansion.text)
        buffer.place_cursor(buffer.get_iter_at_offset(start_offset + expansion.cursor))
        buffer.end_user_action()

    def _show_template_popover(self, page: Page, start_offset: int, cursor_offset: int, matches) -> None:
        popover = Gtk.Popover(relative_to=page.view)
        listbox = Gtk.ListBox()
        for template in matches:
            row = Gtk.ListBoxRow()
            row.add(Gtk.Label(label=f"{template.trigger}    {template.description}", xalign=0.0))
            listbox.add(row)

        def activate(_box, row) -> None:
            popover.popdown()
            self._insert_template(page, start_offset, cursor_offset, matches[row.get_index()])
            page.view.grab_focus()
        listbox.connect("row-activated", activate)
        location = page.view.get_iter_location(page.buffer.get_iter_at_offset(cursor_offset))
        x, y = page.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, location.x, location.y)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = x, y, 1, location.height
        popover.set_pointing_to(rect)
        popover.add(listbox)
        listbox.show_all()
        popover.popup()
        self._popover = popover

    # ------------------------------------------------- project index and tools

    def _cache_path(self) -> str:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
        return os.path.join(base, "ogmkdev", hashlib.sha1(self.project_dir.encode("utf-8")).hexdigest() + ".json")

    def _save_index(self, *_args) -> None:
        try:
            self.index.save_cache()
        except (OSError, ValueError):
            pass

    def _word_at_cursor(self) -> str:
        page = self.page
        if page is None:
            return ""
        buffer = page.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        start = cursor.copy()
        while start.backward_char():
            character = start.get_char()
            if not (character.isalnum() or character in "_\\"):
                start.forward_char()
                break
        end = cursor.copy()
        while not end.is_end() and (end.get_char().isalnum() or end.get_char() in "_\\"):
            end.forward_char()
        return buffer.get_text(start, end, True).strip("\\")

    def navigate(self, file: str, line: int, column: int = 1) -> None:
        page = self.open_path(file)
        buffer = page.buffer
        last = max(buffer.get_line_count() - 1, 0)
        iterator = buffer.get_iter_at_line(min(max(line - 1, 0), last))
        iterator.forward_chars(max(column - 1, 0))
        buffer.place_cursor(iterator)
        page.view.scroll_to_iter(iterator, 0.2, False, 0.0, 0.0)

    def _location(self, file: str, line: int) -> str:
        return f"{os.path.relpath(file, self.project_dir)}:{line}"

    def _show_results(self, view: ResultsView, rows, panel: str) -> None:
        count = view.show(rows)
        self.bottom.set_current_page(self.bottom_pages[panel])
        self.status.set_text(f"{count} {panel.lower()} result(s)")

    def find_implementations(self) -> None:
        word = self._word_at_cursor()
        if not word:
            self.status.set_text("place the cursor on a class or interface name")
            return
        found = self.index.implementations(word)
        if len(found) == 1:
            self.navigate(found[0].file, found[0].line, found[0].column)
            self.status.set_text(f"implementation of {word}: {found[0].short}")
            return
        rows = [(s.short, self._location(s.file, s.line), s.file, s.line, s.column) for s in found]
        self.status.set_text(f"implementations of {word}: {len(found)}")
        self._show_results(self.search_view, rows, "Search")

    def go_to_definition(self) -> None:
        word = self._word_at_cursor()
        if not word:
            self.status.set_text("place the cursor on a name")
            return
        found = self.index.definitions(word)
        if not found:
            self.status.set_text(f"no definition for {word}")
            return
        if len(found) == 1:
            self.navigate(found[0].file, found[0].line, found[0].column)
            self.status.set_text(f"definition of {word}: {self._location(found[0].file, found[0].line)}")
            return
        rows = [(s.name, self._location(s.file, s.line), s.file, s.line, s.column) for s in found]
        self._show_results(self.search_view, rows, "Search")
        self.status.set_text(f"{len(found)} definitions of {word}")

    def organize_imports(self) -> None:
        page = self.page
        if page is None or page.document.detection.language != "php":
            self.status.set_text("organise imports works on PHP files")
            return
        text = page.text()
        organised = organize.organize(text)
        if organised == text:
            self.status.set_text("imports are already organised")
            return
        page.buffer.set_text(organised)
        self.status.set_text("imports organised")

    def show_hierarchy(self) -> None:
        word = self._word_at_cursor()
        if not word:
            self.status.set_text("place the cursor on a class or interface name")
            return
        tree = self.index.hierarchy(word)
        dependencies = []
        for name in self.index.dependencies(word):
            found = self.index.find(name)
            dependencies.append((name, found[0].file, found[0].line, found[0].column) if found else (name, "", 0, 0))
        self.hierarchy_view.show(tree, dependencies)
        self.diagram_view.show(tree)
        self.left.set_current_page(self.left_pages["Hierarchy"])
        self.status.set_text(f"type hierarchy of {word}")

    def search_in_files(self, text: Optional[str] = None) -> None:
        if text is None:
            text = self._prompt("Search in Files", "Text to find in the project:")
        if not text:
            return
        hits = self.index.find_in_files(text)
        rows = [(hit.text[:160], self._location(hit.file, hit.line), hit.file, hit.line, hit.column) for hit in hits]
        self._show_results(self.search_view, rows, "Search")
        self.status.set_text(f"{len(hits)} match(es) for '{text}'")

    def inspect_project(self) -> None:
        results = self.index.inspect()
        rows = [(f"{item.severity}: {item.message}", self._location(item.file, item.line), item.file,
                 item.line, item.column) for item in results]
        self._show_results(self.problems_view, rows, "Problems")
        self.status.set_text(f"inspection: {len(results)} problem(s)")

    def refresh_index(self) -> None:
        counts = self.index.refresh()
        self.status.set_text(f"index: {counts['added']} added, {counts['changed']} changed, "
                             f"{counts['removed']} removed")

    def open_folder(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Open Folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.OK)
        folder = dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        dialog.destroy()
        if folder:
            self.set_project(folder)

    def set_project(self, folder: str) -> None:
        self._save_index()
        self.project_dir = os.path.abspath(folder)  # noqa
        self.run_configs = runconfig.discover(self.project_dir)
        self._load_run_list()
        self.settings_store = SettingsStore(self.project_dir)
        self.project_folders = [self.project_dir]
        self._apply_workspace()
        self._rebuild_tree()
        self._refresh_settings_all()
        self.status.set_text(f"project {self.project_dir}")

    def _prompt(self, title: str, label: str) -> str:
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        content = dialog.get_content_area()
        content.pack_start(Gtk.Label(label=label, xalign=0.0), False, False, 4)
        content.pack_start(entry, False, False, 4)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.show_all()
        response = dialog.run()
        text = entry.get_text().strip()
        dialog.destroy()
        return text if response == Gtk.ResponseType.OK else ""

    # ----------------------------------------------------------- settings

    def open_global_settings(self) -> None:
        self._settings_dialog("global")

    def open_diagnostic_settings(self) -> None:
        self._settings_dialog("global", tab="Diagnostics")

    def open_project_settings(self) -> None:
        self._settings_dialog("project")

    def _settings_dialog(self, scope: str, tab: Optional[str] = None) -> None:
        title = "Preferences" if scope == "global" else "Project Settings"
        dialog = Gtk.Dialog(title=f"{title}: {self.settings_store.path_for(scope)}", transient_for=self, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Apply", Gtk.ResponseType.OK)
        current = self.settings_store.read(scope)
        notebook = Gtk.Notebook()
        widgets = {}
        for group, settings in settings_module.groups():
            grid = Gtk.Grid(column_spacing=12, row_spacing=8)
            grid.set_border_width(12)
            for row, setting in enumerate(settings):
                grid.attach(Gtk.Label(label=setting.label, xalign=0.0), 0, row, 1, 1)
                value = current.get(setting.key, setting.default)
                if setting.kind == "choice":
                    widget = Gtk.ComboBoxText()
                    for choice in setting.choices:
                        widget.append_text(choice)
                    widget.set_active(setting.choices.index(value) if value in setting.choices else 0)
                elif setting.kind == "text":
                    widget = Gtk.Entry()
                    widget.set_text(value)
                elif setting.kind == "int":
                    widget = Gtk.SpinButton.new_with_range(0, 200, 1)
                    widget.set_value(int(value) if value.isdigit() else int(setting.default))
                else:
                    widget = Gtk.CheckButton()
                    widget.set_active(value == "true")
                grid.attach(widget, 1, row, 1, 1)
                widgets[setting.key] = (setting, widget)
            notebook.append_page(grid, Gtk.Label(label=group))
            if tab == group:
                notebook.set_current_page(notebook.get_n_pages() - 1)
        dialog.get_content_area().pack_start(notebook, True, True, 0)
        dialog.set_default_size(620, 460)
        dialog.show_all()
        response = dialog.run()
        values = {}
        if response == Gtk.ResponseType.OK:
            for key, (setting, widget) in widgets.items():
                values[key] = self._widget_value(setting, widget)
        dialog.destroy()
        if values:
            self.apply_settings_values(scope, values)

    @staticmethod
    def _widget_value(setting, widget) -> str:
        if setting.kind == "choice":
            return setting.choices[widget.get_active()]
        if setting.kind == "int":
            return str(int(widget.get_value()))
        if setting.kind == "text":
            return widget.get_text().strip()
        return "true" if widget.get_active() else "false"

    def apply_settings_values(self, scope: str, values: Dict[str, str]) -> None:
        """Write values into the global or project settings and apply them to open documents."""
        self.settings_store.apply(scope, values)
        self._refresh_settings_all()
        self.status.set_text(f"{'preferences' if scope == 'global' else 'project settings'} saved")

    def _refresh_settings_all(self) -> None:
        if self._autosave_flag is None:
            self.autosave = self.settings_store.value("ogmkdev_autosave") == "on"
        self._apply_keymap()
        self._apply_workspace()
        for page in self.pages:
            path = page.document.path
            properties = self.settings_store.effective_for(path) if path else self.settings_store.global_properties()
            page.document.settings = editorconfig.settings_from_properties(properties)
            page.apply_settings()
            page.document.analyze()
            page.highlight()
        self._update_status()

    # ------------------------------------------------------- panes (split)

    def _new_notebook(self) -> Gtk.Notebook:
        notebook = Gtk.Notebook(scrollable=True)
        notebook.set_group_name("ogmkdev-editor")  # tabs can be dragged from one pane to another
        notebook.connect("switch-page", lambda *_: self._on_pane_switched(notebook))
        notebook.connect("button-press-event", lambda *_: self._activate_notebook(notebook))
        notebook.connect("page-added", lambda nb, child, _n: self._owner_changed(nb, child))
        close = Gtk.Button.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_tooltip_text("Close this pane")
        close.connect("clicked", lambda _b: self.close_pane(notebook))
        notebook.set_action_widget(close, Gtk.PackType.END)
        close.show()
        self.notebooks.append(notebook)
        return notebook

    def _on_pane_switched(self, notebook: Gtk.Notebook) -> None:
        self._activate_notebook(notebook)
        _ui(self._update_status)
        _ui(self.refresh_history)

    def _activate_notebook(self, notebook: Gtk.Notebook) -> bool:
        self.active_notebook = notebook
        return False

    def _owner_changed(self, notebook: Gtk.Notebook, child) -> None:
        for page in self.pages:
            if page.scroller is child:
                page.notebook = notebook

    def _replace_widget(self, old, new) -> None:
        parent = old.get_parent()
        if isinstance(parent, Gtk.Paned):
            first = parent.get_child1() is old
            parent.remove(old)
            (parent.pack1 if first else parent.pack2)(new, True, False)
        else:
            parent.remove(old)
            parent.pack_start(new, True, True, 0)

    def _split_notebook(self, notebook: Gtk.Notebook, orientation) -> Gtk.Notebook:
        new = self._new_notebook()
        paned = Gtk.Paned(orientation=orientation)
        self._replace_widget(notebook, paned)
        paned.pack1(notebook, True, False)
        paned.pack2(new, True, False)
        paned.show_all()
        self._activate_notebook(new)
        return new

    def split_right(self) -> None:
        self._split_notebook(self.active_notebook, Gtk.Orientation.HORIZONTAL)

    def split_down(self) -> None:
        self._split_notebook(self.active_notebook, Gtk.Orientation.VERTICAL)

    def split_four(self) -> None:
        self._grid(2, 2)

    def split_six(self) -> None:
        self._grid(2, 3)

    def _grid(self, rows: int, cols: int) -> None:
        first = self.active_notebook
        columns = [first]
        for _ in range(cols - 1):
            columns.append(self._split_notebook(columns[-1], Gtk.Orientation.HORIZONTAL))
        for column in columns:
            bottom = column
            for _ in range(rows - 1):
                bottom = self._split_notebook(bottom, Gtk.Orientation.VERTICAL)
        self._activate_notebook(first)
        self.status.set_text(f"{rows} x {cols} panes")

    def _first_leaf(self, widget) -> Gtk.Notebook:
        return self._first_leaf(widget.get_child1()) if isinstance(widget, Gtk.Paned) else widget

    def close_active_pane(self) -> None:
        self.close_pane(self.active_notebook)

    def close_pane(self, notebook: Optional[Gtk.Notebook] = None) -> None:
        """Close a pane: its tabs move to the neighbouring pane, and the split shrinks."""
        notebook = notebook or self.active_notebook
        if len(self.notebooks) <= 1:
            self.status.set_text("the last pane cannot be closed")
            return
        paned = notebook.get_parent()
        if not isinstance(paned, Gtk.Paned):
            return
        sibling = paned.get_child2() if paned.get_child1() is notebook else paned.get_child1()
        target = self._first_leaf(sibling)
        for page in [p for p in self.pages if p.notebook is notebook]:
            notebook.remove_page(notebook.page_num(page.scroller))
            page.tab_label = Gtk.Label(label=page.document.title)
            target.append_page(page.scroller, page.tab_label)
            target.set_tab_reorderable(page.scroller, True)
            target.set_tab_detachable(page.scroller, True)
            page.notebook = target
            page.update_label()
        paned.remove(notebook)
        paned.remove(sibling)
        self._replace_widget(paned, sibling)
        self.notebooks.remove(notebook)
        notebook.destroy()
        self._activate_notebook(target)
        self._update_status()

    # ------------------------------------------------------------- history

    def _build_history_panel(self) -> Gtk.Widget:
        self.history_store = Gtk.ListStore(str, str, str, str)  # label, when, size, revision id
        self.history_view = Gtk.TreeView(model=self.history_store)
        selection = self.history_view.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        for index, title in enumerate(("Label", "When", "Size")):
            self.history_view.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=index))
        selection.connect("changed", lambda *_: self._show_history_diff())
        self.history_diff = Gtk.TextView(editable=False, monospace=True)
        self.history_diff.set_cursor_visible(False)
        top = Gtk.ScrolledWindow()
        top.add(self.history_view)
        bottom = Gtk.ScrolledWindow()
        bottom.add(self.history_diff)
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.pack1(top, True, False)
        paned.pack2(bottom, True, False)
        buttons = Gtk.Box(spacing=4)
        for label, handler in (("Extract patch set...", self.extract_patch_set),
                               ("Revert to selected", self.revert_to_selected)):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, h=handler: h())
            buttons.pack_start(button, True, True, 0)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(buttons, False, False, 0)
        box.pack_start(paned, True, True, 0)
        return box

    def _selected_revisions(self) -> list:
        page = self.page
        if page is None or page.document.path is None:
            return []
        _model, paths = self.history_view.get_selection().get_selected_rows()
        chosen = {self.history_store[path][3] for path in paths}
        return [r for r in self.history.revisions(page.document.path) if r.id in chosen]

    def refresh_history(self) -> None:
        if not hasattr(self, "history_store"):
            return
        page = self.page
        self.history_store.clear()
        if page is None or page.document.path is None:
            self.history_diff.get_buffer().set_text("")
            return
        for revision in self.history.revisions(page.document.path):
            self.history_store.append([revision.label, revision.when, str(revision.size), revision.id])
        if len(self.history_store):
            self.history_view.get_selection().select_path(Gtk.TreePath.new_first())
        self._show_history_diff()

    def _show_history_diff(self) -> None:
        page = self.page
        selected = self._selected_revisions()
        if page is None or not selected:
            self.history_diff.get_buffer().set_text("")
            return
        if len(selected) == 1:
            text = self.history.diff(self.history.content(selected[0]), page.text(),
                                     f"revision {selected[0].when}", "current")
        else:
            text = self.history.patch_set(selected)
        self.history_diff.get_buffer().set_text(text or "no differences")

    def show_local_history(self) -> None:
        self.left.set_current_page(self.left_pages["History"])
        self.refresh_history()

    def extract_patch_set(self) -> None:
        page = self.page
        if page is None or page.document.path is None:
            self.status.set_text("the file has no history yet")
            return
        revisions = self._selected_revisions() or self.history.revisions(page.document.path)
        if not revisions:
            self.status.set_text("no revisions to extract")
            return
        dialog = Gtk.FileChooserDialog(title="Extract Patch Set", parent=self, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dialog.set_current_name(page.document.title + ".patch")
        dialog.set_current_folder(self.project_dir)
        response = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and filename:
            self.history.extract_patch(revisions, filename)
            self.status.set_text(f"patch set of {len(revisions)} revision(s) written to {filename}")

    def revert_to_selected(self) -> None:
        selected = self._selected_revisions()
        page = self.page
        if page is None or len(selected) != 1:
            self.status.set_text("select exactly one revision to revert to")
            return
        page.buffer.set_text(self.history.content(selected[0]))
        self.status.set_text(f"reverted to {selected[0].when} (not saved yet)")

    # ------------------------------------------------------ autosave, index

    def _schedule_autosave(self, page: Page) -> None:
        if not self.autosave or page.document.path is None:
            return
        if page.autosave_id:
            GLib.source_remove(page.autosave_id)
        page.autosave_id = GLib.timeout_add_seconds(AUTOSAVE_SECONDS, self._autosave, page)

    def _autosave(self, page: Page) -> bool:
        page.autosave_id = 0
        if page in self.pages and page.dirty and page.document.path:
            page.document.text = page.text()
            try:
                page.document.save()
            except OSError as error:
                self.status.set_text(f"autosave failed: {error}")
                return False
            self._after_save(page, "autosave")
            self.status.set_text(f"autosaved {page.document.title}")
        return False

    def _remove_index_cache(self) -> None:
        try:
            os.remove(self._cache_path())
        except OSError:
            pass

    def clear_index(self) -> None:
        self._remove_index_cache()
        self._apply_workspace()
        self.status.set_text("index cleared and rebuilt")

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

    def _apply_keymap(self) -> None:
        defaults = {method: accelerator for _m, _l, _i, accelerator, method, _t in ACTIONS if accelerator}
        properties = self.settings_store.effective_for(os.path.join(self.project_dir, "_"))
        self.bindings = keymap_module.resolve(defaults, properties)
        self.key_actions = keymap_module.by_accelerator(self.bindings)

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        mask = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
        accelerator = keymap_module.canonical(Gtk.accelerator_name(event.keyval, event.state & mask))
        method = self.key_actions.get(accelerator) if accelerator else None
        if method is None:
            return False
        getattr(self, method)()
        return True

def main(argv: List[str]) -> int:
    """Usage: python -m ogmkdev [--dark|--light] [--scheme blend|jetbrains|eclipse] [file-or-folder]"""
    mode, scheme, paths = "light", "blend", []
    autosave: Optional[bool] = None
    clear_index = False
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--dark":
            mode = "dark"
        elif arg == "--light":
            mode = "light"
        elif arg == "--scheme" and args:
            scheme = args.pop(0)
        elif arg == "--autosave":
            autosave = True
        elif arg == "--no-autosave":
            autosave = False
        elif arg == "--clear-index":
            clear_index = True
        else:
            paths.append(arg)
    if scheme not in theme.SCHEMES:
        print(f"unknown color scheme {scheme!r}; choose from {', '.join(theme.SCHEMES)}")
        return 2
    target = os.path.abspath(paths[0]) if paths else None
    if target and os.path.isdir(target):
        window = EditorWindow(None, project_dir=target, mode=mode, scheme=scheme, autosave=autosave,
                              clear_index=clear_index)
    else:
        window = EditorWindow(target, project_dir=os.path.dirname(target) if target else None,
                              mode=mode, scheme=scheme, autosave=autosave, clear_index=clear_index)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()
    return 0
