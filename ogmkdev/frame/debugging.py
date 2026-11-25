"""Debugging in the frame. A run configuration of type GDB or XDebug starts a session of ogmkdev.debug (GDB/MI
or DBGp). The breakpoints the Howl editors show go to the engine before the program runs, and the breakpoints
are synced again before every resume, so a breakpoint set during a stop applies at the next continue or step.

The engine emits its events on its own thread: they are taken over on the GTK thread with GLib.idle_add. The
Howl editors are only read on the GTK thread, as Howl's Lua state belongs to it.
"""

from __future__ import annotations

import shlex
import subprocess
import threading
from typing import List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from .. import runconfig  # noqa: E402
from ..debug import DebuggerError, Exited, GdbMiDebugger, Output, Stopped, XdebugDebugger  # noqa: E402
from ..debug.sync import BreakpointSync  # noqa: E402

Location = Tuple[str, int]


class DebugMixin:
    """Window methods; uses ``folder``, ``editors``, ``set_status``, ``log``, ``show_debug_stop`` and
    ``_pipe_output``. The session attributes are None until a session starts."""

    _debugger = None
    _breakpoint_sync: Optional[BreakpointSync] = None
    _debug_process: Optional[subprocess.Popen] = None

    # ----------------------------------------------------------- actions

    def debug_selected(self) -> None:
        """Debug > Debug Configuration: starts a session for the selected run configuration."""
        config = self._selected_run_config()
        if config is None:
            self.set_status("select a run configuration first")
            return
        self.start_debugging(config)

    def start_debugging(self, config: runconfig.RunConfiguration) -> None:
        if self._debugger is not None:
            self.set_status("a debug session is already running")
            return
        try:
            if config.type == runconfig.GDB_TYPE:
                debugger, launch = self._gdb_engine(config)
            elif config.type == runconfig.XDEBUG_TYPE:
                debugger, launch = self._xdebug_engine(config)
            else:
                self.set_status(f"{config.name}: type {config.type} cannot be debugged")
                return
        except (runconfig.RunConfigError, ValueError, OSError) as error:
            self.set_status(f"{config.name}: {error}")
            return
        sync = BreakpointSync(debugger)
        self._debugger = debugger
        self._breakpoint_sync = sync
        debugger.on_event(lambda event: GLib.idle_add(self._on_debug_event, debugger, event))
        self.set_status(f"debugging {config.name} ...")
        wanted = self.editors.breakpoints()
        threading.Thread(target=self._debug_main, args=(debugger, sync, launch, wanted), daemon=True).start()

    def debug_continue(self) -> None:
        self._debug_operation("run", "continue")

    def step_over(self) -> None:
        self._debug_operation("step_over", "step over")

    def step_into(self) -> None:
        self._debug_operation("step_into", "step into")

    def step_out(self) -> None:
        self._debug_operation("step_out", "step out")

    def stop_debugging(self) -> None:
        if self._debugger is None:
            self.set_status("no debug session is running")
            return
        self._end_debugging(self._debugger)
        self.set_status("debug session stopped")

    # ----------------------------------------------------------- engines

    def _gdb_engine(self, config: runconfig.RunConfiguration):
        program = runconfig._expand(config.option("PROGRAM", "") or "", self.folder)
        if not program:
            raise runconfig.RunConfigError(f"{config.name}: PROGRAM is empty")
        args = shlex.split(config.option("ARGUMENTS", "") or "")
        cwd = runconfig._expand(config.option("WORKING_DIRECTORY", "$PROJECT_DIR$") or self.folder, self.folder)
        return GdbMiDebugger(program, args, cwd), None

    def _xdebug_engine(self, config: runconfig.RunConfiguration):
        """XDebug connects back to the listener: the script runs with the debugger's port in its settings."""
        script = runconfig._expand(config.option("SCRIPT_NAME", "") or "", self.folder)
        if not script:
            raise runconfig.RunConfigError(f"{config.name}: SCRIPT_NAME is empty")
        debugger = XdebugDebugger(port=int(config.option("PORT", "0") or "0"))
        port = debugger.listen()
        launch: List[str] = ["php", "-d", "xdebug.mode=debug", "-d", "xdebug.start_with_request=yes",
                             "-d", "xdebug.client_host=127.0.0.1", "-d", f"xdebug.client_port={port}", script]
        return debugger, launch

    # ------------------------------------------------------------ worker

    def _debug_main(self, debugger, sync: BreakpointSync, launch: Optional[List[str]], wanted: List[Location]) -> None:
        """Worker thread: starts the engine, sends the breakpoints and lets the program run."""
        try:
            if launch:
                process = subprocess.Popen(launch, cwd=self.folder, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, errors="replace")
                self._debug_process = process
                threading.Thread(target=self._pipe_output, args=(process,), daemon=True).start()
            debugger.start()
            for problem in sync.sync(wanted):
                GLib.idle_add(self.log, f"breakpoint not set: {problem}")
            debugger.run()
        except (DebuggerError, OSError) as error:
            GLib.idle_add(self._debug_failed, debugger, str(error))

    def _debug_operation(self, operation: str, name: str) -> None:
        """Syncs the breakpoints with the editors, then runs the engine's operation, on a worker thread."""
        debugger = self._debugger
        if debugger is None:
            self.set_status("no debug session: run a GDB or XDebug configuration in debug mode first")
            return
        sync = self._breakpoint_sync
        wanted = self.editors.breakpoints()

        def worker() -> None:
            try:
                for problem in sync.sync(wanted):
                    GLib.idle_add(self.log, f"breakpoint not set: {problem}")
                getattr(debugger, operation)()
            except (DebuggerError, OSError) as error:
                GLib.idle_add(self.set_status, f"{name}: {error}")

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------ events

    def _on_debug_event(self, debugger, event) -> bool:
        if debugger is not self._debugger:
            return False
        if isinstance(event, Output):
            self.log(event.text.rstrip("\n"))
        elif isinstance(event, Stopped):
            location = event.location
            if location and location.file and location.line:
                self.show_debug_stop(location.file, location.line)
            else:
                self.set_status(f"stopped ({event.reason})")
        elif isinstance(event, Exited):
            code = "" if event.code is None else f", exit code {event.code}"
            self.set_status(f"program exited{code}")
            self._end_debugging(debugger)
        return False

    def _debug_failed(self, debugger, message: str) -> bool:
        self.set_status(f"debug session failed: {message}")
        if self._debugger is debugger:
            self._end_debugging(debugger)
        return False

    def _end_debugging(self, debugger) -> None:
        if self._debugger is debugger:
            self._debugger = None
            self._breakpoint_sync = None
        # the script the engine was started for ends with the session (it would run on otherwise)
        process, self._debug_process = self._debug_process, None
        if process is not None and process.poll() is None:
            process.terminate()
        threading.Thread(target=debugger.stop, daemon=True).start()
