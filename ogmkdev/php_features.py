"""PHP 8.0 to 8.6 language and library features, detected on the parse tree of :mod:`ogmkdev.parsers.php`.

Every feature has the PHP version that introduced it. :func:`analyze` lists the uses in a source file;
:func:`findings_above` keeps those newer than the version a file targets (``ogmkdev_dialect``).

Sources for the 8.5 and 8.6 items: php.net/releases/8.5 and php.net/releases/8.6 (8.6 was released
on 19 November 2026) and the RFCs they link: pipe operator v3, clone with v2, partial function
application v2 (placeholders ``?`` and ``...``), array_first/array_last, #[\\NoDiscard], closures in
constant expressions, readonly property defaults, clamp(), SortDirection, Time\\Duration, Io\\Poll.
A feature is a node or a flag of the tree: a construct the parser reads is found wherever it stands.
A finding is placed on the keyword or operator that makes the feature, as the token-based check did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .parsers import php as phpparser
from .parsers.syntax import Node, position

Version = Tuple[int, int]


def parse_version(text: str) -> Version:
    major, _, minor = text.partition(".")
    return int(major), int(minor or 0)


# feature id -> (version, description)
FEATURES: Dict[str, Tuple[Version, str]] = {
    "attribute": ((8, 0), "attributes (#[...])"),
    "nullsafe": ((8, 0), "nullsafe operator (?->)"),
    "match": ((8, 0), "match expression"),
    "throw-expression": ((8, 0), "throw as an expression"),
    "named-arguments": ((8, 0), "named arguments"),
    "constructor-promotion": ((8, 0), "constructor property promotion"),
    "class-on-object": ((8, 0), "$object::class"),
    "non-capturing-catch": ((8, 0), "catch without a variable"),
    "enum": ((8, 1), "enums"),
    "readonly-property": ((8, 1), "readonly properties"),
    "first-class-callable": ((8, 1), "first-class callable syntax (f(...))"),
    "never-type": ((8, 1), "never return type"),
    "pure-intersection-types": ((8, 1), "intersection types (A&B)"),
    "octal-prefix": ((8, 1), "0o octal prefix"),
    "final-constants": ((8, 1), "final class constants"),
    "readonly-class": ((8, 2), "readonly classes"),
    "dnf-types": ((8, 2), "disjunctive normal form types ((A&B)|null)"),
    "true-type": ((8, 2), "true as a standalone type"),
    "null-false-type": ((8, 2), "null and false as standalone types"),
    "allow-dynamic-properties": ((8, 2), "#[\\AllowDynamicProperties]"),
    "typed-class-constants": ((8, 3), "typed class constants"),
    "override-attribute": ((8, 3), "#[\\Override]"),
    "dynamic-class-constant": ((8, 3), "dynamic class constant fetch ($c::{$name})"),
    "property-hooks": ((8, 4), "property hooks"),
    "asymmetric-visibility": ((8, 4), "asymmetric visibility (public private(set))"),
    "new-without-parentheses": ((8, 4), "new without parentheses in a chain"),
    "deprecated-attribute": ((8, 4), "#[\\Deprecated]"),
    "pipe-operator": ((8, 5), "pipe operator (|>)"),
    "clone-with": ((8, 5), "clone with arguments"),
    "nodiscard-attribute": ((8, 5), "#[\\NoDiscard]"),
    "closure-in-constant": ((8, 5), "closures in constant expressions"),
    "partial-application": ((8, 6), "partial function application (? and ... placeholders)"),
    "readonly-defaults": ((8, 6), "default values for readonly properties"),
}

# library functions by version (names are matched case-insensitively)
FUNCTIONS: Dict[str, Version] = {
    "str_contains": (8, 0), "str_starts_with": (8, 0), "str_ends_with": (8, 0), "fdiv": (8, 0),
    "get_debug_type": (8, 0), "preg_last_error_msg": (8, 0), "get_resource_id": (8, 0),
    "array_is_list": (8, 1), "enum_exists": (8, 1),
    "memory_reset_peak_usage": (8, 2),
    "json_validate": (8, 3), "mb_str_pad": (8, 3),
    "array_find": (8, 4), "array_find_key": (8, 4), "array_any": (8, 4), "array_all": (8, 4),
    "mb_trim": (8, 4), "mb_ltrim": (8, 4), "mb_rtrim": (8, 4), "mb_ucfirst": (8, 4), "mb_lcfirst": (8, 4),
    "array_first": (8, 5), "array_last": (8, 5),
    "clamp": (8, 6),
}
# classes by version
CLASSES: Dict[str, Version] = {"SortDirection": (8, 6), "Time\\Duration": (8, 6), "Io\\Poll": (8, 6)}


@dataclass(frozen=True)
class Finding:
    line: int
    column: int
    feature: str
    version: Version
    description: str
    kind: str = "feature"    # "feature" for syntax, "function" or "class" for library items

    @property
    def message(self) -> str:
        major, minor = self.version
        return f"{self.description} needs PHP {major}.{minor}"


def analyze(source: str) -> List[Finding]:
    """The features of a PHP source, in source order, with the library functions and classes it uses."""
    tree, _errors = phpparser.parse_partial(source)
    found: List[Finding] = []
    _visit(tree, None, source, False, found)
    return sorted(set(found), key=lambda finding: (finding.line, finding.column, finding.feature))


ATTRIBUTE_FEATURES = {
    "allowdynamicproperties": "allow-dynamic-properties",
    "override": "override-attribute",
    "deprecated": "deprecated-attribute",
    "nodiscard": "nodiscard-attribute",
}
PROMOTION_FLAGS = frozenset({"public", "protected", "private", "readonly"})
# a visibility keyword that makes the set side of an asymmetric property: public private(set)
ASYMMETRIC_SET = re.compile(r"\b(?:public|protected|private)\s*\(\s*set\s*\)", re.IGNORECASE)
# the nodes whose second child is a member after '::' or '->' (a name there is no class)
MEMBER_PARENTS = frozenset({"ClassConstant", "StaticCall", "PropertyAccess", "MethodCall", "NullsafePropertyAccess"})


def _feature(found: List[Finding], source: str, offset: int, feature: str) -> None:
    version, description = FEATURES[feature]
    line, column = position(source, offset)
    found.append(Finding(line, column, feature, version, description, "feature"))


def _head(node: Node) -> int:
    """Where the modifiers of a declaration end: the start of its first child that is not an attribute group."""
    for child in node.children:
        if child.kind != "AttributeGroup":
            return child.start
    return node.end


def _keyword(source: str, word: str, node: Node) -> int:
    """Where the keyword ``word`` stands among the modifiers of a declaration; the node start if it is not there."""
    match = re.compile(rf"\b{word}\b", re.IGNORECASE).search(source, node.start, _head(node))
    return match.start() if match else node.start


def _operator(source: str, node: Node, text: str) -> int:
    """Where the operator ``text`` stands: after the first child of the node; the node start if it is not there."""
    first = node.children[0] if node.children else None
    index = source.find(text, first.end if first is not None else node.start, node.end)
    return index if index >= 0 else node.start


def _visit(node: Node, parent: Optional[Node], source: str, in_attribute: bool, found: List[Finding],
           member: bool = False) -> None:
    _check(node, parent, source, in_attribute, found, member)
    inside = in_attribute or node.kind == "Attribute"
    for index, child in enumerate(node.children):
        _visit(child, node, source, inside, found, member=node.kind in MEMBER_PARENTS and index > 0)


def _check(node: Node, parent: Optional[Node], source: str, in_attribute: bool, found: List[Finding],
           member: bool) -> None:
    kind, flags = node.kind, node.flags
    if kind == "AttributeGroup":
        _feature(found, source, node.start, "attribute")
    elif kind == "Attribute":
        name = _attribute_name(node, source)
        if name in ATTRIBUTE_FEATURES:
            _feature(found, source, node.start, ATTRIBUTE_FEATURES[name])
    elif kind == "NullsafePropertyAccess" or (kind == "MethodCall" and "nullsafe" in flags):
        _feature(found, source, _operator(source, node, "?->"), "nullsafe")
    elif kind == "MatchExpression":
        _feature(found, source, node.start, "match")
    elif kind == "ThrowExpression" and not (parent is not None and parent.kind == "ExpressionStatement"):
        _feature(found, source, node.start, "throw-expression")
    elif kind == "NamedArgument":
        _feature(found, source, node.start, "named-arguments")
    elif kind == "MethodDeclaration":
        _constructor_promotion(node, source, found)
    elif kind == "ClassConstant":
        _class_constant(node, source, found)
    elif kind == "CatchClause":
        if not any(child.kind == "Variable" for child in node.children):
            _feature(found, source, node.start, "non-capturing-catch")
    elif kind == "EnumDeclaration":
        _feature(found, source, _keyword(source, "enum", node), "enum")
    elif kind == "ClassDeclaration" and "readonly" in flags:
        _feature(found, source, _keyword(source, "readonly", node), "readonly-class")
    elif kind == "PropertyDeclaration":
        _property(node, source, found)
    elif kind == "Parameter" and "readonly" in flags:
        _feature(found, source, _keyword(source, "readonly", node), "readonly-property")
    elif kind == "PropertyHooks":
        _feature(found, source, _hooked_variable(node, parent), "property-hooks")
    elif kind == "Arguments" and "callable" in flags:
        _feature(found, source, node.start, "first-class-callable")
    elif kind == "ArgumentPlaceholder":
        _feature(found, source, node.start, "partial-application")
    elif kind == "Type":
        _type(node, source, found)
    elif kind == "Literal" and node.text[:2].lower() == "0o":
        _feature(found, source, node.start, "octal-prefix")
    elif kind == "BinaryExpression" and node.text == "|>":
        _feature(found, source, _operator(source, node, "|>"), "pipe-operator")
    elif kind == "CloneExpression" and "with" in flags:
        _feature(found, source, node.start, "clone-with")
    elif kind in ("Closure", "ArrowFunction") and in_attribute:
        _feature(found, source, node.start, "closure-in-constant")
    elif kind == "NewExpression" and _chained_without_parentheses(node, parent, source):
        _feature(found, source, node.start, "new-without-parentheses")
    elif kind == "Call":
        _library_function(node, source, found)
    elif kind == "Name" and not member:
        _library_class(node, source, found)


def _attribute_name(node: Node, source: str) -> str:
    name = next((child for child in node.children if child.kind == "Name"), None)
    return source[name.start:name.end].lstrip("\\").lower() if name is not None else ""


def _constructor_promotion(node: Node, source: str, found: List[Finding]) -> None:
    name = next((child for child in node.children if child.kind == "Name"), None)
    if name is None or source[name.start:name.end].lower() != "__construct":
        return
    for parameters in node.children:
        if parameters.kind != "ParameterList":
            continue
        if any(parameter.kind == "Parameter" and parameter.flags & PROMOTION_FLAGS for parameter in parameters.children):
            _feature(found, source, name.start, "constructor-promotion")


def _class_constant(node: Node, source: str, found: List[Finding]) -> None:
    if len(node.children) > 1 and node.children[-1].kind == "Name" and node.children[0].kind != "Name" \
            and source[node.children[-1].start:node.children[-1].end].lower() == "class":
        _feature(found, source, node.start, "class-on-object")  # $object::class
    if "dynamic" in node.flags:
        _feature(found, source, _operator(source, node, "::"), "dynamic-class-constant")
    if "final" in node.flags:
        _feature(found, source, _keyword(source, "final", node), "final-constants")
    if any(child.kind == "Type" for child in node.children):
        _feature(found, source, _keyword(source, "const", node), "typed-class-constants")


def _hooked_variable(node: Node, parent: Optional[Node]) -> int:
    """Where the property with the hooks is named: the variable of the element before the hooks."""
    elements = [] if parent is None else [child for child in parent.children
                                          if child.kind == "PropertyElement" and child.end <= node.start]
    if not elements:
        return node.start
    element = max(elements, key=lambda child: child.end)
    return element.children[0].start if element.children else element.start


def _property(node: Node, source: str, found: List[Finding]) -> None:
    if "asymmetric" in node.flags:
        match = ASYMMETRIC_SET.search(source, node.start, _head(node))
        _feature(found, source, match.start() if match else node.start, "asymmetric-visibility")
    if "readonly" in node.flags:
        readonly = _keyword(source, "readonly", node)
        _feature(found, source, readonly, "readonly-property")
        if any(element.kind == "PropertyElement" and len(element.children) > 1 for element in node.children):
            _feature(found, source, readonly, "readonly-defaults")


def _type(node: Node, source: str, found: List[Finding]) -> None:
    members = node.children
    if any(member.kind == "Type" for member in members):
        _feature(found, source, node.start, "dnf-types")
        return
    names = [member for member in members if member.kind == "Name"]
    if len(names) == 1:
        word = source[names[0].start:names[0].end].lower()
        if word == "never":
            _feature(found, source, names[0].start, "never-type")
        elif word == "true":
            _feature(found, source, names[0].start, "true-type")
        elif word in ("null", "false"):
            _feature(found, source, names[0].start, "null-false-type")
    elif len(names) > 1 and all("&" in source[a.end:b.start] for a, b in zip(names, names[1:])):
        first_and = source.find("&", names[0].end, names[1].start)
        _feature(found, source, first_and if first_and >= 0 else node.start, "pure-intersection-types")


def _chained_without_parentheses(node: Node, parent: Optional[Node], source: str) -> bool:
    """new A()->b(): the new expression is the object of a member access, with no parentheses around it."""
    if parent is None or parent.kind not in ("PropertyAccess", "MethodCall") or not parent.children \
            or parent.children[0] is not node:
        return False
    return source[node.end:].lstrip().startswith(("->", "?->"))


def _library_function(node: Node, source: str, found: List[Finding]) -> None:
    callee = node.children[0] if node.children else None
    if callee is None or callee.kind != "Name":
        return
    name = source[callee.start:callee.end].lstrip("\\").lower()
    if name in FUNCTIONS:
        line, column = position(source, callee.start)
        found.append(Finding(line, column, "function:" + name, FUNCTIONS[name], f"{name}()", "function"))


def _library_class(node: Node, source: str, found: List[Finding]) -> None:
    name = source[node.start:node.end].lstrip("\\")
    if name in CLASSES:
        line, column = position(source, node.start)
        found.append(Finding(line, column, "class:" + name, CLASSES[name], f"class {name}", "class"))


def findings_above(source: str, configured: str) -> List[Finding]:
    """Findings newer than the PHP version ``configured`` (for example "8.3")."""
    limit = parse_version(configured)
    return [f for f in analyze(source) if f.version > limit]
