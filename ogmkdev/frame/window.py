"""The frame window (GTK 4): menu bar, toolbar, tabs, editor area with Howl editors, bottom panel,
find field and status line."""

from __future__ import annotations

import os
import time
from typing import Optional, Sequence, Union

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from ogmkdev import __version__, filetemplates, index as index_module, markup, newclass, projects, scaffold  # noqa: E402
from ogmkdev.settings import ATTACHED_KEY, SETTINGS_BY_KEY, SettingsStore, appearance_mode, folder_list, folders_text  # noqa: E402
from ogmkdev.theme import MODES, SCHEMES  # noqa: E402
from ogmkdev.outcome import Failure  # noqa: E402
from ogmkdev.progress import Progress  # noqa: E402
from ogmkdev.workspace import Workspace  # noqa: E402
from ogmkdev.bridges import kdevelop as kdevelop_bridge  # noqa: E402
from ogmkdev import jetbrains as jetbrains_import  # noqa: E402
from ogmkdev import php_paths  # noqa: E402
from ogmkdev.preview import kind_of as preview_kind  # noqa: E402
from . import theme  # noqa: E402
from .editors import EditorArea  # noqa: E402
from .howl import Editors  # noqa: E402
from .links_dialog import LinksDialog  # noqa: E402
from .menus import CONTEXT_MENU, MENUS, PENDING  # noqa: E402
from .panels import PanelsMixin  # noqa: E402
from .tabs import TabsMixin  # noqa: E402
from .tools import ToolsMixin  # noqa: E402
from .analysis import AnalysisMixin  # noqa: E402
from .debugging import DebugMixin  # noqa: E402
from .structure import StructureMixin  # noqa: E402
from .preview import PreviewMixin  # noqa: E402

HIDDEN_NAMES = {".git", "node_modules", "__pycache__"}
LOOSE_LABEL = "Loose files"  # the tree entry for open files the tree does not show
ICON_THEME = "Humanity"
APP_ICON = "ogmkdev"       # the logo (packaging/logo.svg) is installed under this name in the hicolor theme
EDGE_COLUMN_DEFAULT = 120  # the edge line when the file's EditorConfig sets no max_line_length
AUTOSAVE_SECONDS = 2       # a modified file is saved this long after it was changed (autosave)

# Toolbar: icon, tooltip, target (None for a separator)
TOOLBAR = (
    ("document-new", "New Editor", "add_editor"),
    ("document-open", "Open", "open_dialog"),
    ("document-save", "Save", "howl:save"),
    None,
    ("edit-undo", "Undo", "howl:editor-undo"),
    ("edit-redo", "Redo", "howl:editor-redo"),
    ("edit-find", "Find", "focus_find"),
    None,
    ("go-jump", "Show current file in Files", "reveal_current_file"),
    None,
    "spacer",
    ("media-playback-start", "Run", "run_selected"),
    ("system-run", "Run configurations", "show_run_tab"),
    ("media-record", "Toggle breakpoint (F9)", "howl:breakpoint-toggle"),
    ("media-skip-forward", "Step over", "step_over"),
    ("go-down", "Step into", "step_into"),
    ("go-up", "Step out", "step_out"),
    ("media-playback-stop", "Stop", "stop_process"),
    None,
    ("dialog-warning", "Inspect project (all its folders)", "inspect_folder"),
)

_frame_provider: Optional[Gtk.CssProvider] = None


def install_frame_css(mode: str, scheme: str) -> None:
    """The frame's colours from the palette of ``mode`` and ``scheme`` (ogmkdev/theme.py)."""
    global _frame_provider
    display = Gdk.Display.get_default()
    if _frame_provider is None:
        _frame_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, _frame_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        Gtk.Settings.get_for_display(display).set_property("gtk-icon-theme-name", ICON_THEME)
    _frame_provider.load_from_string(theme.frame_css(mode, scheme))


def theme_folder() -> str:
    """The folder of the Howl theme files the frame writes (under the user's cache)."""
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "ogmkdev", "themes")


