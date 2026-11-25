"""The panels of the frame that use the backend modules: Git, TODOs, Quick Open and Search Everywhere."""

from __future__ import annotations

import os
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import git as git_module  # noqa: E402
from .. import search_everywhere as search  # noqa: E402
from .. import settings as settings_module  # noqa: E402
from .. import todos  # noqa: E402
from ..history import file_patch  # noqa: E402
from ..settings import SettingsStore  # noqa: E402
from ..workspace import workspace_files  # noqa: E402
from .menus import MENUS  # noqa: E402


def _scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
    scroller = Gtk.ScrolledWindow()
    scroller.set_child(child)
    scroller.set_vexpand(True)
    return scroller


def _text_view() -> Gtk.TextView:
    view = Gtk.TextView(editable=False, monospace=True)
    view.set_cursor_visible(False)
    return view


class PanelsMixin:
    """Methods of the frame window; the window provides ``left``, ``bottom``, ``workspace``, ``open_file``."""

    # ------------------------------------------------------------- Git

    def show_git(self) -> None:
        if not hasattr(self, "git_store"):
            self._build_git()
        self.left.set_current_page(self.left.page_num(self.git_box))
        self.refresh_git()

    def _build_git(self) -> None:
        self.git_store = Gtk.ListStore(str, str, str, object)  # staged, change, path, Change
        self.git_view = Gtk.TreeView(model=self.git_store)
        selection = self.git_view.get_selection()
        selection.set_mode(Gtk.SelectionMode.MULTIPLE)
        selection.connect("changed", lambda *_: self._show_git_diff())
        for index, heading in enumerate(("Staged", "Change", "Path")):
            self.git_view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
        self.git_diff = _text_view()
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_start_child(_scrolled(self.git_view))
        paned.set_end_child(_scrolled(self.git_diff))
        paned.set_position(220)
        paned.set_vexpand(True)
        grid = Gtk.Grid(column_homogeneous=True, column_spacing=4, row_spacing=4)
        buttons = (("Stage", self.git_stage), ("Unstage", self.git_unstage), ("Diff", self._show_git_diff),
                   ("Commit...", self.git_commit), ("Refresh", self.refresh_git))
        for index, (label, handler) in enumerate(buttons):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, h=handler: h())
            grid.attach(button, index % 3, index // 3, 1, 1)
        self.git_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.git_box.append(grid)
        self.git_box.append(paned)
        self.left.append_page(self.git_box, Gtk.Label(label="Git"))
        self.git_all: list = []

    def refresh_git(self) -> None:
        if not hasattr(self, "git_store"):
            return
        selected = {change.path for change in self._git_selected()}
        changes = []
        for folder in self.workspace.folders:
            try:
                changes.extend(git_module.status(folder))
            except (git_module.GitError, OSError):
                continue
        self.git_all = sorted({change.path: change for change in changes}.values(), key=lambda c: c.path)
        self.git_store.clear()
        for change in self.git_all:
            staged = "" if change.untracked else change.index.strip()
            iterator = self.git_store.append([staged, change.label,
                                              os.path.relpath(change.path, change.root), change])
            if change.path in selected:
                self.git_view.get_selection().select_iter(iterator)
        self.set_status(f"{len(self.git_all)} changed file(s) in git")

    def _git_selected(self) -> list:
        if not hasattr(self, "git_view"):
            return []
        model, paths = self.git_view.get_selection().get_selected_rows()
        return [model[path][3] for path in paths]

    def _git_run(self, description: str, action: Callable[[], None]) -> None:
        try:
            action()
        except git_module.GitError as error:
            self.set_status(f"git: {error}")
        else:
            self.set_status(description)
        self.refresh_git()

    def git_stage(self) -> None:
        changes = self._git_selected()
        if not changes:
            self.set_status("select files in the Git panel first")
            return
        self._git_run(f"staged {len(changes)} file(s)",
                      lambda: [git_module.stage(c.root, [c.path]) for c in changes])

    def git_unstage(self) -> None:
        changes = self._git_selected()
        if not changes:
            self.set_status("select files in the Git panel first")
            return
        self._git_run(f"unstaged {len(changes)} file(s)",
                      lambda: [git_module.unstage(c.root, [c.path]) for c in changes])

    def _show_git_diff(self) -> None:
        if not hasattr(self, "git_diff"):
            return
        parts = []
        for change in self._git_selected():
            relative = os.path.relpath(change.path, change.root)
            try:
                if change.untracked:
                    with open(change.path, encoding="utf-8", errors="replace") as handle:
                        parts.append(file_patch("", handle.read(), relative))
                    continue
                if change.staged:
                    parts.append(git_module.diff(change.root, change.path, staged=True))
                if change.worktree.strip():
                    parts.append(git_module.diff(change.root, change.path, staged=False))
            except (git_module.GitError, OSError) as error:
                parts.append(f"{relative}: {error}\n")
        self.git_diff.get_buffer().set_text("".join(parts))

    def git_commit(self) -> None:
        staged = [change for change in self.git_all if change.staged]
        if not staged:
            self.set_status("nothing is staged")
            return
        self.ask_text("Commit", f"Commit message for {len(staged)} staged file(s):",
                      lambda message: self._git_run(
                          f"committed {len(staged)} file(s)",
                          lambda: [git_module.commit(root, message) for root in sorted({c.root for c in staged})]))

    def ask_text(self, title: str, label: str, on_ok: Callable[[str], None]) -> None:
        window = Gtk.Window(title=title, transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        entry = Gtk.Entry()
        button = Gtk.Button(label="OK")
        box.append(Gtk.Label(label=label, xalign=0))
        box.append(entry)
        box.append(button)
        for margin in ("set_margin_start", "set_margin_end", "set_margin_top", "set_margin_bottom"):
            getattr(box, margin)(10)

        def finish(*_args) -> None:
            text = entry.get_text().strip()
            window.destroy()
            if text:
                on_ok(text)

        button.connect("clicked", finish)
        entry.connect("activate", finish)
        window.set_child(box)
        window.present()
        entry.grab_focus()

    # ----------------------------------------------------------- TODOs

    def show_todos(self) -> None:
        if not hasattr(self, "todo_store"):
            self._build_todos()
        self.refresh_todos()
        self.bottom.set_current_page(self.bottom.page_num(self.todo_box))

    def _build_todos(self) -> None:
        self.todo_store = Gtk.ListStore(str, str, str, str, object)  # priority, keyword, where, text, Todo
        self.todo_view = Gtk.TreeView(model=self.todo_store)
        for index, heading in enumerate(("Priority", "Keyword", "Where", "Text")):
            self.todo_view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
        self.todo_view.connect("row-activated", self._on_todo_activated)
        self.todo_box = _scrolled(self.todo_view)
        self.bottom.append_page(self.todo_box, Gtk.Label(label="TODO"))

    def _keywords(self) -> list:
        store = SettingsStore(self.folder)
        return todos.parse_keywords(store.value("ogmkdev_todo_keywords") or settings_module.SETTINGS_BY_KEY[
            "ogmkdev_todo_keywords"].default)

    def refresh_todos(self) -> None:
        keywords = self._keywords()
        found = todos.todos_in_files(workspace_files(self.workspace), keywords)
        self.todo_store.clear()
        for todo in found:
            where = f"{os.path.relpath(todo.path, self.folder)}:{todo.line}"
            self.todo_store.append([f"P{todo.priority}", todo.keyword, where, todo.text, todo])
        self.set_status(f"{len(found)} TODO(s) in comments")

    def _on_todo_activated(self, _view, path, _column) -> None:
        todo = self.todo_store[self.todo_store.get_iter(path)][4]
        self.open_file(todo.path, todo.line, 1)

    # ------------------------------------------- Quick Open, Search Everywhere

    def quick_open(self) -> None:
        self._search_window("Quick Open", ("file",))

    def search_everywhere(self) -> None:
        self._search_window("Search Everywhere", None)

    def _search_candidates(self) -> list:
        candidates = []
        for path in workspace_files(self.workspace):
            candidates.append(search.Candidate("file", os.path.relpath(path, self.folder),
                                               self.workspace.kind(path), ("file", path)))
        for _title, entries in MENUS:
            for label, _name, accelerator, method in entries:
                candidates.append(search.Candidate("action", label, accelerator, ("action", method)))
        for setting in settings_module.SCHEMA:
            candidates.append(search.Candidate("setting", setting.label, f"{setting.group}: {setting.key}",
                                               ("setting", setting.group)))
        return candidates

    def _search_window(self, title: str, categories) -> None:
        candidates = self._search_candidates()
        window = Gtk.Window(title=title, transient_for=self, modal=True)
        window.set_default_size(680, 460)
        entry = Gtk.Entry(placeholder_text="type to filter, Enter opens, Up and Down move")
        store = Gtk.ListStore(str, str, str, object)  # kind, name, where, Candidate
        view = Gtk.TreeView(model=store)
        for index, heading in enumerate(("Kind", "Name", "Where")):
            view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))

        def update(*_args) -> None:
            store.clear()
            for candidate in search.rank(candidates, entry.get_text(), categories):
                store.append([candidate.category, candidate.label, candidate.detail, candidate])
            if len(store):
                view.get_selection().select_path(Gtk.TreePath.new_first())

        def chosen() -> Optional[search.Candidate]:
            model, iterator = view.get_selection().get_selected()
            return model[iterator][3] if iterator is not None else None

        def activate(*_args) -> None:
            candidate = chosen()
            if candidate is None:
                return
            window.destroy()
            self.activate_candidate(candidate)

        def move(step: int) -> None:
            if not len(store):
                return
            _model, iterator = view.get_selection().get_selected()
            current = store.get_path(iterator).get_indices()[0] if iterator is not None else -1
            path = Gtk.TreePath.new_from_indices([min(max(current + step, 0), len(store) - 1)])
            view.get_selection().select_path(path)
            view.scroll_to_cell(path, None, False, 0.0, 0.0)

        keys = Gtk.EventControllerKey()

        def on_key(_controller, keyval, _keycode, _state) -> bool:
            from gi.repository import Gdk
            if keyval == Gdk.KEY_Down:
                move(1)
                return True
            if keyval == Gdk.KEY_Up:
                move(-1)
                return True
            return False

        keys.connect("key-pressed", on_key)
        entry.add_controller(keys)
        entry.connect("changed", update)
        entry.connect("activate", activate)
        view.connect("row-activated", activate)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(entry)
        box.append(_scrolled(view))
        for margin in ("set_margin_start", "set_margin_end", "set_margin_top", "set_margin_bottom"):
            getattr(box, margin)(10)
        window.set_child(box)
        update()
        window.present()
        entry.grab_focus()

    def activate_candidate(self, candidate: search.Candidate) -> None:
        kind = candidate.target[0]
        if kind == "file":
            self.open_file(candidate.target[1])
        elif kind == "action":
            getattr(self, candidate.target[1])()
        elif kind == "setting":
            self.set_status(f"settings group {candidate.target[1]} (the settings dialog is not in the frame yet)")
