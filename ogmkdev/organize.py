"""Organise PHP imports: sort the top-level ``use`` statements, drop unused ones, find unresolved ones.

The statements and the names of the code come from the parse tree of :mod:`ogmkdev.parsers.php`. A name in a
string or a comment is no use of an import; neither is a method, a property or a declared name that happens to
carry the same name as an import. Only plain ``use`` statements are organised. A group import (``use A\\{B, C};``)
leaves the file alone, and so does a file with a syntax error, since a part the parser could not read may hold
the only use of an import. Code between two groups of imports stays where it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set

from .parsers import php as phpparser
from .parsers.syntax import Node, position

# nodes whose first name is the name they declare: a class, a function, a constant, an argument label
DECLARATIONS = frozenset({"ClassDeclaration", "InterfaceDeclaration", "TraitDeclaration", "EnumDeclaration",
                          "FunctionDeclaration", "MethodDeclaration", "ConstElement", "EnumCase",
                          "NamespaceDeclaration", "NamedArgument"})
# nodes whose second child is a member after '::' or '->': a name there is no reference to an import
MEMBER_PARENTS = frozenset({"ClassConstant", "StaticCall", "PropertyAccess", "MethodCall", "NullsafePropertyAccess"})


@dataclass(frozen=True)
class UseStatement:
    start: int          # offset of the keyword "use"
    end: int            # offset just after the semicolon
    fqn: str            # imported name without the leading backslash
    alias: str          # name the code uses
    kind: str           # "" (class), "function" or "const"
    line: int
    column: int


def _parse(source: str) -> Optional[Node]:
    """The tree of a source without syntax errors; ``None`` when it has one."""
    tree, errors = phpparser.parse_partial(source)
    return None if errors else tree


def _top_level(tree: Optional[Node], source: str) -> Optional[List[UseStatement]]:
    """The use statements outside blocks, one per imported name; ``None`` for a group import or no tree."""
    if tree is None:
        return None
    statements: List[UseStatement] = []
    for node in tree.children:
        if node.kind != "UseStatement":
            continue
        line, column = position(source, node.start)
        for item in node.children:
            if item.kind != "UseItem" or not item.children:
                continue
            if item.text:      # the prefix of a group import: use A\{B, C};
                return None
            name = item.children[0]
            fqn = source[name.start:name.end].lstrip("\\")
            alias = source[item.children[1].start:item.children[1].end] if len(item.children) > 1 \
                else fqn.rsplit("\\", 1)[-1]
            statements.append(UseStatement(node.start, node.end, fqn, alias, node.text, line, column))
    return statements


def _refers(node: Node, parent: Optional[Node], index: int) -> bool:
    """Whether a name is a reference in the code: not the member after '::' or '->', not a declared name."""
    if parent is None:
        return True
    if parent.kind in MEMBER_PARENTS and index > 0:
        return False
    if parent.kind in DECLARATIONS:
        return next((child for child in parent.children if child.kind == "Name"), None) is not node
    return True


def _used_names(tree: Node, source: str) -> Set[str]:
    """The first segment of every name the code refers to, lower-cased (the use statements do not count)."""
    used: Set[str] = set()

    def visit(node: Node, parent: Optional[Node], index: int) -> None:
        if node.kind == "UseStatement":
            return
        if node.kind == "Name" and _refers(node, parent, index):
            used.add(source[node.start:node.end].lstrip("\\").split("\\", 1)[0].lower())
        for child_index, child in enumerate(node.children):
            visit(child, node, child_index)

    visit(tree, None, 0)
    return used


def top_level_uses(source: str) -> Optional[List[UseStatement]]:
    """The top-level use statements, or ``None`` when a group import or a syntax error makes organising unsafe."""
    return _top_level(_parse(source), source)


def unused_imports(source: str) -> List[UseStatement]:
    tree = _parse(source)
    statements = _top_level(tree, source)
    if not statements:
        return []
    used = _used_names(tree, source)
    return [s for s in statements if s.alias.lower() not in used]


def unresolved_imports(source: str, index) -> List[UseStatement]:
    """Class imports that the project index does not know (libraries are reported as hints)."""
    return [s for s in (top_level_uses(source) or []) if s.kind == "" and not index.find(s.fqn)]


def _statement_text(statement: UseStatement) -> str:
    kind = f"{statement.kind} " if statement.kind else ""
    last = statement.fqn.rsplit("\\", 1)[-1]
    alias = f" as {statement.alias}" if statement.alias.lower() != last.lower() else ""
    return f"use {kind}{statement.fqn}{alias};"


def _runs(source: str, statements: List[UseStatement]) -> List[List[UseStatement]]:
    """Groups of use statements with nothing but white space between them; each group is organised on its own."""
    runs: List[List[UseStatement]] = []
    for statement in statements:
        if runs and (statement.start == runs[-1][-1].start
                     or source[runs[-1][-1].end:statement.start].strip() == ""):
            runs[-1].append(statement)
        else:
            runs.append([statement])
    return runs


def organize(source: str) -> str:
    """Sorted, de-duplicated top-level imports with unused ones removed. A file that cannot be organised
    safely is returned as it is."""
    tree = _parse(source)
    statements = _top_level(tree, source)
    if not statements:
        return source
    used = _used_names(tree, source)
    kept_ids: Set[int] = set()
    seen = set()
    for statement in statements:
        if statement.alias.lower() not in used:
            continue
        key = (statement.kind, statement.fqn.lower(), statement.alias.lower())
        if key in seen:
            continue
        seen.add(key)
        kept_ids.add(id(statement))
    pieces: List[str] = []
    cursor = 0
    for run in _runs(source, statements):
        start, end = run[0].start, run[-1].end
        kept = sorted((s for s in run if id(s) in kept_ids), key=lambda s: (s.kind, s.fqn.lower()))
        pieces.append(source[cursor:start])
        if kept:
            pieces.append("\n".join(_statement_text(statement) for statement in kept))
            cursor = end
        else:
            cursor = end
            while cursor < len(source) and source[cursor] == "\n":
                cursor += 1
    pieces.append(source[cursor:])
    return "".join(pieces)
