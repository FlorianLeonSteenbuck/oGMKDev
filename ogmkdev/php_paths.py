"""Paths that a PHP file builds from its own folder: ``__DIR__ . "/style.css"`` and ``dirname(__FILE__) . '/x.php'``.

Such a path depends on the folder of the file. A Ctrl+click on the string opens the file next to it. The concatenation is
evaluated the way PHP evaluates it: the string literals of the chain are joined to the folder, nothing else is added.
This module has no GTK; the frame uses :func:`path_at` for Ctrl+click in PHP files.
"""

from __future__ import annotations

import os
import re
from typing import Optional

_LITERAL = r"""(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""
_DIRECTORY = r"(?:__DIR__|dirname\(\s*__FILE__\s*\))"
_CHAIN = re.compile(rf"{_DIRECTORY}(?P<chain>(?:\s*\.\s*{_LITERAL})+)")
_LITERAL_PATTERN = re.compile(_LITERAL)


def _value(literal: str) -> str:
    """The text of a PHP string literal: the quotes removed, the escaped quote and backslash turned back."""
    return literal[1:-1].replace("\\\\", "\\").replace("\\'", "'").replace('\\"', '"')


def path_at(line: str, column: int, folder: str) -> Optional[str]:
    """The path that the chain of string literals on ``line`` builds from ``folder`` when the 1-based ``column`` lies in
    one of its literals (in any of them: the whole chain is one path), or None for every other place of the line."""
    index = column - 1
    if index < 0:
        return None
    for match in _CHAIN.finditer(line):
        chain = match.group("chain")
        base = match.start("chain")
        literals = list(_LITERAL_PATTERN.finditer(chain))
        if any(base + literal.start() <= index < base + literal.end() for literal in literals):
            text = "".join(_value(literal.group(0)) for literal in literals)
            return os.path.normpath(folder + text)
    return None
