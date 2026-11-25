"""Changes of an open file since it was last saved: the lines that differ and the unified diff.

The frame compares the text of the Howl buffer with the file on disk (the saved state). Pure functions,
no GUI: the gutter marks and the Changes tab are drawn from these results.
"""

from __future__ import annotations

import difflib
from typing import List, Tuple

ADDED = "added"
CHANGED = "changed"
DELETED = "deleted"


def line_changes(saved: str, current: str) -> List[Tuple[int, str]]:
    """The marks of the current text against the saved one, as (line, kind) with 1-based lines.

    Inserted lines are added and replaced lines are changed. A block that was removed is marked deleted on
    the line that follows it (on the last line when the block was at the end).
    """
    old = saved.split("\n")
    new = current.split("\n")
    marks: List[Tuple[int, str]] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            marks.extend((line, ADDED) for line in range(j1 + 1, j2 + 1))
        elif tag == "replace":
            marks.extend((line, CHANGED) for line in range(j1 + 1, j2 + 1))
        elif tag == "delete":
            marks.append((min(j1 + 1, len(new)), DELETED))
    return marks


def changed_lines(saved: str, current: str) -> int:
    """How many lines of the current text differ from the saved one (a deleted block counts as one line)."""
    return len({line for line, _kind in line_changes(saved, current)})


def diff_text(saved: str, current: str, saved_name: str = "saved", current_name: str = "buffer") -> str:
    """The unified diff of the saved text and the current one; empty when they are the same."""
    return "\n".join(difflib.unified_diff(saved.split("\n"), current.split("\n"),
                                          saved_name, current_name, lineterm=""))
