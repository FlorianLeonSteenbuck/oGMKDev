"""Workspace: project folders, the folders of each role, and hidden folders.

Configured with the ``ogmkdev_source_roots``, ``ogmkdev_test_roots``, ``ogmkdev_build_roots``,
``ogmkdev_artifact_roots``, ``ogmkdev_asset_roots`` and ``ogmkdev_exclude`` keys (global and project
scope, see :mod:`ogmkdev.settings`). Each list is comma separated. An entry with a slash is a path
relative to its project folder (``src/main``); an entry without one is a folder name that is matched
anywhere in the path (``tests``).

Hidden are the ignored folders and files (``ogmkdev_exclude``, by default IDE configuration such as
``.idea`` and ``*.iml``) and the dot-folders and dot-files, except ``.editorconfig``. Hidden entries are
not in the tree, not in the index and not in search: the index holds what the tree shows.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_EXCLUDES = (".git", "node_modules", "__pycache__", "vendor", ".idea", "*.iml")
DEFAULT_TEST_ROOTS = ("tests", "test", "spec")
DEFAULT_SOURCE_NAMES = ("src", "source", "app", "lib", "include")
DEFAULT_BUILD_NAMES = ("build", "dist", "out", "target", "bin", "obj")
DEFAULT_ARTIFACT_NAMES = ("artifacts", "coverage", "reports", "logs")
DEFAULT_ASSET_NAMES = ("assets", "static", "public", "resources", "images", "fonts")
ROLES = ("test", "source", "build", "artifacts", "assets")


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


FOLDER_ROLES = ("test", "source", "build", "artifacts", "assets", "none")


def _rules(text: str) -> Tuple[Tuple[str, str], ...]:
    """``*_api=build; ui_*=assets`` as ((pattern, role), ...): entries that do not parse are skipped."""
    rules = []
    for entry in text.split(";"):
        pattern, _, role = entry.partition("=")
        pattern, role = pattern.strip(), role.strip().lower()
        if pattern and role in FOLDER_ROLES:
            rules.append((pattern, role))
    return tuple(rules)


@dataclass
class Workspace:
    folders: List[str] = field(default_factory=list)
    source_roots: Tuple[str, ...] = ()
    test_roots: Tuple[str, ...] = DEFAULT_TEST_ROOTS
    excludes: Tuple[str, ...] = DEFAULT_EXCLUDES
    build_roots: Tuple[str, ...] = DEFAULT_BUILD_NAMES
    artifact_roots: Tuple[str, ...] = DEFAULT_ARTIFACT_NAMES
    asset_roots: Tuple[str, ...] = DEFAULT_ASSET_NAMES
    rules: Tuple[Tuple[str, str], ...] = ()  # (pattern, role) of the Custom settings: the first match wins

    @classmethod
    def from_properties(cls, folders: Sequence[str], props: Dict[str, str]) -> "Workspace":
        return cls(
            folders=[os.path.abspath(f) for f in folders],
            source_roots=_items(props.get("ogmkdev_source_roots", "")),
            test_roots=_items(props.get("ogmkdev_test_roots", "tests,test,spec")),
            excludes=_items(props.get("ogmkdev_exclude", ",".join(DEFAULT_EXCLUDES))),
            build_roots=_items(props.get("ogmkdev_build_roots", ",".join(DEFAULT_BUILD_NAMES))),
            artifact_roots=_items(props.get("ogmkdev_artifact_roots", ",".join(DEFAULT_ARTIFACT_NAMES))),
            asset_roots=_items(props.get("ogmkdev_asset_roots", ",".join(DEFAULT_ASSET_NAMES))),
            rules=_rules(props.get("ogmkdev_folder_rules", "")),
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

    def is_hidden(self, path: str) -> bool:
        """Not shown in the tree, not indexed, not searched: ignored, or a dot-folder or dot-file."""
        if self.is_excluded(path):
            return True
        located = self.folder_of(path)
        if located is None:
            return False
        return any(segment.startswith(".") and segment != ".editorconfig"
                   for segment in located[1].split("/") if segment not in ("", "."))

    def role(self, path: str) -> Optional[str]:
        """The role of a folder: ``test``, ``source``, ``build``, ``artifacts`` or ``assets``.

        The first matching role wins in that order; a folder with no role, a hidden folder and a file
        have none. Source folders default to the common names when ``ogmkdev_source_roots`` is empty.
        """
        located = self.folder_of(path)
        if located is None or self.is_hidden(path) or not os.path.isdir(path):
            return None
        relative = located[1]
        if relative in ("", "."):
            return None
        for pattern, rule_role in self.rules:  # a rule names the folder by its path or name and beats the default names
            if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(os.path.basename(relative), pattern):
                return None if rule_role == "none" else rule_role
        sources = self.source_roots or DEFAULT_SOURCE_NAMES
        for role, entries in (("test", self.test_roots), ("source", sources), ("build", self.build_roots),
                              ("artifacts", self.artifact_roots), ("assets", self.asset_roots)):
            if any(self._matches(relative, entry) for entry in entries):
                return role
        return None

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
        return self.is_hidden


SKIP_NAMES = {".git", "node_modules", "__pycache__"}


def workspace_files(workspace: "Workspace", limit: int = 20000) -> List[str]:
    """Files the tree shows in the workspace folders (for quick open and search)."""
    found: List[str] = []
    for folder in workspace.folders:
        for directory, subdirs, names in os.walk(folder):
            subdirs[:] = [d for d in subdirs if d not in SKIP_NAMES and not workspace.is_hidden(
                os.path.join(directory, d))]
            for name in names:
                path = os.path.join(directory, name)
                if not workspace.is_hidden(path):
                    found.append(path)
                    if len(found) >= limit:
                        return found
    return found
