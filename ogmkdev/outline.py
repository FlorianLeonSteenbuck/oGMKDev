"""The outline of a JavaScript or TypeScript file, read from the parse tree of :mod:`ogmkdev.parsers.javascript`.

The outline lists the classes with their methods, accessors and fields, the functions, and the variables (a
variable that holds a function is listed as a function). In TypeScript it also lists the interfaces with their
members, the type aliases, the enums and the namespaces with their declarations. Each item has the line and the
column of its name, so the Structure tab can open it. A file with a syntax error has no outline: the error is
returned instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .parsers import javascript as jsparser

NAME_KINDS = ("Identifier", "PrivateName")
FUNCTION_VALUES = ("ArrowFunction", "FunctionExpression")
WRAPPERS = ("ExportNamedDeclaration", "ExportDefaultDeclaration", "AmbientDeclaration")
NAMESPACES = ("NamespaceDeclaration", "ModuleDeclaration")
MODIFIERS = ("public", "private", "protected", "static", "abstract", "override", "readonly", "async")


@dataclass
class Item:
    label: str      # what the tree shows, e.g. "class Animal", "speak()", "const shout"
    kind: str       # class, interface, type, enum, namespace, function, variable, method, accessor, field, member
    line: int       # 1-based line of the name (of the declaration when it has no name)
    column: int     # 1-based column of the name, in characters
    children: List[Item] = field(default_factory=list)


def count(items: Sequence[Item]) -> int:
    """The number of items, their children included."""
    return sum(1 + count(item.children) for item in items)


def script_outline(source: str, typed: bool = False, jsx: bool = True) -> Tuple[List[Item], Optional[str]]:
    """The outline of ``source``, and the message of its syntax error when it has one (the outline is then empty)."""
    try:
        tree = jsparser.parse(source, typed=typed, jsx=jsx)
    except jsparser.ParseError as error:
        return [], f"syntax error at line {error.line}: {error.message}"
    except RecursionError:
        return [], "nested too deeply for the outline"
    return _declarations(source, tree.children), None


def _position(source: str, offset: int) -> Tuple[int, int]:
    line = source.count("\n", 0, offset) + 1
    column = offset - (source.rfind("\n", 0, offset) + 1) + 1
    return line, column


def _item(source: str, label: str, kind: str, offset: int, children: Optional[List[Item]] = None) -> Item:
    line, column = _position(source, offset)
    return Item(label, kind, line, column, children or [])


def _name_child(node):
    """The first child of a node when that child is a name (an identifier or a private name), else None."""
    if node.children and node.children[0].kind in NAME_KINDS:
        return node.children[0]
    return None


def _member_key(node) -> Tuple[str, int]:
    """The name of a member (its first child: an identifier, a private name or a string) and where it is. A
    computed name has no text of its own."""
    key = node.children[0] if node.children else None
    if key is not None and key.kind in NAME_KINDS + ("Literal",):
        return key.text, key.start
    return "[computed]", node.start


def _modifiers(node) -> str:
    return "".join(f"{word} " for word in MODIFIERS if word in node.flags)


def _named(source: str, node, word: str, kind: str, children: Optional[List[Item]] = None) -> Item:
    """A declaration that is named by its first child: ``word`` and the name, e.g. "interface Shape"."""
    name = _name_child(node)
    if name is None:
        return _item(source, word, kind, node.start, children)
    return _item(source, f"{word} {name.text}", kind, name.start, children)


def _class(source: str, node) -> Item:
    # the first identifier of a class is its name only when the keyword stands right before it: the superclass
    # of an anonymous class (class extends Base) is no name
    name = _name_child(node)
    named = name is not None and source[node.start:name.start].rstrip().endswith("class")
    prefix = "abstract " if "abstract" in node.flags else ""
    members: List[Item] = []
    for child in node.children:
        if child.kind == "MethodDefinition":
            members.append(_method(source, child))
        elif child.kind == "FieldDefinition":
            members.append(_field(source, child))
    if not named:
        return _item(source, f"{prefix}class", "class", node.start, members)
    return _item(source, f"{prefix}class {name.text}", "class", name.start, members)


def _method(source: str, node) -> Item:
    name, offset = _member_key(node)
    if node.text in ("get", "set"):
        return _item(source, f"{_modifiers(node)}{node.text} {name}", "accessor", offset)
    return _item(source, f"{_modifiers(node)}{name}()", "method", offset)


def _field(source: str, node) -> Item:
    name, offset = _member_key(node)
    return _item(source, f"{_modifiers(node)}{name}", "field", offset)


def _variables(source: str, node) -> List[Item]:
    items: List[Item] = []
    for declarator in node.children:
        if declarator.kind != "VariableDeclarator":
            continue
        name = _name_child(declarator)
        if name is None:
            continue  # a destructuring pattern names no single variable
        holds_function = any(child.kind in FUNCTION_VALUES for child in declarator.children)
        items.append(_item(source, f"{node.text} {name.text}", "function" if holds_function else "variable",
                           name.start))
    return items


def _interface(source: str, node) -> Item:
    members: List[Item] = []
    for body in node.children:
        if body.kind != "TypeLiteral":
            continue
        for member in body.children:
            if member.kind == "MethodSignature":
                name, offset = _member_key(member)
                members.append(_item(source, f"{name}()", "member", offset))
            elif member.kind == "PropertySignature":
                name, offset = _member_key(member)
                members.append(_item(source, name, "member", offset))
    return _named(source, node, "interface", "interface", members)


def _enum(source: str, node) -> Item:
    members: List[Item] = []
    for member in node.children:
        if member.kind == "EnumMember":
            name, offset = _member_key(member)
            members.append(_item(source, name, "member", offset))
    return _named(source, node, "enum", "enum", members)


def _namespace(source: str, node) -> Item:
    children: List[Item] = []
    for block in node.children:
        if block.kind == "ModuleBlock":
            children.extend(_declarations(source, block.children))
    return _named(source, node, "namespace", "namespace", children)


def _declarations(source: str, nodes) -> List[Item]:
    items: List[Item] = []
    for node in nodes:
        kind = node.kind
        if kind in WRAPPERS:  # export, export default and declare wrap the declaration they mark
            items.extend(_declarations(source, node.children))
        elif kind == "ClassDeclaration":
            items.append(_class(source, node))
        elif kind == "FunctionDeclaration":
            items.append(_named(source, node, "async function" if "async" in node.flags else "function", "function"))
        elif kind == "VariableDeclaration":
            items.extend(_variables(source, node))
        elif kind == "InterfaceDeclaration":
            items.append(_interface(source, node))
        elif kind == "TypeAliasDeclaration":
            items.append(_named(source, node, "type", "type"))
        elif kind == "EnumDeclaration":
            items.append(_enum(source, node))
        elif kind in NAMESPACES:
            items.append(_namespace(source, node))
    return items
