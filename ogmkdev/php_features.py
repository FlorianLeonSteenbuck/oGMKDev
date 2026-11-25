"""PHP 8.0 to 8.6 language and library features, detected on the token stream.

Every feature has the PHP version that introduced it. :func:`analyze` lists the uses in a source file;
:func:`findings_above` keeps those newer than the version a file targets (``ogmkdev_dialect``).

Sources for the 8.5 and 8.6 items: php.net/releases/8.5 and php.net/releases/8.6 (8.6 was released
on 19 November 2026) and the RFCs they link: pipe operator v3, clone with v2, partial function
application v2 (placeholders ``?`` and ``...``), array_first/array_last, #[\\NoDiscard], closures in
constant expressions, readonly property defaults, clamp(), SortDirection, Time\\Duration, Io\\Poll.
Detection is token-based: it is a heuristic per construct and does not replace a full parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .lexers import php_lexer as P

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

_EXPRESSION_BEFORE_THROW = frozenset({"??", "??=", "=", "=>", "?", "||", "&&", "("})
_TYPE_KEYWORDS = frozenset({"int", "float", "string", "bool", "array", "object", "mixed", "null", "false", "true"})
_VISIBILITY = frozenset({"public", "private", "protected"})


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


def _position(source: str, offset: int) -> Tuple[int, int]:
    line = source.count("\n", 0, offset) + 1
    column = offset - (source.rfind("\n", 0, offset) + 1) + 1
    return line, column


def _matching(sig: List[P.Token], source: str, index: int, open_text: str, close_text: str) -> int:
    depth = 0
    for position in range(index, len(sig)):
        text = _text(source, sig[position])
        if text == open_text:
            depth += 1
        elif text == close_text:
            depth -= 1
            if depth == 0:
                return position
    return -1


def _text(source: str, token: P.Token) -> str:
    return source[token.start:token.end]


def analyze(source: str) -> List[Finding]:
    """Every PHP 8.0 to 8.6 feature used in ``source`` (syntax, functions and classes)."""
    tokens = P.tokenize(source)
    sig = [t for t in tokens if t.kind not in ("html", "open", "close", "comment", "doc")]
    found: List[Tuple[int, str]] = []  # (token offset, feature id)
    texts = [_text(source, t).lower() if t.kind in ("keyword", "name") else _text(source, t) for t in sig]
    kinds = [t.kind for t in sig]
    in_attribute = 0

    def add(index: int, feature: str) -> None:
        found.append((sig[index].start, feature))

    for i, token in enumerate(sig):
        text = texts[i]
        prev = texts[i - 1] if i > 0 else ""
        nxt = texts[i + 1] if i + 1 < len(sig) else ""
        if token.kind == "attr":
            in_attribute += 1
            name = texts[i + 1].lstrip("\\") if i + 1 < len(sig) else ""
            add(i, "attribute")
            for attribute, feature in (("override", "override-attribute"), ("nodiscard", "nodiscard-attribute"),
                                       ("deprecated", "deprecated-attribute"),
                                       ("allowdynamicproperties", "allow-dynamic-properties")):
                if name == attribute:
                    add(i + 1, feature)
            continue
        if token.kind == "operator" and text == "]" and in_attribute:
            in_attribute -= 1
            continue
        if token.kind == "operator" and text == "?->":
            add(i, "nullsafe")
        elif token.kind == "operator" and text == "|>":
            add(i, "pipe-operator")
        elif token.kind == "keyword" and text == "match" and nxt == "(":
            add(i, "match")
        elif token.kind == "keyword" and text == "throw" and prev in _EXPRESSION_BEFORE_THROW:
            add(i, "throw-expression")
        elif token.kind == "name" and nxt == ":" and prev in ("(", ","):
            add(i, "named-arguments")
        elif token.kind == "variable" and nxt == "::" and texts[i + 2] == "class":
            add(i, "class-on-object")
        elif token.kind == "keyword" and text == "catch" and nxt == "(" and i + 3 < len(sig) \
                and kinds[i + 2] == "name" and texts[i + 3] == ")":
            add(i, "non-capturing-catch")
        elif token.kind == "keyword" and text == "enum" and kinds[i + 1:i + 2] == ["name"] \
                and texts[i + 2:i + 3] and texts[i + 2] in ("{", ":", "implements"):
            add(i, "enum")
        elif token.kind == "keyword" and text == "readonly":
            if nxt in ("class", "abstract", "final"):
                add(i, "readonly-class")
            else:
                add(i, "readonly-property")
                if _readonly_has_default(sig, texts, kinds, i):
                    add(i, "readonly-defaults")
        elif token.kind == "operator" and text == "(" and nxt == "..." and texts[i + 2:i + 3] == [")"]:
            add(i, "first-class-callable")
        elif token.kind == "operator" and text == "..." and prev == "," and nxt == ")":
            add(i, "partial-application")
        elif token.kind == "operator" and text == "?" and prev in ("(", ",") and nxt in (",", ")"):
            add(i, "partial-application")
        elif token.kind == "keyword" and text == "never":
            add(i, "never-type")
        elif token.kind == "operator" and text == "&" and kinds[i - 1:i] == ["name"] and kinds[i + 1:i + 2] == ["name"] \
                and texts[i + 2:i + 3] and (kinds[i + 2] == "variable" or texts[i + 2] in ("|", ")")):
            add(i, "pure-intersection-types")
        elif token.kind == "keyword" and text == "final" and nxt == "const":
            add(i, "final-constants")
        elif token.kind == "number" and text[:2].lower() == "0o":
            add(i, "octal-prefix")
        elif token.kind == "keyword" and text in ("true", "false", "null") and prev == ":" and nxt in ("{", ";"):
            add(i, "true-type" if text == "true" else "null-false-type")
        elif token.kind == "operator" and text == "(" and i + 4 < len(sig) and texts[i + 2] == "&" \
                and kinds[i + 1] == "name" and kinds[i + 3] == "name" and texts[i + 4] == ")" \
                and texts[i + 5:i + 6] == ["|"]:
            add(i, "dnf-types")
        elif token.kind == "keyword" and text == "const" and i + 3 < len(sig) and kinds[i + 1] in ("name", "keyword") \
                and kinds[i + 2] == "name" and texts[i + 3] == "=":
            add(i, "typed-class-constants")
        elif token.kind == "operator" and text == "::" and nxt == "{":
            add(i, "dynamic-class-constant")
        elif token.kind == "keyword" and text in _VISIBILITY and nxt == "(" and texts[i + 2:i + 4] == ["set", ")"]:
            add(i, "asymmetric-visibility")
        elif token.kind == "keyword" and text == "new" and kinds[i + 1:i + 2] == ["name"] \
                and texts[i + 2:i + 3] == ["("] and _chained_after_new(source, sig, texts, i + 2):
            add(i, "new-without-parentheses")
        elif token.kind == "variable" and nxt == "{" and prev not in ("function", "fn"):
            add(i, "property-hooks")
        elif token.kind == "keyword" and text == "clone" and nxt == "(" and _has_top_level_comma(sig, texts, i + 1):
            add(i, "clone-with")
        elif token.kind == "keyword" and text == "static" and nxt in ("fn", "function") and in_attribute:
            add(i, "closure-in-constant")
        elif token.kind == "name" and nxt == "(" and prev not in ("->", "?->", "::", "function", "new"):
            if text in FUNCTIONS or text.lstrip("\\") in FUNCTIONS:
                found.append((sig[i].start, "function:" + text.lstrip("\\").lower()))
        original = _text(source, token).lstrip("\\")
        if token.kind == "name" and original in CLASSES and prev != "::":
            found.append((sig[i].start, "class:" + original))
        if token.kind == "name" and text.lower() == "__construct" and nxt == "(" \
                and _promotes(sig, texts, i + 1):
            add(i, "constructor-promotion")

    results: List[Finding] = []
    for offset, feature in sorted(set(found)):
        line, column = _position(source, offset)
        if feature.startswith("function:"):
            name = feature.split(":", 1)[1]
            version = FUNCTIONS[name]
            results.append(Finding(line, column, feature, version, f"{name}()", "function"))
        elif feature.startswith("class:"):
            name = feature.split(":", 1)[1]
            results.append(Finding(line, column, feature, CLASSES[name], f"class {name}", "class"))
        else:
            version, description = FEATURES[feature]
            results.append(Finding(line, column, feature, version, description, "feature"))
    return results


def _readonly_has_default(sig, texts, kinds, index: int) -> bool:
    depth = 0
    for position in range(index, len(sig)):
        text = texts[position]
        if text == "(":
            depth += 1
        elif text == ")":
            depth -= 1
            if depth < 0:
                return False
        elif depth == 0 and text in (";", "{"):
            return False
        elif depth == 0 and kinds[position] == "variable" and texts[position + 1:position + 2] == ["="]:
            return True
    return False


def _chained_after_new(source: str, sig, texts, index: int) -> bool:
    if index >= len(sig) or texts[index] != "(":
        return False
    close = _matching(sig, source, index, "(", ")")
    return close >= 0 and close + 1 < len(sig) and texts[close + 1] in ("->", "?->", "::")


def _has_top_level_comma(sig, texts, index: int) -> bool:
    depth = 0
    for position in range(index, len(sig)):
        text = texts[position]
        if text == "(":
            depth += 1
        elif text == ")":
            depth -= 1
            if depth == 0:
                return False
        elif text == "," and depth == 1:
            return True
    return False


def _promotes(sig, texts, index: int) -> bool:
    depth = 0
    for position in range(index, len(sig)):
        text = texts[position]
        if text == "(":
            depth += 1
        elif text == ")":
            depth -= 1
            if depth == 0:
                return False
        elif depth == 1 and text in _VISIBILITY:
            return True
    return False




def findings_above(source: str, configured: str) -> List[Finding]:
    """Findings newer than the PHP version ``configured`` (for example "8.3")."""
    limit = parse_version(configured)
    return [f for f in analyze(source) if f.version > limit]
