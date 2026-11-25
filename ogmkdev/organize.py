"""Organise PHP imports: sort the top-level ``use`` statements, drop unused ones, find unresolved ones.

Only plain ``use`` statements are handled. A group import (``use A\\{B, C};``) is left alone, and the
file is returned unchanged, so nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .lexers import php_lexer as P


@dataclass(frozen=True)
class UseStatement:
    start: int          # offset of the keyword "use"
    end: int            # offset just after the semicolon
    fqn: str            # imported name without the leading backslash
    alias: str          # name the code uses
    kind: str           # "" (class), "function" or "const"
    line: int
    column: int


def _position(source: str, offset: int):
    line = source.count("\n", 0, offset) + 1
    return line, offset - (source.rfind("\n", 0, offset) + 1) + 1


def top_level_uses(source: str) -> Optional[List[UseStatement]]:
    """The top-level use statements, or ``None`` when a group import makes organising unsafe."""
    tokens = [t for t in P.tokenize(source) if t.kind not in ("html", "open", "close", "comment", "doc")]
    texts = [source[t.start:t.end] for t in tokens]
    statements: List[UseStatement] = []
    depth = 0
    i = 0
    while i < len(tokens):
        text = texts[i]
        if tokens[i].kind == "operator" and text == "{":
            depth += 1
        elif tokens[i].kind == "operator" and text == "}":
            depth -= 1
        elif tokens[i].kind == "keyword" and text.lower() == "use" and depth == 0 \
                and not (i + 1 < len(tokens) and texts[i + 1] == "("):
            j = i + 1
            kind = ""
            if j < len(tokens) and tokens[j].kind == "keyword" and texts[j].lower() in ("function", "const"):
                kind = texts[j].lower()
                j += 1
            names = []
            while j < len(tokens) and texts[j] != ";":
                if texts[j] == "{":
                    return None
                if tokens[j].kind == "name":
                    alias = texts[j].lstrip("\\").rsplit("\\", 1)[-1]
                    fqn = texts[j].lstrip("\\")
                    if j + 2 < len(tokens) and texts[j + 1].lower() == "as" and tokens[j + 2].kind == "name":
                        alias = texts[j + 2]
                        j += 2
                    names.append((fqn, alias, tokens[j].start))
                j += 1
            if j >= len(tokens):
                return None
            end = tokens[j].end
            for fqn, alias, offset in names:
                line, column = _position(source, tokens[i].start)
                statements.append(UseStatement(tokens[i].start, end, fqn, alias, kind, line, column))
            i = j + 1
            continue
        i += 1
    return statements


def _used_names(source: str, statements: List[UseStatement]) -> set:
    skipped = [(s.start, s.end) for s in statements]
    used = set()
    for token in P.tokenize(source):
        if token.kind != "name" and token.kind != "keyword":
            continue
        if any(start <= token.start < end for start, end in skipped):
            continue
        used.add(source[token.start:token.end].lstrip("\\").split("\\", 1)[0].lower())
    return used


def unused_imports(source: str) -> List[UseStatement]:
    statements = top_level_uses(source) or []
    used = _used_names(source, statements)
    return [s for s in statements if s.alias.lower() not in used]


def unresolved_imports(source: str, index) -> List[UseStatement]:
    """Class imports that the project index does not know (libraries are reported as hints)."""
    return [s for s in (top_level_uses(source) or []) if s.kind == "" and not index.find(s.fqn)]


def _statement_text(statement: UseStatement) -> str:
    kind = f"{statement.kind} " if statement.kind else ""
    last = statement.fqn.rsplit("\\", 1)[-1]
    alias = f" as {statement.alias}" if statement.alias.lower() != last.lower() else ""
    return f"use {kind}{statement.fqn}{alias};"


def organize(source: str) -> str:
    """Sorted, de-duplicated top-level imports with unused ones removed."""
    statements = top_level_uses(source)
    if not statements:
        return source
    used = _used_names(source, statements)
    kept = []
    seen = set()
    for statement in statements:
        if statement.alias.lower() not in used:
            continue
        key = (statement.kind, statement.fqn.lower(), statement.alias.lower())
        if key in seen:
            continue
        seen.add(key)
        kept.append(statement)
    region_start = statements[0].start
    region_end = statements[-1].end
    lines = [_statement_text(statement) for statement in sorted(kept, key=lambda s: (s.kind, s.fqn.lower()))]
    block = "\n".join(lines)
    return source[:region_start] + block + source[region_end:] if kept else \
        source[:region_start] + source[region_end:].lstrip("\n")
