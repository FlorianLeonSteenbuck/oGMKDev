"""Workspace: project folders, source and test folders, and ignored folders.

Configured with the ``ogmkdev_source_roots``, ``ogmkdev_test_roots`` and ``ogmkdev_exclude`` keys (global
and project scope, see :mod:`ogmkdev.settings`). Each list is comma separated. An entry with a slash is
a path relative to its project folder (``src/main``); an entry without one is a folder name that is
matched anywhere in the path (``tests``). Ignored folders are hidden from the tree and left out of the
index and of search.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


def _items(text: str) -> Tuple[str, ...]:
    result = []
    for part in text.split(","):
        part = part.strip().replace("\\", "/")
        while part.startswith("./"):
            part = part[2:]
        part = part.strip("/")
        if part:
            result.append(part)
    return tuple(result)


@dataclass
class Workspace:
    folders: List[str] = field(default_factory=list)
    source_roots: Tuple[str, ...] = ()
    test_roots: Tuple[str, ...] = ("tests", "test", "spec")
    excludes: Tuple[str, ...] = (".git", "node_modules", "__pycache__", "vendor")

    @classmethod
    def from_properties(cls, folders: Sequence[str], props: Dict[str, str]) -> "Workspace":
        return cls(
            folders=[os.path.abspath(f) for f in folders],
            source_roots=_items(props.get("ogmkdev_source_roots", "")),
            test_roots=_items(props.get("ogmkdev_test_roots", "tests,test,spec")),
            excludes=_items(props.get("ogmkdev_exclude", ".git,node_modules,__pycache__,vendor")),
        )

    def folder_of(self, path: str) -> Optional[Tuple[str, str]]:
        absolute = os.path.abspath(path)
        for folder in self.folders:
            if absolute == folder or absolute.startswith(folder + os.sep):
                return folder, os.path.relpath(absolute, folder).replace(os.sep, "/")
        return None

    @staticmethod
    def _matches(relative: str, entry: str) -> bool:
        if "/" in entry:
            return relative == entry or relative.startswith(entry + "/")
        return entry in relative.split("/")

    def is_excluded(self, path: str) -> bool:
        located = self.folder_of(path)
        if located is None:
            return False
        _folder, relative = located
        if relative in ("", "."):
            return False
        segments = relative.split("/")
        for entry in self.excludes:
            if "/" in entry:
                if relative == entry or relative.startswith(entry + "/"):
                    return True
            elif any(fnmatch.fnmatch(segment, entry) for segment in segments):
                return True
        return False

    def kind(self, path: str) -> str:
        """``excluded``, ``test``, ``source`` or ``other`` (outside every folder or not in a root)."""
        if self.is_excluded(path):
            return "excluded"
        located = self.folder_of(path)
        if located is None:
            return "other"
        _folder, relative = located
        if any(self._matches(relative, entry) for entry in self.test_roots):
            return "test"
        if not self.source_roots or any(self._matches(relative, entry) for entry in self.source_roots):
            return "source"
        return "other"

    def excluded_predicate(self):
        return self.is_excluded


SKIP_NAMES = {".git", "node_modules", "__pycache__"}


def workspace_files(workspace: "Workspace", limit: int = 20000) -> List[str]:
    """Files of the workspace folders, without ignored folders (for quick open and search)."""
    found: List[str] = []
    for folder in workspace.folders:
        for directory, subdirs, names in os.walk(folder):
            subdirs[:] = [d for d in subdirs if d not in SKIP_NAMES and not workspace.is_excluded(
                os.path.join(directory, d))]
            for name in names:
                path = os.path.join(directory, name)
                if not workspace.is_excluded(path):
                    found.append(path)
                    if len(found) >= limit:
                        return found
    return found
