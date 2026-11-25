"""Git for the workspace: status, staging, unstaging, diffs and commits, through the git command line.

Nothing is cached: every call asks git. Paths are absolute in this API; git gets them relative to the
repository root. A new (untracked) file is shown as ``new``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence


class GitError(RuntimeError):
    pass


def _run(args: Sequence[str], cwd: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or f"git {args[0]} failed")
    return result.stdout


def repository_root(folder: str) -> Optional[str]:
    try:
        return _run(["rev-parse", "--show-toplevel"], folder).strip() or None
    except (GitError, OSError):
        return None


@dataclass(frozen=True)
class Change:
    root: str
    path: str          # absolute path
    index: str         # status letter in the index (staging area), " " when none
    worktree: str      # status letter in the working tree, " " when none

    @property
    def untracked(self) -> bool:
        return self.index == "?" and self.worktree == "?"

    @property
    def staged(self) -> bool:
        return self.index not in (" ", "?")

    @property
    def label(self) -> str:
        if self.untracked:
            return "new"
        if self.worktree.strip():
            return self.worktree
        return self.index.strip()


def status(folder: str) -> List[Change]:
    root = repository_root(folder)
    if root is None:
        return []
    output = _run(["status", "--porcelain=v1", "-z", "--untracked-files=all"], root)
    entries = output.split("\0")
    changes: List[Change] = []
    position = 0
    while position < len(entries):
        entry = entries[position]
        position += 1
        if len(entry) < 4:
            continue
        index, worktree, path = entry[0], entry[1], entry[3:]
        if index in "RC":
            position += 1  # renames and copies are followed by the original path
        changes.append(Change(root, os.path.normpath(os.path.join(root, path)), index, worktree))
    return changes


def _relative(root: str, paths: Sequence[str]) -> List[str]:
    return [os.path.relpath(os.path.abspath(p), root) for p in paths]


def stage(root: str, paths: Sequence[str]) -> None:
    if paths:
        _run(["add", "--", *_relative(root, paths)], root)


def unstage(root: str, paths: Sequence[str]) -> None:
    if paths:
        _run(["reset", "-q", "--", *_relative(root, paths)], root)


def diff(root: str, path: str, staged: bool = False) -> str:
    args = ["diff", "--no-color"] + (["--cached"] if staged else []) + ["--", os.path.relpath(path, root)]
    return _run(args, root)


def commit(root: str, message: str) -> str:
    if not message.strip():
        raise GitError("the commit message is empty")
    return _run(["commit", "-m", message], root)
