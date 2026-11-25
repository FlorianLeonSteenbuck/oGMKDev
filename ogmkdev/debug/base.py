"""Debugger interface shared by all backends (GDB/MI, XDebug/DBGp).

The shape follows KDevelop's ``IDebugSession`` (kdevplatform/debugger/interfaces/
idebugsession.h): a session owns breakpoints and watches, is driven by run/step commands,
and reports state through events. Backends implement the ``_`` hooks; the public methods
keep the bookkeeping (ids, watch list, listeners) in one place.

Threading: backends may emit events from their own I/O thread. Listeners must be cheap or
marshal to the UI thread themselves (GTK: ``GLib.idle_add``). Events are also queued, so
synchronous callers can use :meth:`Debugger.wait_event`.
"""

from __future__ import annotations

import abc
import itertools
import queue
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union


class DebuggerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Breakpoint:
    id: int
    file: str
    line: int
    condition: Optional[str] = None
    enabled: bool = True


@dataclass(frozen=True)
class Watch:
    id: int
    expression: str


@dataclass(frozen=True)
class Location:
    file: Optional[str]
    line: Optional[int]
    function: Optional[str] = None


@dataclass(frozen=True)
class Stopped:
    reason: str                      # "breakpoint" | "step" | "pause" | "signal" | "unknown"
    location: Optional[Location] = None
    breakpoint_id: Optional[int] = None


@dataclass(frozen=True)
class Exited:
    code: Optional[int] = None


@dataclass(frozen=True)
class Output:
    text: str
    stream: str = "console"          # "console" | "target" | "error"


Event = Union[Stopped, Exited, Output]
Listener = Callable[[Event], None]


class Debugger(abc.ABC):
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._lock = threading.RLock()
        self._breakpoints: Dict[int, Breakpoint] = {}
        self._watches: Dict[int, Watch] = {}
        self._listeners: List[Listener] = []
        self._queue: "queue.Queue[Event]" = queue.Queue()

    # ------------------------------------------------------------- events

    def on_event(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def emit(self, event: Event) -> None:
        self._queue.put(event)
        for listener in list(self._listeners):
            listener(event)

    def wait_event(self, predicate: Callable[[Event], bool], timeout: float) -> Event:
        """Block until an event matching ``predicate`` arrives (events are consumed)."""
        import time
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DebuggerError("timed out waiting for debugger event")
            try:
                event = self._queue.get(timeout=remaining)
            except queue.Empty:
                continue
            if predicate(event):
                return event

    # -------------------------------------------------------- breakpoints

    @property
    def breakpoints(self) -> Tuple[Breakpoint, ...]:
        with self._lock:
            return tuple(self._breakpoints.values())

    def add_breakpoint(self, file: str, line: int, condition: Optional[str] = None) -> Breakpoint:
        if line < 1:
            raise DebuggerError("line numbers start at 1")
        with self._lock:
            bp = Breakpoint(next(self._ids), file, line, condition)
            self._add_breakpoint(bp)
            self._breakpoints[bp.id] = bp
            return bp

    def remove_breakpoint(self, breakpoint_id: int) -> None:
        with self._lock:
            bp = self._breakpoints.pop(breakpoint_id, None)
            if bp is not None:
                self._remove_breakpoint(bp)

    # ------------------------------------------------------------ watches

    @property
    def watches(self) -> Tuple[Watch, ...]:
        with self._lock:
            return tuple(self._watches.values())

    def add_watch(self, expression: str) -> Watch:
        if not expression.strip():
            raise DebuggerError("empty watch expression")
        with self._lock:
            watch = Watch(next(self._ids), expression.strip())
            self._watches[watch.id] = watch
            return watch

    def remove_watch(self, watch_id: int) -> None:
        with self._lock:
            self._watches.pop(watch_id, None)

    def watch_values(self) -> Dict[str, str]:
        """Evaluate every watch in the current frame; errors become ``<error: ...>``."""
        values: Dict[str, str] = {}
        for watch in self.watches:
            try:
                values[watch.expression] = self.evaluate(watch.expression)
            except DebuggerError as error:
                values[watch.expression] = f"<error: {error}>"
        return values

    # ------------------------------------------------------ backend hooks

    @abc.abstractmethod
    def start(self) -> None:
        """Launch or attach and become ready for commands (execution not yet resumed)."""

    @abc.abstractmethod
    def run(self) -> None:
        """Start or continue execution until the next stop or exit."""

    @abc.abstractmethod
    def step_over(self) -> None: ...

    @abc.abstractmethod
    def step_into(self) -> None: ...

    @abc.abstractmethod
    def step_out(self) -> None: ...

    @abc.abstractmethod
    def stop(self) -> None:
        """Kill or detach from the debuggee and release the backend."""

    @abc.abstractmethod
    def evaluate(self, expression: str) -> str:
        """Value of ``expression`` in the current frame, as display text."""

    def variables(self) -> List[Tuple[str, str]]:
        """The local variables of the current frame, as (name, value text) pairs. Engines that cannot list
        them say so with a DebuggerError."""
        raise DebuggerError("this engine does not list the variables of a frame")

    @abc.abstractmethod
    def _add_breakpoint(self, bp: Breakpoint) -> None: ...

    @abc.abstractmethod
    def _remove_breakpoint(self, bp: Breakpoint) -> None: ...
