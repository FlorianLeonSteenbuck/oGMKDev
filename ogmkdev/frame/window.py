"""The frame window (GTK 4): menu bar, tabs, workspace tree, Howl editors and the bottom panel."""

from __future__ import annotations

import os
from typing import Sequence

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from ogmkdev.workspace import Workspace  # noqa: E402
from .howl import Editors  # noqa: E402
from .menus import MENUS, PENDING  # noqa: E402
from .panels import PanelsMixin  # noqa: E402
from .tabs import TabsMixin  # noqa: E402

HIDDEN_NAMES = {".git", "node_modules", "__pycache__"}

# Howl's editor and the frame share the display; the frame sets its own colours with a higher priority.
FRAME_CSS = """
.ogmkdev-frame, .ogmkdev-frame menubar, .ogmkdev-frame menu, .ogmkdev-frame popover {
  background-color: #f6f5f4;
  color: #2e3436;
}
.ogmkdev-frame label, .ogmkdev-frame treeview, .ogmkdev-frame menuitem label,
.ogmkdev-frame menubar > menuitem, .ogmkdev-frame textview text {
  color: #2e3436;
  background-color: transparent;
}
.ogmkdev-frame textview text { background-color: #ffffff; }
.ogmkdev-frame treeview { background-color: #ffffff; }
.ogmkdev-frame .ogmkdev-statusbar { background-color: #e8e6e3; padding: 3px 8px; }
"""
_css_installed = False


def install_frame_css() -> None:
    global _css_installed
    if _css_installed:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(FRAME_CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_USER)
    _css_installed = True


class Frame(TabsMixin, PanelsMixin, Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, project_dir: str, files: Sequence[str] = ()) -> None:
        install_frame_css()
        super().__init__(application=app, title="oGMKDev")
        self.add_css_class("ogmkdev-frame")
        self.project_dir = os.path.abspath(project_dir)
        self.workspace = Workspace.from_properties([self.project_dir], {})
        self.editors = Editors()
        self.set_default_size(1400, 860)
        self._install_actions()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        root.append(self._menubar(app))

        main = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main.set_start_child(self._left())
        main.set_resize_start_child(False)
        main.set_shrink_start_child(False)
        main.set_position(380)
        main.set_vexpand(True)

        right = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        right.set_start_child(self._editor_area())
        right.set_resize_start_child(True)
        right.set_end_child(self._bottom())
        right.set_resize_end_child(False)
        right.set_position(600)
        main.set_end_child(right)
        root.append(main)

        self.status = Gtk.Label(xalign=0)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.add_css_class("ogmkdev-statusbar")
        bar.append(self.status)
        root.append(bar)

        self._populate_tree()
        self.build_left_tabs()
        self._build_git()
        self.build_bottom_tabs()
        self._build_todos()
        if not files:
            self.add_editor(None)
        for path in files:
            self.open_file(path)
        self.set_status(f"project {self.project_dir}")

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

    def _install_actions(self) -> None:
        for _title, entries in MENUS:
            for _label, name, _accelerator, target in entries:
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, t=target: self._run_target(t))
                self.add_action(action)

    def _run_target(self, target: str) -> None:
        if target.startswith("howl:"):
            if not self.editors.command(target[len("howl:"):]):
                self.set_status(f"{target[len('howl:'):]}: no Howl editor has the focus")
            return
        getattr(self, target)()

    def __getattr__(self, name: str):
        # menu entries whose feature is not wired yet report that instead of failing
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

    def _editor_area(self) -> Gtk.Widget:
        self.editor_area = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.editor_area.set_homogeneous(True)
        self.editor_area.set_vexpand(True)
        return self.editor_area

    def add_editor(self, path=None) -> bool:
        """A new Howl editor in its own column of the editor area, with ``path`` if given."""
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        column.set_hexpand(True)
        column.set_vexpand(True)
        self.editor_area.append(column)
        if not self.editors.add(column, path):
            self.set_status("the Howl editor could not be started")
            return False
        self.set_status(f"{self.editors.count} editor(s)" + (f" · {path}" if path else ""))
        return True

    def open_file(self, path: str, line: int = 0, column: int = 0) -> None:
        """Opens a file in the Howl editor that has the focus; the first file starts an editor."""
        if self.editors.count == 0:
            self.add_editor(path)
            return
        if self.editors.open(path, line, column):
            self.set_status(f"opened {path}")
        else:
            self.set_status(f"could not open {path}")

    def new_editor(self) -> None:
        self.add_editor(None)

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

    # ---------------------------------------------------- menu actions

    def open_dialog(self) -> None:
        self._native = Gtk.FileChooserNative.new("Open", self, Gtk.FileChooserAction.OPEN, "Open", "Cancel")
        self._native.set_current_folder(Gio.File.new_for_path(self.project_dir))
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

    def close_tab(self) -> None:
        self.editors.command("buffer-close")
