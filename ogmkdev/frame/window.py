"""The frame window (GTK 4): menu bar, toolbar, tabs, editor area with Howl editors, bottom panel,
find field and status line."""

from __future__ import annotations

import os
import time
from typing import Optional, Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from ogmkdev import filetemplates, index as index_module, markup, newclass, scaffold  # noqa: E402
from ogmkdev.settings import SettingsStore  # noqa: E402
from ogmkdev.workspace import Workspace  # noqa: E402
from . import theme  # noqa: E402
from .editors import EditorArea  # noqa: E402
from .howl import Editors  # noqa: E402
from .menus import CONTEXT_MENU, MENUS, PENDING  # noqa: E402
from .panels import PanelsMixin  # noqa: E402
from .tabs import TabsMixin  # noqa: E402
from .tools import ToolsMixin  # noqa: E402
from .analysis import AnalysisMixin  # noqa: E402
from .debugging import DebugMixin  # noqa: E402
from .structure import StructureMixin  # noqa: E402

HIDDEN_NAMES = {".git", "node_modules", "__pycache__"}
LOOSE_LABEL = "Loose files"  # the tree entry for open files the tree does not show
ICON_THEME = "Humanity"
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
    ("dialog-warning", "Inspect folder", "inspect_folder"),
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


class Frame(AnalysisMixin, DebugMixin, ToolsMixin, StructureMixin, TabsMixin, PanelsMixin, Gtk.ApplicationWindow):
    _edge_key: Optional[tuple] = None
    _loose_root = None  # the tree entry 'Loose files' (a Gtk.TreeIter) while it exists
    def __init__(self, app: Gtk.Application, folder: str, files: Sequence[str] = (),
                 mode: str = "light", scheme: str = "blend", autosave: Optional[bool] = None) -> None:
        self.mode, self.scheme = mode, scheme
        install_frame_css(mode, scheme)
        super().__init__(application=app, title="oGMKDev")
        self.add_css_class("ogmkdev-frame")
        self.folder = os.path.abspath(folder)
        self.project_folders = [self.folder]  # the folders of the workspace (File > Add Folder)
        # Autosave saves a modified file AUTOSAVE_SECONDS after it was changed: the flag, or the setting
        self.autosave_enabled = autosave if autosave is not None else (
            SettingsStore(self.folder).value("ogmkdev_autosave") == "on")
        self._dirty_since: dict = {}
        self._poll_source = 0
        self.workspace = Workspace.from_properties(
            [self.folder], SettingsStore(self.folder).effective_for(os.path.join(self.folder, "_")))
        self.editors = Editors()
        self.area = EditorArea(self)
        self.set_default_size(1500, 900)
        self._install_actions()
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

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.add_css_class("ogmkdev-statusbar")
        self.status = Gtk.Label(xalign=0)
        self.status.set_hexpand(True)
        self.position = Gtk.Label(xalign=1)
        bar.append(self.status)
        bar.append(self.position)
        root.append(bar)

        self._populate_tree()
        self.build_left_tabs()
        self.build_bottom_tabs()
        if not files:
            self.add_editor(None)
        for path in files:
            self.open_file(path)
        # the Howl theme is selected once Howl runs (the first editor starts it)
        cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "ogmkdev", "themes")
        self.editors.theme(theme.theme_name(mode, scheme), theme.write_howl_theme(mode, scheme, cache))
        self.set_status(f"folder {self.folder}")
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
            menu.append_submenu(title, submenu)
        return Gtk.PopoverMenuBar.new_from_model(menu)

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

    def _sync_loose(self) -> None:
        """Open files the tree does not show (ignored, hidden or outside the folders) hang loose below the
        'Loose files' entry at the end of the tree; a file that is closed leaves it again."""
        loose = [path for path in self.editors.files()
                 if self.workspace.folder_of(path) is None or self.workspace.is_hidden(path)]
        shown = set(loose)
        present = set()
        if self._loose_root is not None:
            child = self.tree_store.iter_children(self._loose_root)
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
            if self._loose_root is None:
                self._loose_root = self.tree_store.append(None, [LOOSE_LABEL, "", "document-properties", None])
            self.tree_store.append(self._loose_root, [os.path.basename(path), path, "text-x-generic", None])
            self.tree.expand_row(self.tree_store.get_path(self._loose_root), False)
        if self._loose_root is not None and not self.tree_store.iter_n_children(self._loose_root):
            self.tree_store.remove(self._loose_root)
            self._loose_root = None

    def _reveal_loose(self, path: str) -> bool:
        """Selects an open file that hangs loose below 'Loose files'."""
        if self._loose_root is None:
            return False
        child = self.tree_store.iter_children(self._loose_root)
        while child is not None:
            if self.tree_store[child][1] == path:
                self.tree.expand_row(self.tree_store.get_path(self._loose_root), False)
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
        """Shows a file in its tab (opened in a new Howl editor if needed) and moves to a line."""
        if self.area.open(path) is None:
            self.set_status(f"could not open {path}")
            return
        if line:
            self.editors.open(path, line, column)
        self.set_status(f"opened {path}")

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
        self.editors.command("buffer-close")

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
        self._sync_loose()
        self._follow_structure(path)
        click = self.editors.take_click()
        if click:
            self._follow_click(*click)
        return True

    def _on_close_request(self, _window) -> bool:
        """The window is closing: its status poll stops (a closed frame must not act on the Howl editors)."""
        if self._poll_source:
            GLib.source_remove(self._poll_source)
            self._poll_source = 0
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
        """Ctrl+click: a file reference (href, src, url(...)) opens its file; anything else goes to the
        definition of the word."""
        value = markup.reference_at(line, column) if column and self._markup_enabled(self.area.current_path()) \
            else None
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
        """The edge line of the editors of a file: the column of its EditorConfig max_line_length."""
        key = (path, self.editors.count)
        if not path or key == self._edge_key:
            return
        self._edge_key = key
        self.editors.set_edge(path, self._settings_for(path).max_line_length or EDGE_COLUMN_DEFAULT)

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

    def _choose_folder(self, title: str, accept: str, on_chosen) -> None:
        native = Gtk.FileChooserNative.new(title, self, Gtk.FileChooserAction.SELECT_FOLDER, accept, "Cancel")
        self._folder_native = native  # kept until the dialog answers
        native.connect("response", lambda dialog, response: self._on_folder_chosen(dialog, response, on_chosen))
        native.show()

    def _on_folder_chosen(self, native, response, on_chosen) -> None:
        if response == Gtk.ResponseType.ACCEPT and native.get_file() is not None:
            on_chosen(native.get_file().get_path())
        self._folder_native = None

    def set_project(self, folder: str) -> None:
        """The folder becomes the project: its tree, its run configurations, its settings and its index."""
        self.folder = os.path.abspath(folder)
        self.project_folders = [self.folder]
        self._reload_project()
        self.set_status(f"project {self.folder}")

    def _add_workspace_folder(self, folder: str) -> None:
        folder = os.path.abspath(folder)
        if folder not in self.project_folders:
            self.project_folders.append(folder)
        self._reload_project()
        self.set_status(f"workspace: {len(self.project_folders)} folder(s)")

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
        about = Gtk.AboutDialog(transient_for=self, modal=True, program_name="oGMKDev", version="0.1.0")
        about.set_license_type(Gtk.License.GPL_2_0_ONLY)
        about.present()
