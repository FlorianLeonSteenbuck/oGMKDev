"""The declarations and the names of a PHP file, read from the parse tree of :mod:`ogmkdev.parsers.php`.

The project index takes its PHP symbols from here: the namespaces and the imports of a file, its classes, interfaces,
traits, enums and functions, their members, the classes they extend, implement and use, and the classes their bodies
refer to. A name is resolved the way PHP resolves it: an alias of a ``use`` statement first, else the namespace it is
written in. The names of a file (for the references) are the names of its code: comments, strings and inline HTML hold
none, and neither do the keywords and the builtin types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .parsers.php import Node
from .parsers.syntax import position

CLASS_KINDS = {
    "ClassDeclaration": "class",
    "InterfaceDeclaration": "interface",
    "TraitDeclaration": "trait",
    "EnumDeclaration": "enum",
}

# names that are not classes or constants: keywords and builtin types, which the code uses as names too
RESERVED = frozenset({
    "self", "static", "parent", "class", "int", "integer", "float", "double", "bool", "boolean", "string", "array",
    "callable", "iterable", "object", "mixed", "void", "null", "never", "false", "true",
})


@dataclass
class Member:
    kind: str       # method, constant or property
    name: str       # as the index names it: "speak", "SIDES", "$helper" (a property keeps its dollar sign)
    line: int
    column: int


@dataclass
class Declaration:
    kind: str                                   # class, interface, trait, enum or function
    name: str                                   # fully qualified
    line: int                                   # of the name
    column: int
    abstract: bool = False
    supertypes: Tuple[str, ...] = ()            # extends and implements, resolved
    traits: Tuple[str, ...] = ()                # used traits, resolved
    references: Tuple[str, ...] = ()            # the classes the body refers to, resolved, in order of appearance
    members: List[Member] = field(default_factory=list)


def declarations(tree: Node, source: str) -> List[Declaration]:
    """The classes, interfaces, traits, enums and functions of a file, in source order. A class counts wherever it is
    declared; a function only at the top level of the file or of a namespace, as PHP has them. An anonymous class (the
    body of ``new class``) is no declaration."""
    found: List[Declaration] = []
    _statements(tree.children, _Scope(""), True, source, found)
    return found


def occurrences(tree: Node, source: str) -> List[Tuple[str, int, int]]:
    """Every name of the code as (short name, line, column), in source order. A qualified name is an occurrence of its
    last part: ``\\App\\Circle`` is ``Circle``."""
    found: List[Tuple[str, int, int]] = []
    for node in tree.walk():
        if node.kind != "Name":
            continue
        short = source[node.start:node.end].rsplit("\\", 1)[-1]
        if not short or short.lower() in RESERVED:
            continue
        line, column = position(source, node.end - len(short))
        found.append((short, line, column))
    return found


class _Scope:
    """A namespace and the classes its file imports with ``use`` (alias in lower case, fully qualified name)."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.imports: Dict[str, str] = {}

    def qualify(self, name: str) -> str:
        return f"{self.namespace}\\{name}" if self.namespace else name

    def resolve(self, name: str) -> str:
        if name.startswith("\\"):
            return name[1:]
        first, _, rest = name.partition("\\")
        if first.lower() == "namespace":
            return self.qualify(rest) if rest else self.namespace
        target = self.imports.get(first.lower())
        if target is not None:
            return target + ("\\" + rest if rest else "")
        return self.qualify(name)


def _statements(nodes: Sequence[Node], scope: _Scope, top: bool, source: str, out: List[Declaration]) -> None:
    """The statements of one level. A namespace statement (without a block) changes the scope of the statements after
    it; a namespace block has its own scope; a ``use`` statement of classes adds its imports to the scope."""
    for node in nodes:
        if node.kind == "NamespaceDeclaration":
            name = _namespace_name(node, source)
            block = next((child for child in node.children if child.kind == "BlockStatement"), None)
            if block is None:
                scope = _Scope(name)
            else:
                _statements(block.children, _Scope(name), True, source, out)
        elif node.kind == "UseStatement":
            if not node.text:  # 'use function' and 'use const' import no class
                _add_imports(node, scope, source)
        else:
            _visit(node, scope, top, source, out, declared=True)


def _visit(node: Node, scope: _Scope, top: bool, source: str, out: List[Declaration], declared: bool) -> None:
    if declared:
        if node.kind in CLASS_KINDS:
            out.append(_class(node, scope, source))
        elif node.kind == "FunctionDeclaration" and top:
            declaration = _function(node, scope, source)
            if declaration is not None:
                out.append(declaration)
    for child in node.children:
        # the body of 'new class' is an anonymous class: its members are read, it is no declaration
        anonymous = node.kind == "NewExpression" and child.kind in CLASS_KINDS
        _visit(child, scope, False, source, out, declared=not anonymous)


