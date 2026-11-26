"""The index as numbers per folder: the files, symbols and references of each project folder (a root), and of each folder
directly below a root that has indexed files. The Index tab of the frame draws these numbers; this module has no GTK."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class FolderCount:
    folder: str     # the absolute folder
    label: str      # the folder's name, below a root as "root/folder"
    root: bool      # True for a project folder, False for a folder below one
    files: int
    symbols: int
    references: int


def folder_counts(index, roots: Sequence[str]) -> List[FolderCount]:
    """The counts of every root (all indexed files under it), then of each folder below it. Roots may overlap: a file
    below two roots counts for both, each row is a folder of its own."""
    rows: List[FolderCount] = []
    for root in roots:
        root = os.path.abspath(root)
        name = os.path.basename(root.rstrip(os.sep)) or root
        total = [0, 0, 0]
        below: dict = {}  # the folder name below the root -> [files, symbols, references] of the files in it
        for path, entry in index.files.items():
            relative = os.path.relpath(path, root)
            if relative == os.pardir or relative.startswith(os.pardir + os.sep):
                continue  # the file lies outside this root
            counts = [1, len(entry.symbols), len(entry.references)]
            total = [sum(pair) for pair in zip(total, counts)]
            parts = relative.split(os.sep)
            if len(parts) > 1:
                below[parts[0]] = [sum(pair) for pair in zip(below.get(parts[0], [0, 0, 0]), counts)]
        rows.append(FolderCount(root, name, True, *total))
        for folder in sorted(below):
            files, symbols, references = below[folder]
            rows.append(FolderCount(os.path.join(root, folder), f"{name}/{folder}", False, files, symbols, references))
    return rows
