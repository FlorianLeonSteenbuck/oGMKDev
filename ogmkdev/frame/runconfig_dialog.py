"""The Run Configurations dialog: the shell configurations of the project, created and edited with a command, arguments,
a working folder and environment variables. They are saved in the project's .run folder. Other configurations are listed
and shown, but they are edited in their own file. A configuration keeps its name when it is edited, because the name is
its file name.

Failures are return values (see ogmkdev.outcome); the dialog shows them and keeps what the form holds.
"""

from __future__ import annotations

import os
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import runconfig  # noqa: E402
from ..outcome import Failure  # noqa: E402

DIM_CSS = "dim-label"
ARGUMENTS_HINT = 'Passed to the command as $1, $2, ... Use "$@" in the command to pass them on, e.g. pytest "$@"'


class RunConfigurationDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, project_dir: str, on_saved: Callable[[str], None]) -> None:
        super().__init__(title="Run Configurations", transient_for=parent, modal=True)
        self.set_default_size(780, 480)
        self.project_dir = project_dir
        self.on_saved = on_saved
        self._configs: List[runconfig.RunConfiguration] = []
        self._current: Optional[runconfig.RunConfiguration] = None  # the configuration in the form; None for a new one

        self.list = Gtk.ListBox()
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.connect("row-selected", lambda _list, row: self._row_selected(row))
        new = Gtk.Button(label="New Shell Configuration")
        new.connect("clicked", lambda _button: self.new_configuration())
        list_scroller = Gtk.ScrolledWindow()
        list_scroller.set_vexpand(True)
        list_scroller.set_child(self.list)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.append(new)
        left.append(list_scroller)

        self.name = Gtk.Entry(hexpand=True)
        self.command = Gtk.Entry(hexpand=True)
        self.arguments = Gtk.Entry(hexpand=True)
        self.arguments.set_tooltip_text(ARGUMENTS_HINT)
        self.folder = Gtk.Entry(hexpand=True)
        self.environment = Gtk.TextView()
        self.environment.set_monospace(True)
        environment_scroller = Gtk.ScrolledWindow()
        environment_scroller.set_min_content_height(90)
        environment_scroller.set_child(self.environment)
        form = Gtk.Grid(column_spacing=8, row_spacing=6)
        fields = (("Name", self.name), ("Command", self.command), ("Arguments", self.arguments),
                  ("Working folder", self.folder), ("Environment", environment_scroller))
        for row, (label, widget) in enumerate(fields):
            form.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            form.attach(widget, 1, row, 1, 1)
        environment_hint = Gtk.Label(label="Environment: KEY=VALUE, one variable per line", xalign=0)
        environment_hint.add_css_class(DIM_CSS)

        self.message = Gtk.Label(xalign=0, wrap=True)
        self.message.add_css_class(DIM_CSS)
        self._save_button = Gtk.Button(label="Save")
        self._save_button.add_css_class("suggested-action")
        self._save_button.connect("clicked", lambda _button: self.save())
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda _button: self.destroy())
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.END)
        buttons.append(close)
        buttons.append(self._save_button)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_hexpand(True)
        right.append(form)
        right.append(environment_hint)
        right.append(self.message)
        right.append(buttons)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(left)
        paned.set_end_child(right)
        paned.set_position(260)
        paned.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.append(paned)
        self.set_child(box)
        self.reload()

    # ------------------------------------------------------------ the list

    def reload(self, select: str = "") -> None:
        """Reads the configurations of the project and lists them. The one named ``select`` is shown; without it, or when
        no configuration has that name, the form is empty for a new configuration."""
        self._configs = runconfig.discover(self.project_dir)
        while (row := self.list.get_row_at_index(0)) is not None:
            self.list.remove(row)
        for config in self._configs:
            label = Gtk.Label(label=config.name, xalign=0)
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            row = Gtk.ListBoxRow()
            row.set_child(label)
            self.list.append(row)
        chosen = next((number for number, config in enumerate(self._configs) if config.name == select), None)
        if chosen is None:
            self.new_configuration()
        else:
            self.list.select_row(self.list.get_row_at_index(chosen))

    def _row_selected(self, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is not None:  # a cleared selection keeps the form as it is
            self._show(self._configs[row.get_index()])

    # ------------------------------------------------------------ the form

    def _show(self, config: runconfig.RunConfiguration) -> None:
        """Puts a configuration into the form. Only a shell configuration that runs its own script text can be edited here."""
        self._current = config
        self.name.set_text(config.name)
        self.name.set_editable(False)
        self.command.set_text(config.option("SCRIPT_TEXT", "") or "")
        self.arguments.set_text(config.option("PARAMETERS", "") or "")
        self.folder.set_text(config.option("WORKING_DIRECTORY", "") or runconfig.DEFAULT_WORKING_DIRECTORY)
        self.environment.get_buffer().set_text(runconfig.environment_text(config.envs))
        if config.type == runconfig.SHELL_TYPE and not config.option("SCRIPT_PATH"):
            self._set_editable(True)
            self.message.set_text("")
            return
        self._set_editable(False)
        what = "a script file" if config.option("SCRIPT_PATH") else f"the type {config.type}"
        self.message.set_text(f"{config.name} runs {what}: it is edited in its file in the .run folder.")

    def new_configuration(self) -> None:
        """An empty form for a new shell configuration."""
        self._current = None
        self.list.unselect_all()
        self.name.set_text("")
        self.name.set_editable(True)
        self.command.set_text("")
        self.arguments.set_text("")
        self.folder.set_text(runconfig.DEFAULT_WORKING_DIRECTORY)
        self.environment.get_buffer().set_text("")
        self._set_editable(True)
        self.message.set_text("A new configuration is saved as .run/<name>.run.xml in the project folder.")

    def _set_editable(self, editable: bool) -> None:
        for entry in (self.command, self.arguments, self.folder):
            entry.set_editable(editable)
        self.environment.set_editable(editable)
        self._save_button.set_sensitive(editable)

    def _environment_text(self) -> str:
        buffer = self.environment.get_buffer()
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, False)

    # ------------------------------------------------------------ saving

    def save(self) -> None:
        """Writes the form to .run/<name>.run.xml. A new name must not name a file that exists: it is not overwritten."""
        name = self._current.name if self._current is not None else runconfig.valid_name(self.name.get_text())
        if isinstance(name, Failure):
            self.message.set_text(str(name))
            return
        path = runconfig.configuration_path(self.project_dir, name)
        if self._current is None and os.path.exists(path):
            self.message.set_text(f"{name} exists: choose another name, or select it in the list to edit it")
            return
        command = self.command.get_text().strip()
        if not command:
            self.message.set_text("The command is empty.")
            return
        envs = runconfig.environment_from_text(self._environment_text())
        if isinstance(envs, Failure):
            self.message.set_text(str(envs))
            return
        config = runconfig.shell_configuration(name, command, self.arguments.get_text(), self.folder.get_text(), envs,
                                               base=self._current)
        try:
            runconfig.save(config, path)
        except OSError as problem:
            self.message.set_text(f"not saved: {problem}")
            return
        self.on_saved(name)
        self.reload(select=name)
        note = ""
        if self.arguments.get_text().strip() and not runconfig.reads_arguments(command):
            note = " The command does not read the arguments ($@, $1, ...), so they are not passed on."
        self.message.set_text(f"Saved {path}.{note}")