def _namespace_name(node: Node, source: str) -> str:
    name = next((child for child in node.children if child.kind == "Name"), None)
    return source[name.start:name.end].strip("\\") if name is not None else ""


def _add_imports(node: Node, scope: _Scope, source: str) -> None:
    for item in node.children:
        if item.kind != "UseItem":
            continue
        names = [child for child in item.children if child.kind == "Name"]
        if not names:
            continue
        written = source[names[0].start:names[0].end]
        prefix = item.text  # the prefix of a group: use App\{Helper} gives App for Helper
        fqn = (prefix + "\\" + written if prefix else written).strip("\\")
        alias = source[names[1].start:names[1].end] if len(names) > 1 else fqn.rsplit("\\", 1)[-1]
        scope.imports[alias.lower()] = fqn


def _function(node: Node, scope: _Scope, source: str) -> Optional[Declaration]:
    name = next((child for child in node.children if child.kind == "Name"), None)
    if name is None:
        return None
    line, column = position(source, name.start)
    return Declaration("function", scope.qualify(source[name.start:name.end]), line, column)


def _class(node: Node, scope: _Scope, source: str) -> Declaration:
    kind = CLASS_KINDS[node.kind]
    names = [child for child in node.children if child.kind == "Name"]
    declared, heritage = names[0], names[1:]
    line, column = position(source, declared.start)
    declaration = Declaration(
        kind=kind,
        name=scope.qualify(source[declared.start:declared.end]),
        line=line,
        column=column,
        abstract=kind == "interface" or "abstract" in node.flags,
        supertypes=tuple(scope.resolve(source[name.start:name.end]) for name in heritage),
    )
    body = next((child for child in node.children if child.kind == "ClassBody"), None)
    if body is None:
        return declaration
    traits: List[str] = []
    references: List[str] = []
    for member in body.children:
        if member.kind == "TraitUse":
            traits.extend(scope.resolve(source[name.start:name.end])
                          for name in member.children if name.kind == "Name")
        elif member.kind == "MethodDeclaration":
            _add_member(declaration, "method", member, source)
        elif member.kind == "PropertyDeclaration":
            for element in member.children:
                if element.kind == "PropertyElement":
                    variable = next((child for child in element.children if child.kind == "Variable"), None)
                    if variable is not None:
                        _add_member(declaration, "property", variable, source)
        elif member.kind == "ClassConstant":
            for element in member.children:
                if element.kind == "ConstElement":
                    _add_member(declaration, "constant", element, source)
        elif member.kind == "EnumCase":
            _add_member(declaration, "constant", member, source)
    for node_in_body in body.walk():
        references.extend(_references_of(node_in_body, scope, source))
    declaration.traits = tuple(traits)
    declaration.references = tuple(dict.fromkeys(references))
    return declaration


def _add_member(declaration: Declaration, kind: str, node: Node, source: str) -> None:
    """A member is named by its first name child (a variable, for a property, names the node itself)."""
    if kind == "property":
        name_node = node
    else:
        name_node = next((child for child in node.children if child.kind == "Name"), None)
    if name_node is None:
        return
    line, column = position(source, name_node.start)
    text = source[name_node.start:name_node.end]
    declaration.members.append(Member(kind, text, line, column))


def _references_of(node: Node, scope: _Scope, source: str) -> List[str]:
    """The classes a node of a class body refers to: a type, the class of 'new', 'instanceof', 'catch', an attribute,
    or the class in front of '::'. Builtin types and the keywords self, static and parent are no class."""
    if node.kind == "Type":
        candidates = [child for child in node.children if child.kind == "Name"]
    elif node.kind == "CatchClause":
        candidates = [child for child in node.children if child.kind == "Name"]
    elif node.kind == "BinaryExpression" and node.text.lower() == "instanceof":
        candidates = [child for child in node.children if child.kind == "Name"]
    elif node.kind in ("NewExpression", "StaticCall", "StaticProperty", "ClassConstant", "Attribute"):
        candidates = [child for child in node.children if child.kind == "Name"][:1]
    else:
        return []
    found: List[str] = []
    for candidate in candidates:
        text = source[candidate.start:candidate.end]
        if text.rsplit("\\", 1)[-1].lower() in RESERVED:
            continue
        found.append(scope.resolve(text))
    return found
