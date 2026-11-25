"""Local history: snapshots of documents outside the project, diffs, patch sets and changed lines.

Every save (and every autosave) can keep a snapshot in the user's data directory
(``$XDG_DATA_HOME/ogmkdev/history``). Nothing is written into the project. A snapshot identical to the
latest one is not stored twice. A patch set is the unified diff of a chosen sequence of revisions.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


def default_history_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "ogmkdev", "history")


@dataclass(frozen=True)
class Revision:
    id: str
    path: str
    timestamp: float
    label: str
    size: int

    @property
    def when(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))


class LocalHistory:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base = base_dir or default_history_dir()

    def _dir(self, path: str) -> str:
        digest = hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()
        return os.path.join(self.base, digest)

    def _index_path(self, path: str) -> str:
        return os.path.join(self._dir(path), "index.json")

    def _entries(self, path: str) -> List[dict]:
        try:
            with open(self._index_path(path), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return []

    def snapshot(self, path: str, text: str, label: str = "save") -> Optional[Revision]:
        """Keep ``text`` as a revision of ``path``. Returns ``None`` when it equals the latest revision."""
        entries = self._entries(path)
        if entries and self.content(self._revision(path, entries[-1])) == text:
            return None
        directory = self._dir(path)
        os.makedirs(directory, exist_ok=True)
        stamp = time.time()
        identifier = f"{time.time_ns()}"
        with open(os.path.join(directory, identifier + ".txt"), "w", encoding="utf-8") as handle:
            handle.write(text)
        entry = {"id": identifier, "timestamp": stamp, "label": label, "size": len(text)}
        entries.append(entry)
        with open(self._index_path(path), "w", encoding="utf-8") as handle:
            json.dump(entries, handle)
        return self._revision(path, entry)

    def _revision(self, path: str, entry: dict) -> Revision:
        return Revision(entry["id"], os.path.abspath(path), entry["timestamp"], entry["label"], entry["size"])

    def revisions(self, path: str) -> List[Revision]:
        """Newest first."""
        return [self._revision(path, e) for e in reversed(self._entries(path))]

    def content(self, revision: Revision) -> str:
        with open(os.path.join(self._dir(revision.path), revision.id + ".txt"), encoding="utf-8") as handle:
            return handle.read()

    @staticmethod
    def diff(old_text: str, new_text: str, old_name: str = "old", new_name: str = "new") -> str:
        return "".join(difflib.unified_diff(old_text.splitlines(keepends=True),
                                            new_text.splitlines(keepends=True),
                                            fromfile=old_name, tofile=new_name))

    def diff_revisions(self, older: Revision, newer: Revision) -> str:
        return self.diff(self.content(older), self.content(newer), f"{older.path} {older.when}",
                         f"{newer.path} {newer.when}")

    def patch_set(self, revisions: Sequence[Revision], base_dir: Optional[str] = None) -> str:
        """One git-style patch: the diffs between consecutive revisions, oldest first.

        Paths are relative to ``base_dir`` (the project folder) when given, so ``git apply`` and
        ``patch -p1`` accept the result.
        """
        ordered = sorted(revisions, key=lambda r: r.timestamp)
        parts = []
        for older, newer in zip(ordered, ordered[1:]):
            name = patch_name(newer.path, base_dir)
            parts.append(file_patch(self.content(older), self.content(newer), name))
        return "".join(parts)

    def extract_patch(self, revisions: Sequence[Revision], destination: str,
                      base_dir: Optional[str] = None) -> str:
        text = self.patch_set(revisions, base_dir)
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write(text)
        return destination


def patch_name(path: str, base_dir: Optional[str] = None) -> str:
    """The name a file has inside a patch: relative to ``base_dir`` with forward slashes."""
    if base_dir:
        try:
            relative = os.path.relpath(os.path.abspath(path), os.path.abspath(base_dir))
            if not relative.startswith(os.pardir):
                return relative.replace(os.sep, "/")
        except ValueError:
            pass
    return os.path.basename(path)


def file_patch(old_text: str, new_text: str, name: str) -> str:
    """A git-style patch for one file (empty when nothing changed)."""
    old_label = f"a/{name}" if old_text else "/dev/null"
    new_label = f"b/{name}" if new_text else "/dev/null"
    lines = []
    for line in difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                                     fromfile=old_label, tofile=new_label):
        lines.append(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    if not lines:
        return ""
    return f"diff --git a/{name} b/{name}\n" + "".join(lines)


def changed_lines(old_text: str, new_text: str) -> Dict[int, str]:
    """Line changes of ``new_text`` against ``old_text``: line number (1-based) to added, modified or deleted.

    A deletion is marked on the line that now follows the removed lines.
    """
    old = old_text.splitlines()
    new = new_text.splitlines()
    marks: Dict[int, str] = {}
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            for line in range(j1 + 1, j2 + 1):
                marks[line] = "added"
        elif tag == "replace":
            for line in range(j1 + 1, j2 + 1):
                marks[line] = "modified"
        elif tag == "delete":
            marks[min(j1 + 1, max(len(new), 1))] = "deleted"
    return marks
