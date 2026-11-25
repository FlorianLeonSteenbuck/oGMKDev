"""The tabs of the frame: Run (run configurations, output to the console), and the panels that
are waiting for their backend (Hierarchy, History, Watches, Problems, Search)."""

from __future__ import annotations

import subprocess
import threading
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import runconfig  # noqa: E402
from .panels import _scrolled  # noqa: E402


def _table(headings) -> tuple:
    """A list store (one extra object column for the row's data) and a tree view for it."""
    store = Gtk.ListStore(*([str] * len(headings)), object)
    view = Gtk.TreeView(model=store)
    for index, heading in enumerate(headings):
        view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
    return store, view


class TabsMixin:
    """Window methods for the tabs; uses ``left``, ``bottom``, ``folder``, ``log``, ``set_status``."""

    # ------------------------------------------------------------- tabs

    # -------------------------------------------------------------- Run

    def _build_run(self) -> None:
        self.run_store = Gtk.ListStore(str, str, str, object)  # name, type, factory, RunConfiguration
        self.run_view = Gtk.TreeView(model=self.run_store)
        for index, heading in enumerate(("Name", "Type", "Factory")):
            self.run_view.append_column(Gtk.TreeViewColumn(heading, Gtk.CellRendererText(), text=index))
        self.run_view.connect("row-activated", lambda *_: self.run_selected())
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, handler in (("Run", self.run_selected), ("Stop", self.stop_process),
                               ("Refresh", self.refresh_run)):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, h=handler: h())
            buttons.append(button)
        self.run_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.run_box.append(buttons)
        self.run_box.append(_scrolled(self.run_view))
        self.left.append_page(self.run_box, Gtk.Label(label="Run"))
        self._process: Optional[subprocess.Popen] = None
        self.refresh_run()

    def refresh_run(self) -> None:
        self.run_store.clear()
        try:
            configs = runconfig.discover(self.folder)
        except OSError as error:
            self.set_status(f"run configurations: {error}")
            return
        for config in configs:
            self.run_store.append([config.name, config.type, config.factory, config])
        self.set_status(f"{len(configs)} run configuration(s)")

    def _selected_run_config(self) -> Optional[runconfig.RunConfiguration]:
        model, iterator = self.run_view.get_selection().get_selected()
        return model[iterator][3] if iterator is not None else None

    def run_selected(self) -> None:
        config = self._selected_run_config()
        if config is None:
            self.set_status("select a run configuration first")
            return
        if config.type in (runconfig.GDB_TYPE, runconfig.XDEBUG_TYPE):
            self.set_status("debug configurations are not wired in the frame yet")
            return
        if self._process is not None and self._process.poll() is None:
            self.set_status("a process is still running (Run > Stop Process)")
            return
        try:
            spec = config.to_process(self.folder)
        except runconfig.RunConfigError as error:
            self.set_status(str(error))
            return
        self.log("$ " + " ".join(spec.argv))
        try:
            self._process = subprocess.Popen(spec.argv, cwd=spec.cwd, env=spec.env, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, errors="replace")
        except OSError as error:
            self.set_status(f"cannot start {spec.argv[0]}: {error}")
            return
        self.set_status(f"running {config.name}")
        threading.Thread(target=self._pipe_output, args=(self._process,), daemon=True).start()

    def _pipe_output(self, process: subprocess.Popen) -> None:
        for line in process.stdout:
            GLib.idle_add(self.log, line.rstrip("\n"))
        code = process.wait()
        GLib.idle_add(self.log, f"process exited with code {code}")
        GLib.idle_add(self.set_status, f"process exited with code {code}")

    def stop_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            self.set_status("process terminated")
        else:
            self.set_status("no process is running")
