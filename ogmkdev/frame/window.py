"""The frame window (GTK 4): menu bar, toolbar, tabs, editor area with Howl editors, bottom panel,
find field and status line."""

from __future__ import annotations

import os
from typing import Optional, Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from ogmkdev.workspace import Workspace  # noqa: E402
from . import theme  # noqa: E402
from .editors import EditorArea  # noqa: E402
from .howl import Editors  # noqa: E402
from .menus import MENUS, PENDING  # noqa: E402
from .panels import PanelsMixin  # noqa: E402
from .tabs import TabsMixin  # noqa: E402
from .tools import ToolsMixin  # noqa: E402
from .analysis import AnalysisMixin  # noqa: E402

HIDDEN_NAMES = {".git", "node_modules", "__pycache__"}
ICON_THEME = "Humanity"

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
    "spacer",
    ("media-playback-start", "Run", "run_selected"),
    ("system-run", "Run configurations", "show_run_tab"),
    ("media-record", "Toggle breakpoint", "toggle_breakpoint"),
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


class Frame(AnalysisMixin, ToolsMixin, TabsMixin, PanelsMixin, Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, folder: str, files: Sequence[str] = (),
                 mode: str = "light", scheme: str = "blend") -> None:
        self.mode, self.scheme = mode, scheme
        install_frame_css(mode, scheme)
        super().__init__(application=app, title="oGMKDev")
        self.add_css_class("ogmkdev-frame")
        self.folder = os.path.abspath(folder)
        self.workspace = Workspace.from_properties([self.folder], {})
        self.editors = Editors()
        self.area = EditorArea(self)
        self.set_default_size(1500, 900)
        self._install_actions()

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
        GLib.timeout_add(500, self._poll)

    # ------------------------------------------------------ tabs setup

    def build_left_tabs(self) -> None:
        self._build_run()
        self._build_hierarchy()
        self._build_history()
        self._build_git()

    def build_bottom_tabs(self) -> None:
        self._build_watches()
        self._build_problems()
        self._build_search()
        self._build_todos()

    def show_run_tab(self) -> None:
        self.left.set_current_page(self.left.page_num(self.run_box))

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
        self.tree_store = Gtk.TreeStore(str, str)  # name, absolute path ("" for a placeholder)
        self.tree = Gtk.TreeView(model=self.tree_store)
        self.tree.set_headers_visible(False)
        self.tree.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0))
        self.tree.connect("row-expanded", self._on_row_expanded)
        self.tree.connect("row-activated", self._on_row_activated)
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.tree)
        scroller.set_vexpand(True)
        self.left = Gtk.Notebook()
        self.left.append_page(scroller, Gtk.Label(label="Files"))
        return self.left

    def _populate_tree(self) -> None:
        for folder in self.workspace.folders:
            node = self.tree_store.append(None, [os.path.basename(folder) or folder, folder])
            self._fill(node, folder)
            self.tree.expand_row(self.tree_store.get_path(node), False)

    def _fill(self, parent, folder: str) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        for entry in entries:
            if entry.name in HIDDEN_NAMES or self.workspace.is_excluded(entry.path):
                continue
            if entry.name.startswith(".") and entry.name not in (".editorconfig",):
                continue
            node = self.tree_store.append(parent, [entry.name, entry.path])
            if entry.is_dir(follow_symlinks=False):
                self.tree_store.append(node, ["", ""])  # filled when the folder is expanded

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
        self.track_history(path)
        return True

    # ---------------------------------------------------- menu actions

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
