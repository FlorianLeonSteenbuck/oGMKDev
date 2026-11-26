"""Building the project index in the background, and the folders to watch for changes.

``IndexBuilder`` is a background service (``service.Service``): it builds a ``ProjectIndex`` in a thread of its own and hands
the result over through ``deliver``, called from that thread with (index, folders, error): the index is None and error a
message when the build failed. A cancelled build delivers nothing, and the index stays as it was. The caller takes the index
over on its own thread, so the index is never shared while it is built. One build runs at a time; a request made while one
runs starts a build afterwards (only the latest such request is kept). After ``shutdown`` no build starts. Each finished
build also saves the index cache, so the next start re-indexes only the changed files.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, List, Optional, Sequence

from .index import ProjectIndex
from .service import Cancelled, Service


def watched_directories(roots: Sequence[str], excluded: Optional[Callable[[str], bool]] = None) -> List[str]:
    """The folders under the roots, the roots included, without the excluded ones and what is under them."""
    found: List[str] = []
    for root in roots:
        for dirpath, dirnames, _files in os.walk(root):
            dirnames[:] = [name for name in dirnames if not (excluded and excluded(os.path.join(dirpath, name)))]
            found.append(dirpath)
    return found


class IndexBuilder(Service):
    label = "Index"

    def request(self, roots: Sequence[str], cache_path: Optional[str] = None,
                excluded: Optional[Callable[[str], bool]] = None, settings_for: Optional[Callable] = None) -> None:
        """Starts a build, or keeps the request for after the running build. ``settings_for`` gives the settings a file is
        inspected with; the default is the EditorConfig files of the file alone."""
        super().request(list(roots), cache_path, excluded, settings_for)

    def run(self, cancel: threading.Event, roots: List[str], cache_path: Optional[str], excluded, settings_for):
        index = ProjectIndex(roots, cache_path=cache_path, excluded=excluded, progress=self.progress,
                             settings_for=settings_for, is_cancelled=cancel.is_set)
        folders = watched_directories(index.roots, excluded)
        if cancel.is_set():
            raise Cancelled("the index build was cancelled")
        if cache_path:
            try:
                index.save_cache()
            except OSError:
                pass  # the cache is an optimisation; the index is complete without it
        return index, folders

    def publish(self, result, error: Optional[str]) -> None:
        index, folders = result if result is not None else (None, [])
        self._deliver(index, folders, error)
