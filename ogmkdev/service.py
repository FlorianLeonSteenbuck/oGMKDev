"""Background services: work that runs in a thread of its own, one job at a time.

A service is a subclass of ``Service`` that implements ``run``. ``request`` starts a job with plain arguments; the job's
result goes to ``publish``, called from the job's thread, unless the job was cancelled. A request made while a job runs
waits for it, and only the latest such request is kept. ``cancel`` ends the running job and drops the waiting request;
``shutdown`` does that for good, for when the window closes: no job starts afterwards.

Only plain values cross this boundary, no GTK types, so another layer (such as the controls of the native build) can make
the same calls and take the results as events.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional, Tuple

from .progress import Progress

Deliver = Callable[[Any, Optional[str]], None]


class Cancelled(Exception):
    """A job was cancelled while it ran: it is not complete, and its result is not delivered."""


class Service:
    """The base of a background service. A subclass sets ``label`` (shown while a job runs) and implements ``run``."""

    label = "Task"

    def __init__(self, deliver: Deliver, progress: Optional[Progress] = None) -> None:
        self._deliver = deliver
        self.progress = progress if progress is not None else Progress()
        self._lock = threading.Lock()
        self._running = False
        self._pending: Optional[Tuple[Any, ...]] = None
        self._cancel: Optional[threading.Event] = None  # ends the running job
        self._thread: Optional[threading.Thread] = None  # the thread of the latest job
        self._closed = False

    @property
    def busy(self) -> bool:
        return self._running

    @property
    def closed(self) -> bool:
        return self._closed

    def run(self, cancel: threading.Event, *args: Any) -> Any:
        """The job. Returns its result; raises Cancelled once ``cancel`` is set, and any other exception is an error."""
        raise NotImplementedError

    def publish(self, result: Any, error: Optional[str]) -> None:
        """Hands a finished job over. Called from the job's thread, after the service is free again."""
        self._deliver(result, error)

    def request(self, *args: Any) -> None:
        """Starts a job with these arguments, or keeps them for after the running job."""
        with self._lock:
            if self._closed:
                return
            if self._running:
                self._pending = args  # only the latest request waits
                return
            self._pending = None  # a request made now is newer than one kept earlier
            self._start_locked(args)

    def cancel(self) -> None:
        """Ends the running job: nothing is published for it. A waiting request is dropped; one made later runs."""
        with self._lock:
            self._pending = None
            if self._cancel is not None:
                self._cancel.set()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Ends the service for good: the running job is cancelled, nothing waits, and no job starts afterwards. Waits up
        to ``timeout`` seconds for the job's thread to end."""
        with self._lock:
            self._closed = True
            self._pending = None
            if self._cancel is not None:
                self._cancel.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def _start_locked(self, args: Tuple[Any, ...]) -> None:
        self._running = True
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._work, args=(args, self._cancel), daemon=True)
        self._thread.start()

    def _work(self, args: Tuple[Any, ...], cancel: threading.Event) -> None:
        """Runs the job, then the request kept for it, in this thread. Ends when no request waits."""
        while True:
            result, error, cancelled = self._run_job(args, cancel)
            with self._lock:
                self._running = False  # before the publishing: a reader that sees the service free sees the job ended
                self._cancel = None
            if not cancelled:
                self.publish(result, error)
            with self._lock:
                if self._running or self._closed or self._pending is None:
                    return  # nothing waits, or a request made meanwhile runs in a thread of its own
                args, self._pending = self._pending, None
                cancel = self._cancel = threading.Event()
                self._running = True

    def _run_job(self, args: Tuple[Any, ...], cancel: threading.Event) -> Tuple[Any, Optional[str], bool]:
        result: Any = None
        error: Optional[str] = None
        cancelled = False
        self.progress.start(self.label)
        try:
            result = self.run(cancel, *args)
        except Cancelled:
            cancelled = True
        except Exception as problem:  # the job must always finish and free the service
            error = str(problem) or problem.__class__.__name__
        self.progress.finish()  # before the service is free again: a reader that sees it free sees the job ended
        return result, error, cancelled or cancel.is_set()