class Frame(AnalysisMixin, DebugMixin, ToolsMixin, StructureMixin, PreviewMixin, TabsMixin, PanelsMixin,
            Gtk.ApplicationWindow):
    _edge_key: Optional[tuple] = None
    _loose_ref: Optional[Gtk.TreeRowReference] = None  # the tree entry 'Loose files', as a row reference
    def __init__(self, app: Gtk.Application, folder: str, files: Sequence[str] = (),
                 mode: Optional[str] = None, scheme: str = "blend", autosave: Optional[bool] = None,
                 clear_index: bool = False) -> None:
        # A mode given at the start (--mode) stays; without one, the light or dark colours of the setting apply
        self.mode_pinned = mode is not None
        self.mode = mode if mode is not None else appearance_mode(SettingsStore(folder))
        self.scheme = scheme
        install_frame_css(self.mode, scheme)
        super().__init__(application=app, title="oGMKDev")
        self.set_icon_name(APP_ICON)
        self.add_css_class("ogmkdev-frame")
        self.folder = os.path.abspath(folder)
        self.project_folders = [self.folder]  # the folders of the workspace (File > Add Folder)
        self.task_progress = Progress()  # the background task the status bar shows
        self._startup_notice = self._restore_project()  # the folders attached when the project was open last
        # Autosave saves a modified file AUTOSAVE_SECONDS after it was changed: the flag, or the setting
        self.autosave_enabled = autosave if autosave is not None else (
            SettingsStore(self.folder).value("ogmkdev_autosave") == "on")
        self._dirty_since: dict = {}
        self._poll_source = 0
        self.workspace = Workspace.from_properties(
            self.project_folders, SettingsStore(self.folder).effective_for(os.path.join(self.folder, "_")))
        self.editors = Editors()
        self.area = EditorArea(self)
        self.set_default_size(1500, 900)
        self._install_actions()
        self._install_recent_actions()
        self._install_theme_actions()
        self._install_context_menu()
        self._install_xml_menu()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        root.append(self._menubar(app))
        root.append(self._toolbar())

        right = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        right.set_start_child(self.area.root)
        right.set_resize_start_child(True)
        right.set_end_child(self._bottom())
        right.set_resize_end_child(False)
        right.set_position(600)

        main = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main.set_start_child(self._left())
        main.set_resize_start_child(False)
        main.set_shrink_start_child(False)
        main.set_position(380)
        main.set_end_child(right)
        main.set_vexpand(True)
        root.append(main)

        self.find_entry = Gtk.SearchEntry(placeholder_text="Find in files (Enter)")
        self.find_entry.connect("activate", lambda *_: self.search_in_files())
        self.find_entry.set_margin_start(6)
        self.find_entry.set_margin_end(6)
        self.find_entry.set_margin_top(4)
        self.find_entry.set_margin_bottom(4)
        root.append(self.find_entry)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("ogmkdev-statusbar")
        self.status = Gtk.Label(xalign=0)
        self.status.set_hexpand(True)
        self.progress_bar = Gtk.ProgressBar()  # the background task: shown while one runs
        self.progress_bar.set_valign(Gtk.Align.CENTER)
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_size_request(240, -1)
        self.progress_bar.set_visible(False)
        self.position = Gtk.Label(xalign=1)
        bar.append(self.status)
        bar.append(self.progress_bar)
        bar.append(self.position)
        root.append(bar)

        self._populate_tree()
        if clear_index:  # --clear-index: the cached index is dropped, the build reads every file again
            self._remove_index_cache()
        self._ensure_index()  # the project index is built in the background, as the GTK 3 window did
        self.build_left_tabs()
        self.build_bottom_tabs()
        if not files:
            self.add_editor(None)
        for path in files:
            self.open_file(path)
        # the Howl theme is selected once Howl runs (the first editor starts it)
        self._apply_howl_theme()
        self.set_status(f"folder {self.folder}" + (f"; {self._startup_notice}" if self._startup_notice else ""))
        self._remember_project()
        self._poll_source = GLib.timeout_add(500, self._poll)
        self.connect("close-request", self._on_close_request)

    # ------------------------------------------------------ tabs setup

    def build_left_tabs(self) -> None:
        self._build_run()
        self._build_hierarchy()
        self._build_structure()
        self._build_history()
        self._build_git()

    def build_bottom_tabs(self) -> None:
        self._build_watches()
        self._build_problems()
        self._build_search()
        self._build_todos()
        self._build_changes()
        self._build_preview()
        self._build_index_view()
        self._build_resources_view()

    def show_run_tab(self) -> None:
        self.left.set_current_page(self.left.page_num(self.run_box))

    # ------------------------------------------------------------ panes

    def split_right(self) -> None:
        self.area.split_right()

    def split_down(self) -> None:
        self.area.split_down()

    def split_four(self) -> None:
        self.area.split_four()

    def split_six(self) -> None:
        self.area.split_six()

    def close_active_pane(self) -> None:
        self.area.close_active_pane()

    def show_debug_stop(self, path: str, line: int) -> None:
        """The debugger stopped at a line: the file opens there, and folds that hide the line open."""
        self.open_file(path, line, 1)
        self.set_status(f"stopped at {os.path.basename(path)}:{line}")

    # ------------------------------------------------------------ menus

    def _menubar(self, app: Gtk.Application) -> Gtk.Widget:
        menu = Gio.Menu()
        for title, entries in MENUS:
            submenu = Gio.Menu()
            for label, name, accelerator, _target in entries:
                submenu.append(label, f"win.{name}")
                if accelerator:
                    app.set_accels_for_action(f"win.{name}", [accelerator])
                if name == "open-folder":
                    # File > Open Recent follows Open Folder; _refresh_recent_menu fills it
                    self._recent_menu = Gio.Menu()
                    submenu.insert_submenu(submenu.get_n_items(), "Open Recent", self._recent_menu)
            if title == "View":
                self._theme_items(submenu)
            menu.append_submenu(title, submenu)
        return Gtk.PopoverMenuBar.new_from_model(menu)

    # ------------------------------------------------------------ theme

    def _theme_items(self, submenu: Gio.Menu) -> None:
        """The theme items of the View menu: a check item for dark mode, then a radio item per colour scheme."""
        dark = Gio.Menu()
        dark.append("Dark Theme", "win.dark-theme")
        submenu.append_section(None, dark)
        schemes = Gio.Menu()
        for name in SCHEMES:
            item = Gio.MenuItem.new(f"Color scheme: {name.capitalize()}", None)
            item.set_action_and_target_value("win.color-scheme", GLib.Variant.new_string(name))
            schemes.append_item(item)
        submenu.append_section(None, schemes)

    def _install_theme_actions(self) -> None:
        """Dark mode is an action with a boolean state, the colour scheme one with a string state: the menu
        shows the current choice with a check mark or a radio mark."""
        self._dark_action = Gio.SimpleAction.new_stateful("dark-theme", None,
                                                          GLib.Variant.new_boolean(self.mode == "dark"))
        self._dark_action.connect("activate", lambda _action, _parameter: self.set_theme(
            "light" if self.mode == "dark" else "dark"))
        self.add_action(self._dark_action)
        self._scheme_action = Gio.SimpleAction.new_stateful("color-scheme", GLib.VariantType.new("s"),
                                                            GLib.Variant.new_string(self.scheme))
        self._scheme_action.connect("activate", lambda _action, parameter: self.set_theme(
            self.mode, parameter.get_string()))
        self.add_action(self._scheme_action)

    def set_theme(self, mode: str, scheme: Optional[str] = None) -> None:
        """Switches between light and dark mode and between colour schemes while the frame runs: the frame's
        colours, the Howl theme of the editors, the marks of the View menu and the folder colours. The CSS and
        Howl belong to the whole process, so every open frame follows."""
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        if scheme is not None and scheme not in SCHEMES:
            raise ValueError(f"unknown colour scheme {scheme!r}")
        scheme = scheme or self.scheme
        for frame in self._open_frames():
            frame.mode, frame.scheme = mode, scheme
            frame._sync_theme_actions()
            frame._refresh_role_colours()
            frame.class_diagram.set_palette(theme.palette_for(mode, scheme))
        install_frame_css(mode, scheme)
        self._apply_howl_theme()
        self.set_status(f"theme {theme.theme_name(mode, scheme)}")

    def _open_frames(self) -> list:
        """This frame and the other frames of the application."""
        application = self.get_application()
        windows = application.get_windows() if application is not None else []
        return [self] + [window for window in windows if isinstance(window, Frame) and window is not self]

    def _sync_theme_actions(self) -> None:
        self._dark_action.set_state(GLib.Variant.new_boolean(self.mode == "dark"))
        self._scheme_action.set_state(GLib.Variant.new_string(self.scheme))

    def _refresh_role_colours(self) -> None:
        """The folder rows of the tree keep the colour of their role, which depends on the mode."""
        def refresh(model, _path, iterator):
            if model[iterator][2] == "folder":
                model[iterator][3] = self._role_colour(model[iterator][1])
            return False  # keep walking the tree

        self.tree_store.foreach(refresh)

    def _apply_howl_theme(self) -> None:
        """Registers the Howl theme of the frame's mode and scheme and selects it in the editors."""
        self.editors.theme(theme.theme_name(self.mode, self.scheme),
                           theme.write_howl_theme(self.mode, self.scheme, theme_folder()))

    def _toolbar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        bar.add_css_class("ogmkdev-toolbar")
        for item in TOOLBAR:
            if item == "spacer":
                spacer = Gtk.Box()
                spacer.set_hexpand(True)
                bar.append(spacer)
                continue
            if item is None:
                separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                separator.set_margin_start(4)
                separator.set_margin_end(4)
                bar.append(separator)
                continue
            icon, tooltip, target = item
            button = Gtk.Button.new_from_icon_name(icon)
            button.set_tooltip_text(tooltip)
            button.add_css_class("flat")
            button.connect("clicked", lambda _b, t=target: self._run_target(t))
            bar.append(button)
        return bar

    def _install_actions(self) -> None:
        for _title, entries in MENUS:
            for _label, name, _accelerator, target in entries:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, t=target: self._run_target(t))
                self.add_action(action)

    def _install_context_menu(self) -> None:
        """The right-click menu of the editor area: a popover of the window, so it lies over the
        Howl editors and the rest of the frame."""
        groups: list = [[]]
        for item in CONTEXT_MENU:
            if item is None:
                groups.append([])
            else:
                groups[-1].append(item)
        model = Gio.Menu()
        for group in groups:
            section = Gio.Menu()
            for label, name, _target in group:
                section.append(label, f"win.{name}")
            model.append_section(None, section)
        for group in groups:
            for _label, name, target in group:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, t=target: self._run_target(t))
                self.add_action(action)
        self._context_popover = Gtk.PopoverMenu.new_from_model(model)
        self._context_popover.set_parent(self.area.root)
        self._context_popover.set_has_arrow(False)
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", self._on_context_pressed)
        self.area.root.add_controller(click)

    def _on_context_pressed(self, gesture, _n_press, x, y) -> None:
        if gesture.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            self.show_xml_menu(x, y)  # Ctrl+right-click: the element menu of XML, SVG and HTML
            return
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._context_popover.set_pointing_to(rect)
        self._context_popover.popup()

    def _run_target(self, target: str) -> None:
        if target.startswith("howl:"):
            command = target[len("howl:"):]
            if not self.editors.command(command):
                self.set_status(f"{command}: no Howl editor has the focus")
            return
        getattr(self, target)()

    def __getattr__(self, name: str):
        # entries and buttons whose feature is not wired yet report that instead of failing
        if name in PENDING:
            return lambda *_args: self.set_status(f"{PENDING[name]} is not wired in the frame yet")
        raise AttributeError(name)

    # ------------------------------------------------------- Files tree

    def _left(self) -> Gtk.Widget:
        # name, absolute path ("" for a placeholder), icon, colour of the folder's role (None: no colour)
        self.tree_store = Gtk.TreeStore(str, str, str, str)
        self.tree = Gtk.TreeView(model=self.tree_store)
        self.tree.set_headers_visible(False)
        self.tree.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererPixbuf(), icon_name=2))
        self.tree.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0, foreground=3))
        self.tree.connect("row-expanded", self._on_row_expanded)
        self.tree.connect("row-activated", self._on_row_activated)
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.tree)
        scroller.set_vexpand(True)
        self.files_page = scroller
        self.left = Gtk.Notebook()
        self.left.set_scrollable(True)  # tabs scroll: the panel does not grow with its tab labels
        self.left.append_page(scroller, Gtk.Label(label="Files"))
        return self.left

    def _populate_tree(self) -> None:
        for folder in self.workspace.folders:
            node = self.tree_store.append(None, [os.path.basename(folder) or folder, folder, "folder", None])
            self._fill(node, folder)
            self.tree.expand_row(self.tree_store.get_path(node), False)

    def _fill(self, parent, folder: str) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for entry in entries:
            if entry.name in HIDDEN_NAMES or self.workspace.is_hidden(entry.path):
                continue
            is_dir = entry.is_dir(follow_symlinks=False)
            node = self.tree_store.append(parent, [entry.name, entry.path,
                                                   "folder" if is_dir else "text-x-generic",
                                                   self._role_colour(entry.path) if is_dir else None])
            if is_dir:
                self.tree_store.append(node, ["", "", "", None])  # filled when the folder is expanded

    def _role_colour(self, path: str) -> Optional[str]:
        role = self.workspace.role(path)
        return theme.role_colour(self.mode, role) if role else None

    def _loose_iter(self) -> Optional[Gtk.TreeIter]:
        """The tree entry 'Loose files' as an iterator, or None when there is no such entry. A row reference follows
        the entry through the changes of the tree; an iterator would be stale once the tree was cleared."""
        if self._loose_ref is None or not self._loose_ref.valid():
            self._loose_ref = None
            return None
        return self.tree_store.get_iter(self._loose_ref.get_path())

    def _sync_loose(self) -> None:
        """Open files the tree does not show (ignored, hidden or outside the folders) hang loose below the
        'Loose files' entry at the end of the tree; a file that is closed leaves it again."""
        loose = [path for path in self.editors.files()
                 if self.workspace.folder_of(path) is None or self.workspace.is_hidden(path)]
        shown = set(loose)
        present = set()
        root = self._loose_iter()
        if root is not None:
            child = self.tree_store.iter_children(root)
            while child is not None:
                following = self.tree_store.iter_next(child)
                path = self.tree_store[child][1]
                if path in shown:
                    present.add(path)
                else:
                    self.tree_store.remove(child)
                child = following
        for path in loose:
            if path in present:
                continue
            root = self._loose_iter()
            if root is None:
                root = self.tree_store.append(None, [LOOSE_LABEL, "", "document-properties", None])
                self._loose_ref = Gtk.TreeRowReference.new(self.tree_store, self.tree_store.get_path(root))
            self.tree_store.append(root, [os.path.basename(path), path, "text-x-generic", None])
            self.tree.expand_row(self.tree_store.get_path(root), False)
        root = self._loose_iter()
        if root is not None and not self.tree_store.iter_n_children(root):
            self.tree_store.remove(root)
            self._loose_ref = None

    def _reveal_loose(self, path: str) -> bool:
        """Selects an open file that hangs loose below 'Loose files'."""
        root = self._loose_iter()
        if root is None:
            return False
        child = self.tree_store.iter_children(root)
        while child is not None:
            if self.tree_store[child][1] == path:
                self.tree.expand_row(self.tree_store.get_path(root), False)
                self.tree.get_selection().select_iter(child)
                self.tree.scroll_to_cell(self.tree_store.get_path(child), None, True, 0.5, 0.0)
                return True
            child = self.tree_store.iter_next(child)
        return False

    def _on_row_expanded(self, _view, iterator, _path) -> None:
        if self.tree_store.iter_n_children(iterator) == 1:
            first = self.tree_store.iter_nth_child(iterator, 0)
            if self.tree_store[first][1] == "":
                self.tree_store.remove(first)
                self._fill(iterator, self.tree_store[iterator][1])

    def _on_row_activated(self, _view, path, _column) -> None:
        target = self.tree_store[self.tree_store.get_iter(path)][1]
        if target and os.path.isfile(target):
            self.open_file(target)

    def reveal_current_file(self) -> None:
        """Shows the file of the active tab in the Files tree: its folders open, the file is selected."""
        path = self.area.current_path()
        if not path:
            self.set_status("no file to show in the Files tree")
            return
        if self.reveal_in_tree(path) or self._reveal_loose(path):
            self.left.set_current_page(self.left.page_num(self.files_page))
            self.set_status(f"shown in Files: {path}")
        else:
            self.set_status(f"{path} is not in the workspace folders")

    def reveal_in_tree(self, path: str) -> bool:
        store = self.tree_store
        for index in range(store.iter_n_children(None)):
            root = store.iter_nth_child(None, index)
            root_path = store[root][1]
            if not root_path:
                continue  # the 'Loose files' entry is not a folder
            if path != root_path and not path.startswith(root_path + os.sep):
                continue
            node = root
            for part in os.path.relpath(path, root_path).split(os.sep):
                if part in ("", "."):
                    continue
                self._fill_if_placeholder(node)
                child = store.iter_children(node)
                found = None
                while child is not None:
                    if store[child][0] == part:
                        found = child
                        break
                    child = store.iter_next(child)
                if found is None:
                    return False
                node = found
            self.tree.expand_to_path(store.get_path(node))
            self.tree.get_selection().select_iter(node)
            self.tree.scroll_to_cell(store.get_path(node), None, True, 0.5, 0.0)
            return True
        return False

    def _fill_if_placeholder(self, iterator) -> None:
        if self.tree_store.iter_n_children(iterator) == 1:
            first = self.tree_store.iter_nth_child(iterator, 0)
            if self.tree_store[first][1] == "":
                self.tree_store.remove(first)
                self._fill(iterator, self.tree_store[iterator][1])

    # ----------------------------------------------------------- editors

    def add_editor(self, path: Optional[str] = None) -> bool:
        """A new Howl editor in a tab of the active pane, with ``path`` if given."""
        page = self.area.open(path)
        if page is None:
            self.set_status("the Howl editor could not be started")
            return False
        self.set_status(f"{self.area.count()} editor(s)" + (f" · {path}" if path else ""))
        return True

    def open_file(self, path: str, line: int = 0, column: int = 0) -> None:
        """Shows a file in its tab (opened in a new Howl editor if needed) and moves to a line. An image is shown in
        the Preview page instead: Howl edits text."""
        if os.path.isdir(path):
            self.set_status(f"{path} is a folder, not a file")
            return
        if preview_kind(path) == "image":
            self.preview_image(path)
            self.set_status(f"preview of {path}")
            return
        page = self.area.open(path)
        if page is None:
            self.set_status(f"could not open {path}")
            return
        # the editor of the page takes the keyboard focus first: Howl opens the line in the editor that has the focus
        self.editors.focus(page)
        if line:
            self.editors.open(path, line, column)
        self.set_status(f"opened {path}")

    def save_current(self) -> None:
        """Save: the file of the focused editor. A buffer without a file gets its name in the Save As dialog."""
        if self.editors.status() is None:
            self.save_as()
            return
        self.editors.command("save")

    def save_as(self) -> None:
        """Save As: a native dialog names the file, which gets the text of the focused editor. Howl shows no prompt."""
        info = self.editors.status()
        folder = os.path.dirname(info["path"]) if info else self.folder
        native = Gtk.FileChooserNative.new("Save As", self, Gtk.FileChooserAction.SAVE, "Save", "Cancel")
        native.set_current_folder(Gio.File.new_for_path(folder))
        if info:
            native.set_current_name(os.path.basename(info["path"]))
        native.set_do_overwrite_confirmation(True)
        self._save_native = native  # kept until the dialog answers
        native.connect("response", self._on_save_as_response)
        native.show()

    def _on_save_as_response(self, native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            target = native.get_file().get_path()
            if self.editors.save_as(target):
                self.set_status(f"saved as {target}")
            else:
                self.set_status(f"could not save as {target}")
        self._save_native = None

    # ------------------------------------------------------- new components

    def new_react_component(self) -> None:
        self._new_component_dialog("react")

    def new_vue_component(self) -> None:
        self._new_component_dialog("vue")

    def new_svelte_component(self) -> None:
        self._new_component_dialog("svelte")

    def new_angular_component(self) -> None:
        self._new_component_dialog("angular")

    def new_lit_component(self) -> None:
        self._new_component_dialog("lit")

    def _new_component_dialog(self, framework: str) -> None:
        self.ask_text(f"New {framework.capitalize()} component", "Name (for example cart item):",
                      lambda name: self._create_component(framework, name))

    def _create_component(self, framework: str, name: str) -> None:
        """Creates the files of a component next to the current file (or in the folder), opens the main file
        at the cursor of its template, and never overwrites a file."""
        current = self.area.current_path()
        folder = os.path.dirname(current) if current else self.folder
        try:
            files = scaffold.component_files(framework, name)
        except ValueError as problem:
            self.set_status(str(problem))
            return
        taken = [file_name for file_name, _text, _cursor in files
                 if os.path.exists(os.path.join(folder, file_name))]
        if taken:
            self.set_status(f"not created, these files exist already: {', '.join(taken)}")
            return
        for file_name, text, _cursor in files:
            with open(os.path.join(folder, file_name), "w", encoding="utf-8") as handle:
                handle.write(text)
        main_name, main_text, cursor = files[0]
        main_path = os.path.join(folder, main_name)
        line = main_text[:cursor].count("\n") + 1
        column = cursor - (main_text.rfind("\n", 0, cursor) + 1) + 1
        self.open_file(main_path, line, column)
        self.set_status(f"created the {framework} component: {', '.join(name for name, _t, _c in files)}")

    def new_file_from_template(self) -> None:
        self.ask_text("New file from template", "File name (for example cart.php):",
                      self._create_file_from_template)

    def _create_file_from_template(self, file_name: str) -> None:
        """Creates a file next to the current one (or in the folder) from the file template of its extension,
        opens it with the cursor where the template puts it, and never overwrites a file."""
        current = self.area.current_path()
        folder = os.path.dirname(current) if current else self.folder
        properties = SettingsStore(self.folder).effective_for(os.path.join(folder, file_name.strip() or "_"))
        try:
            created = filetemplates.create_new_file(folder, file_name, self.folder, properties)
        except ValueError as problem:
            self.set_status(str(problem))
            return
        self.open_file(created.path, created.line, created.column)
        self.set_status(created.message)

    def new_class(self) -> None:
        self.ask_text("New class", "File name (for example CartItem.php):", self._new_class_named)

    def _new_class_named(self, file_name: str) -> None:
        if filetemplates.extension_of(file_name.strip()) == "php":
            self.ask_text("New class", "Namespace (empty: from the folder, - for none):",
                          lambda namespace: self._new_class_imports(file_name, namespace))
        else:
            self._new_class_imports(file_name, "")

    def _new_class_imports(self, file_name: str, namespace: str) -> None:
        self.ask_text("New class", "Imports, comma separated (empty for none):",
                      lambda imports: self._create_class(file_name, namespace, imports))

    def _create_class(self, file_name: str, namespace: str, imports: str) -> None:
        """Writes a class file next to the current one (or in the folder), opens it with the cursor in the
        class body, and never overwrites a file."""
        current = self.area.current_path()
        folder = os.path.dirname(current) if current else self.folder
        try:
            created = newclass.create_class_file(folder, file_name, self.folder, namespace, imports.split(","))
        except ValueError as problem:
            self.set_status(str(problem))
            return
        self.open_file(created.path, created.line, created.column)
        self.set_status(created.message)

    def new_editor(self) -> None:
        self.add_editor(None)

    def close_tab(self) -> None:
        """Closes the tab that is shown. Its own editor is released, not the focused one: Howl's focus may still be
        on another file, while the shown tab is the one the user closes."""
        page = self.area.current_page()
        if page is None:
            self.set_status("no tab to close")
            return
        self.area._close_page(page)

    # ------------------------------------------------------ bottom panel

    def _bottom(self) -> Gtk.Widget:
        self.console = Gtk.TextView(editable=False, monospace=True)
        self.console.set_cursor_visible(False)
        self.console_buffer = self.console.get_buffer()
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.console)
        self.bottom = Gtk.Notebook()
        self.bottom.append_page(scroller, Gtk.Label(label="Console"))
        self.bottom.set_size_request(-1, 160)
        return self.bottom

    def log(self, text: str) -> None:
        self.console_buffer.insert(self.console_buffer.get_end_iter(), text + "\n")

    def set_status(self, text: str) -> None:
        self.status.set_text(text)

    # ------------------------------------------------- live status, history

    def _update_progress(self) -> None:
        """The background task in the status bar: a bar with its share while the task knows its size, a bar that
        pulses while it does not, and no bar while no task runs."""
        task = self.task_progress
        self.progress_bar.set_visible(task.running)
        if not task.running:
            return
        if task.total > 0:
            done = min(task.done, task.total)
            self.progress_bar.set_fraction(done / task.total)
            self.progress_bar.set_text(f"{task.label}: {done} of {task.total} files")
        else:
            self.progress_bar.pulse()
            self.progress_bar.set_text(f"{task.label}: scanning the folders")

    def _poll(self) -> bool:
        info = self.editors.status()
        path = info["path"] if info else self.area.current_path()
        if info:
            state = "modified" if info["modified"] else "saved"
            self.position.set_text(f"{os.path.basename(info['path'])}   {info['line']}:{info['column']}"
                                   f"   {info['mode']}   {state}")
        self._autosave_tick(info, path)
        self.track_history(path)
        self._follow_focus(path)
        self._follow_changes(info, path)
        self._sync_loose()
        self._update_progress()
        self._follow_structure(path)
        self._follow_preview()
        click = self.editors.take_click()
        if click:
            self._follow_click(*click)
        return True

    def _on_close_request(self, _window) -> bool:
        """The window is closing: its status poll and its resources timer stop (a closed frame must not act on the Howl
        editors)."""
        if self._poll_source:
            GLib.source_remove(self._poll_source)
            self._poll_source = 0
        if getattr(self, "_resources_source", 0):
            GLib.source_remove(self._resources_source)
            self._resources_source = 0
        self.stop_services()  # a background service of the Run tab does not outlive the frame
        return False

    def _autosave_tick(self, info, path: Optional[str]) -> None:
        """Saves the focused file once it has been modified for AUTOSAVE_SECONDS (the status is polled)."""
        if not info or not path:
            return
        if not (info["modified"] and self.autosave_enabled and os.path.isfile(path)):
            self._dirty_since.pop(path, None)
            return
        since = self._dirty_since.setdefault(path, time.monotonic())
        if time.monotonic() - since >= AUTOSAVE_SECONDS:
            self._dirty_since.pop(path, None)
            self.editors.command("save")
            self.set_status(f"autosaved {os.path.basename(path)}")

    def _follow_click(self, word: str, column: int, line: str) -> None:
        """Ctrl+click: a file reference (href, src, url(...)) opens its file, and in a PHP file a path built from
        __DIR__ opens the file next to it; anything else goes to the definition of the word."""
        current = self.area.current_path()
        if current and column and os.path.splitext(current)[1].lower() in index_module.PHP_EXTENSIONS:
            target = php_paths.path_at(line, column, os.path.dirname(current))
            if target is not None:
                if os.path.isfile(target):
                    self.open_file(target)
                    self.set_status(f"opened {target}")
                else:
                    self.set_status(f"{target} is not a file")
                return
        value = markup.reference_at(line, column) if column and self._markup_enabled(current) else None
        if value and not value.startswith("#") and "://" not in value and not value.startswith("mailto:"):
            target = value.split("#", 1)[0].split("?", 1)[0]
            current = self.area.current_path()
            base = os.path.dirname(current) if current else self.folder
            path = os.path.normpath(os.path.join(base, target))
            if os.path.isfile(path):
                self.open_file(path)
                self.set_status(f"opened the reference {value}")
            else:
                self.set_status(f"the reference {value} is not a file next to this one")
            return
        self._go_to_word(word)

    def _follow_focus(self, path: Optional[str]) -> None:
        """The edge line and the display options (syntax colours, current line) of the editors of a file: the
        column of its EditorConfig max_line_length, and its ogmkdev_syntax_highlight and ogmkdev_current_line."""
        key = (path, self.editors.count)
        if not path or key == self._edge_key:
            return
        self._edge_key = key
        settings = self._settings_for(path)
        self.editors.set_edge(path, settings.max_line_length or EDGE_COLUMN_DEFAULT)
        custom = settings.custom
        syntax = custom.get("ogmkdev_syntax_highlight", "on").strip().lower() != "off"
        current_line = custom.get("ogmkdev_current_line", "true").strip().lower() not in ("false", "off", "no", "0")
        self.editors.options(path, syntax, current_line)
        self._apply_change_colours()

    def _apply_change_colours(self) -> None:
        """The colours of the change stripes in the gutters: the project's ogmkdev_change_color_* settings."""
        store = SettingsStore(self.folder)
        folder_path = os.path.join(self.folder, "_")
        self.editors.change_colours(*(store.value(f"ogmkdev_change_color_{kind}", folder_path)
                                      for kind in ("added", "modified", "deleted")))

    def _settings_changed(self) -> None:
        """The settings were saved: the edge line and the display options of the focused file are applied again
        on the next poll."""
        self._edge_key = None

    def _go_to_word(self, word: str) -> None:
        """Ctrl+click in the Howl editor: the definition of the word. The ids of XML, SVG and HTML documents
        are definitions only where the inspection applies (not in PHP files)."""
        self._ensure_index()
        here = self._markup_enabled(self.area.current_path())
        symbols = [s for s in self.index.definitions(word) if s.kind not in ("id", "declaration") or here]
        if not symbols:
            self.set_status(f"no definition of {word} in the folder")
            return
        if len(symbols) == 1:
            self.open_file(symbols[0].file, symbols[0].line, symbols[0].column or 1)
        else:
            self._show_symbols(f"definition(s) of {word}", symbols)

    # ---------------------------------------------------- menu actions

    # ------------------------------------------------------------ project

    def open_folder(self) -> None:
        """File > Open Folder: the folder becomes the project, with its tree, run configurations, settings
        and index."""
        self._choose_folder("Open Folder", "Open", self.set_project)

    def add_folder_to_workspace(self) -> None:
        """File > Add Folder to Workspace: another folder joins the tree and the index of the project."""
        self._choose_folder("Add Folder to Workspace", "Add", self._add_workspace_folder)

    def import_kdevelop_project(self) -> None:
        """File > Import KDevelop Project...: the launch configurations of a KDevelop project (its .kdev4 file) become run
        configurations in the project's folder, and that folder is opened as the project. Its tree stays as it is."""
        native = Gtk.FileChooserNative.new("Import KDevelop Project", self, Gtk.FileChooserAction.OPEN, "Import",
                                           "Cancel")
        self._kdevelop_native = native  # kept until the dialog answers
        native.connect("response", self._on_kdevelop_chosen)
        native.show()

    def _on_kdevelop_chosen(self, native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            path = native.get_file().get_path()
            result = kdevelop_bridge.import_project(path)
            if isinstance(result, Failure):
                self.set_status(f"not imported: {result}")
            else:
                self.set_project(os.path.dirname(os.path.abspath(path)))
                report = (f"KDevelop project imported: {len(result.written)} run configuration(s), "
                          f"{len(result.existing)} kept, {len(result.skipped)} skipped")
                self.set_status(report + (f" ({'; '.join(result.skipped)})" if result.skipped else ""))
        self._kdevelop_native = None

    def import_jetbrains_project(self) -> None:
        """File > Import JetBrains Project...: the folder of a JetBrains project opens as the project. Its shared run
        configurations (.run and .idea/runConfigurations) are used where they are."""
        native = Gtk.FileChooserNative.new("Import JetBrains Project", self, Gtk.FileChooserAction.SELECT_FOLDER,
                                           "Import", "Cancel")
        self._jetbrains_native = native  # kept until the dialog answers
        native.connect("response", self._on_jetbrains_chosen)
        native.show()

    def _on_jetbrains_chosen(self, native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            result = jetbrains_import.import_project(native.get_file().get_path())
            if isinstance(result, Failure):
                self.set_status(f"not imported: {result}")
            else:
                self.set_project(result.folder)
                listed = f"; listed only: {', '.join(result.listed)}" if result.listed else ""
                self.set_status(f"JetBrains project: {len(result.runnable)} run configuration(s) can run here{listed}")
        self._jetbrains_native = None

    def _choose_folder(self, title: str, accept: str, on_chosen) -> None:
        native = Gtk.FileChooserNative.new(title, self, Gtk.FileChooserAction.SELECT_FOLDER, accept, "Cancel")
        self._folder_native = native  # kept until the dialog answers
        native.connect("response", lambda dialog, response: self._on_folder_chosen(dialog, response, on_chosen))
        native.show()

    def _on_folder_chosen(self, native, response, on_chosen) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            on_chosen(native.get_file().get_path())
        self._folder_native = None

    def _restore_project(self) -> str:
        """Attaches the folders the project had the last time it was open: the ones its project settings name, or, when
        the settings name none, the ones the projects file remembers. Returns what to tell the user: how many folders
        came back, or why the projects file could not be read (the project then opens with its own folder)."""
        self._linked = []  # the folders of the projects linked to this one: they are project folders too
        configured = self._configured_folders()
        if configured is not None:
            attached = [folder for folder in configured if os.path.isdir(folder)]
        else:
            remembered = projects.attached_folders(self.folder)
            if isinstance(remembered, Failure):
                return f"projects file not read: {remembered}"
            attached = remembered
        for folder in attached:
            if folder not in self.project_folders:
                self.project_folders.append(folder)
        linked = projects.linked_folders(self.folder)
        if isinstance(linked, Failure):
            return f"projects file not read: {linked}"
        for folder in linked:
            if folder not in self.project_folders:
                self.project_folders.append(folder)
                self._linked.append(folder)
        restored = len(self.project_folders) - 1
        return f"{restored} attached folder(s) restored" if restored else ""

    def _remember_project(self) -> None:
        """Saves the project with the folders attached to it, so that opening it again restores them. A projects file
        that cannot be read is not overwritten; the status bar tells why nothing was saved."""
        saved = projects.remember(self.folder, [folder for folder in self.project_folders[1:]
                                                if folder not in self._linked])
        if isinstance(saved, Failure):
            self.set_status(f"project not saved: {saved}")
        self._refresh_recent_menu()

    def _install_recent_actions(self) -> None:
        """The actions of File > Open Recent: one opens the project whose folder is the string parameter, the other is the
        placeholder of an empty list (disabled)."""
        opener = Gio.SimpleAction.new("open-recent", GLib.VariantType.new("s"))
        opener.connect("activate", lambda _action, parameter: self.set_project(parameter.get_string()))
        self.add_action(opener)
        none = Gio.SimpleAction.new("recent-none", None)
        none.set_enabled(False)
        self.add_action(none)

    def _refresh_recent_menu(self) -> None:
        """File > Open Recent lists the projects opened last, except the project that is open now. A projects file that
        cannot be read leaves the placeholder, the status bar tells why nothing was saved."""
        menu = self._recent_menu
        menu.remove_all()
        found = projects.recent_projects(exclude=self.folder)
        if isinstance(found, Failure) or not found:
            menu.append_item(Gio.MenuItem.new("No other recent project", "win.recent-none"))
            return
        for project in found:
            item = Gio.MenuItem.new(project.folder, None)
            item.set_action_and_target_value("win.open-recent", GLib.Variant.new_string(project.folder))
            menu.append_item(item)

    def _configured_folders(self) -> Optional[list]:
        """The folders the project settings (the project's .editorconfig) name, as absolute paths; None when the settings
        name none. A key that is there with an empty value names none on purpose."""
        values = SettingsStore(self.folder).read("project")
        if ATTACHED_KEY not in values:
            return None
        return [os.path.normpath(os.path.join(self.folder, item)) for item in folder_list(values[ATTACHED_KEY])]

    def _store_attached_folders(self) -> None:
        """Writes the attached folders into the project settings, relative to the project folder, so that opening the
        project again finds them there, whichever way they were attached."""
        relative = [os.path.relpath(folder, self.folder) for folder in self.project_folders[1:]
                    if folder not in self._linked]  # the links are kept in the projects file, not here
        SettingsStore(self.folder).write("project", SETTINGS_BY_KEY[ATTACHED_KEY], folders_text(relative))

    def _sync_attached_folders(self) -> None:
        """After the settings are saved: the folders the project settings name become the attached folders, so that the
        settings dialog and File > Add Folder agree. Settings that name no folders change nothing."""
        configured = self._configured_folders()
        if configured is None:
            return
        attached = [folder for folder in configured if os.path.isdir(folder) and folder != self.folder]
        linked = [folder for folder in self._linked if os.path.isdir(folder) and folder not in attached]
        if attached + linked != self.project_folders[1:]:
            self.project_folders = [self.folder] + attached + linked
            self._linked = linked
            self._reload_project()
            self.set_status(f"workspace: {len(self.project_folders)} folder(s)")
            self._remember_project()

    def show_linked_projects(self) -> LinksDialog:
        """File > Linked Projects...: the projects linked to this one; a link brings its folder into the project."""
        dialog = LinksDialog(self, lambda: list(self._linked), self.link_project_folder, self.unlink_project_folder)
        dialog.present()
        return dialog

    def link_project_folder(self, path: str) -> Union[str, Failure]:
        """Links another project to this one: its folder becomes part of this project now, and again whenever this project
        is opened. The link is kept in the projects file. Returns the path of that file, or the reason it was not saved."""
        folder = os.path.abspath(path)
        saved = projects.link_project(self.folder, folder)
        if isinstance(saved, Failure):
            self.set_status(f"link not saved: {saved}")
            return saved
        if folder not in self.project_folders:
            self.project_folders.append(folder)
            self._linked.append(folder)
        self._reload_project()
        self.set_status(f"linked project {folder}")
        return saved

    def unlink_project_folder(self, path: str) -> Union[str, Failure]:
        """Removes the link to another project. A folder that the project settings attach stays attached."""
        folder = os.path.abspath(path)
        saved = projects.unlink_project(self.folder, folder)
        if isinstance(saved, Failure):
            self.set_status(f"unlink not saved: {saved}")
            return saved
        if folder in self._linked:
            self._linked.remove(folder)
            if folder not in (self._configured_folders() or []) and folder in self.project_folders:
                self.project_folders.remove(folder)
        self._reload_project()
        self.set_status(f"unlinked project {folder}")
        return saved

    def set_project(self, folder: str) -> None:
        """The folder becomes the project: its tree, its run configurations, its settings and its index."""
        self.folder = os.path.abspath(folder)
        self.project_folders = [self.folder]
        notice = self._restore_project()
        self._reload_project()
        self.set_status(f"project {self.folder}" + (f"; {notice}" if notice else ""))
        self._remember_project()

    def _add_workspace_folder(self, folder: str) -> None:
        folder = os.path.abspath(folder)
        if folder not in self.project_folders:
            self.project_folders.append(folder)
        self._reload_project()
        self.set_status(f"workspace: {len(self.project_folders)} folder(s)")
        self._store_attached_folders()  # the project settings keep the folders, so that they come back
        self._remember_project()

    def _reload_project(self) -> None:
        """Rebuilds what depends on the project folders: the workspace, the tree, the run list and the index
        (built in the background; the index is empty until then)."""
        self.workspace = Workspace.from_properties(
            self.project_folders, SettingsStore(self.folder).effective_for(os.path.join(self.folder, "_")))
        self.tree_store.clear()
        self._populate_tree()
        self.refresh_run()
        self.index = index_module.ProjectIndex([])
        self._request_index_build("building the index in the background")

    def open_dialog(self) -> None:
        self._native = Gtk.FileChooserNative.new("Open", self, Gtk.FileChooserAction.OPEN, "Open", "Cancel")
        self._native.set_current_folder(Gio.File.new_for_path(self.folder))
        self._native.connect("response", self._on_open_response)
        self._native.show()

    def _on_open_response(self, native, response) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file():
            self.open_file(native.get_file().get_path())

    def quit_frame(self) -> None:
        self.get_application().quit()

    def show_about(self) -> None:
        about = Gtk.AboutDialog(transient_for=self, modal=True, program_name="oGMKDev", version=__version__,
                                comments="A lightweight editor: Howl as the editing surface, with a project index "
                                         "and debugging.")
        about.set_license_type(Gtk.License.GPL_2_0_ONLY)
        about.set_logo_icon_name(APP_ICON)  # the logo is installed as the icon of the application
        about.present()
