"""The syntax error and the tree node that the JavaScript and TypeScript parsers share."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


class ParseError(Exception):
    """A syntax error at the 1-based ``line`` and ``column``; ``message`` names the token.

    ``lexical`` is true when the token itself is malformed (an unterminated string, a character that
    starts no token) and false when it is out of place."""

    def __init__(self, line: int, column: int, message: str, lexical: bool = False) -> None:
        super().__init__(f"{line}:{column}: {message}")
        self.line = line
        self.column = column
        self.message = message
        self.lexical = lexical


@dataclass
class Node:
    """A node of the tree: its ``kind`` (``"Program"``, ``"BinaryExpression"``...), the offsets of
    its text, its children, a ``text`` (names, operators, literal text) and ``flags``."""

    kind: str
    start: int
    end: int
    children: List["Node"] = field(default_factory=list)
    text: str = ""
    flags: frozenset = frozenset()

    def walk(self):
        """This node and every node below it, in source order."""
        yield self
        for child in self.children:
            yield from child.walk()


def position(source: str, offset: int) -> Tuple[int, int]:
    """The 1-based line and column of ``offset``; columns count characters."""
    line = source.count("\n", 0, offset) + 1
    column = offset - (source.rfind("\n", 0, offset) + 1) + 1
    return line, column


def flags(*names: str) -> frozenset:
    """The non-empty names as a frozen set (an empty name is ignored, so a condition can be passed)."""
    return frozenset(name for name in names if name)
