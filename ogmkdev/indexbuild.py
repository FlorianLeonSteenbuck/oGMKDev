"""Building the project index in the background, and the folders to watch for changes.

``IndexBuilder`` builds a ``ProjectIndex`` in a worker thread and hands it over through ``deliver``,
called from that thread with (index, folders, error): the index is None and error a message when the
build failed. The caller takes the index over on its own thread, so the index is never shared while
it is built. One build runs at a time; a request made while one runs starts a build afterwards (only
the latest such request is kept). Each finished build also saves the index cache, so the next start
re-indexes only the changed files.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, List, Optional, Sequence, Tuple

from .index import ProjectIndex
from .progress import Progress

Deliver = Callable[[Optional[ProjectIndex], List[str], Optional[str]], None]
Request = Tuple[Sequence[str], Optional[str], Optional[Callable[[str], bool]], Optional[Callable]]


def watched_directories(roots: Sequence[str], excluded: Optional[Callable[[str], bool]] = None) -> List[str]:
    """The folders under the roots, the roots included, without the excluded ones and what is under them."""
    found: List[str] = []
    for root in roots:
        for dirpath, dirnames, _files in os.walk(root):
            dirnames[:] = [name for name in dirnames if not (excluded and excluded(os.path.join(dirpath, name)))]
            found.append(dirpath)
    return found


class IndexBuilder:
    def __init__(self, deliver: Deliver, progress: Optional[Progress] = None) -> None:
        self._deliver = deliver
        self.progress = progress if progress is not None else Progress()
        self._lock = threading.Lock()
        self._running = False
        self._pending: Optional[Request] = None

    @property
    def busy(self) -> bool:
        return self._running

    def request(self, roots: Sequence[str], cache_path: Optional[str] = None,
                excluded: Optional[Callable[[str], bool]] = None, settings_for: Optional[Callable] = None) -> None:
        """Starts a build, or keeps the request for after the running build. ``settings_for`` gives the settings a file is
        inspected with; the default is the EditorConfig files of the file alone."""
        with self._lock:
            if self._running:
                self._pending = (list(roots), cache_path, excluded, settings_for)
                return
            self._running = True
        threading.Thread(target=self._work, args=(list(roots), cache_path, excluded, settings_for), daemon=True).start()

    def _work(self, roots: List[str], cache_path: Optional[str], excluded, settings_for) -> None:
        index: Optional[ProjectIndex] = None
        folders: List[str] = []
        error: Optional[str] = None
        self.progress.start("Index")
        try:
            index = ProjectIndex(roots, cache_path=cache_path, excluded=excluded, progress=self.progress,
                                 settings_for=settings_for)
            folders = watched_directories(index.roots, excluded)
            if cache_path:
                try:
                    index.save_cache()
                except OSError:
                    pass  # the cache is an optimisation; the index is complete without it
        except Exception as problem:  # the worker must always finish and free the builder
            error = str(problem) or problem.__class__.__name__
        self.progress.finish()  # before the builder is free again: a reader that sees it free sees the task ended
        with self._lock:
            self._running = False
            pending, self._pending = self._pending, None
        self._deliver(index, folders, error)
        if pending is not None:
            self.request(*pending)
