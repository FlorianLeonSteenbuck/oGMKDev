"""Doc comments generated from the signature of a function, method or class.

A doc comment lists each parameter with its type and name, the return type, and for a class its
properties: the fields and the constructor parameters that are promoted to properties. The text is
read from the source, not from a syntax tree: the declaration on the cursor line (or within the next
few lines) is taken, with the parameters, the return type and the members of its class body.

* PHP: a PHPDoc block (``@param``, ``@return``, ``@property``);
* TypeScript and JavaScript: a JSDoc block (``@param {type} name``, ``@returns``, ``@property``);
* Python: a Google-style docstring inside the function or class, below its header.

:func:`generate` returns the block and the 1-based line it goes in front of (for Python the line below
the header, the block is the docstring's lines with their indentation).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Param:
    name: str           # as written: "$items" in PHP, "items" elsewhere
    type: str           # the declared type, "" when none
    default: str = ""
    variadic: bool = False
    promoted: bool = False  # a constructor parameter that is also a property


@dataclass
class Signature:
    kind: str                       # function | class
    name: str
    params: List[Param] = field(default_factory=list)
    returns: str = ""               # the declared return type, "" when none
    members: List[Tuple[str, str]] = field(default_factory=list)  # (type, name) of the properties


@dataclass
class DocBlock:
    line: int                       # 1-based line the block goes in front of
    text: str                       # the lines of the block, indented, without a final newline


FAMILIES = {"php": "php", "ecmascript": "js", "typescript": "js", "tsx": "js", "jsx": "js",
            "python": "py", "pypy": "py"}

PHP_CLASS = re.compile(r"^\s*(?:(?:abstract|final|readonly)\s+)*(class|interface|trait|enum)\s+([A-Za-z_]\w*)")
PHP_FUNCTION = re.compile(r"^\s*(?:(?:public|protected|private|static|final|abstract)\s+)*function\s+&?"
                          r"([A-Za-z_]\w*)\s*\(")
PHP_PARAM = re.compile(r"""^\s*(?:#\[.*?\]\s*)*(?P<mods>(?:(?:public|protected|private|readonly)\s+)*)"""
                       r"""(?P<type>[^$&.]*?)\s*(?P<ref>&?)\s*(?P<variadic>\.\.\.)?\s*\$(?P<name>\w+)\s*"""
                       r"""(?:=\s*(?P<default>.*?))?\s*$""", re.S)
PHP_PROPERTY = re.compile(r"^\s*(?:(?:public|protected|private|static|readonly|var)\s+)*"
                          r"(?:(?P<type>\??[\w\\|]+)\s+)?\$(?P<name>\w+)\s*(?:=|;)")

JS_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(class|interface)\s+([A-Za-z_$][\w$]*)")
JS_FUNCTION = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*"
                         r"([A-Za-z_$][\w$]*)?\s*(?:<[^>]*>)?\s*\(")
JS_ARROW = re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?=\s*(?:async\s+)?"
                      r"(?:<[^>]*>\s*)?\(")
JS_METHOD = re.compile(r"^\s*(?:(?:public|private|protected|static|async|readonly|abstract|override|get|set)\s+)*"
                       r"\*?([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\(")
JS_NOT_A_METHOD = frozenset({"if", "for", "while", "switch", "catch", "return", "function", "with", "super"})
TS_PARAM = re.compile(r"^\s*(?:(?:public|private|protected|readonly)\s+)*(?P<variadic>\.\.\.)?"
                      r"(?P<name>[A-Za-z_$][\w$]*|\{.*?\}|\[.*?\])\s*(?P<optional>\?)?\s*(?::\s*(?P<type>[^=]+?))?"
                      r"\s*(?:=\s*(?P<default>.*))?$", re.S)
TS_FIELD = re.compile(r"^\s*(?:(?:public|private|protected|readonly|static|declare|abstract)\s+)*"
                      r"(?P<name>[A-Za-z_$][\w$]*)\s*\??\s*:\s*(?P<type>[^;=(]+?)\s*(?:=.*)?;?\s*$")

PY_CLASS = re.compile(r"^(\s*)class\s+([A-Za-z_]\w*)")
PY_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(")
PY_ANNOTATED = re.compile(r"^\s{4}([A-Za-z_]\w*)\s*:\s*([^=]+?)\s*(?:=.*)?$")


def family_of(language: str) -> Optional[str]:
    return FAMILIES.get(language)


def _line_starts(text: str) -> List[int]:
    return [0] + [match.end() for match in re.finditer("\n", text)]


def _close_paren(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_top(text: str) -> List[str]:
    """Splits a parameter list at the commas outside brackets, generics and strings."""
    parts: List[str] = []
    depth = 0
    quote = None
    current = ""
    for char in text:
        if quote:
            current += char
            if char == quote:
                quote = None
            continue
        if char in "\"'`":
            quote = char
        elif char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current)
    return [part.strip() for part in parts if part.strip()]


def _braces(line: str) -> int:
    opened = line.count("{")
    closed = line.count("}")
    return opened - closed


# ------------------------------------------------------------------ PHP

def _php_params(params_text: str) -> List[Param]:
    found = []
    for part in _split_top(params_text):
        match = PHP_PARAM.match(part)
        if not match:
            continue
        default = (match.group("default") or "").strip()
        mods = match.group("mods") or ""
        found.append(Param(name="$" + match.group("name"),
                           type=(match.group("type") or "").strip(),
                           default=default,
                           variadic=bool(match.group("variadic")),
                           promoted=bool(re.search(r"\b(public|protected|private)\b", mods))))
    return found


def _php_promoted_in_class(lines: List[str], class_index: int) -> List[Param]:
    """The promoted parameters of the constructor in the body of the class at class_index."""
    depth = 0
    opened = False
    for index in range(class_index, len(lines)):
        line = lines[index]
        if opened and depth == 1:
            match = PHP_FUNCTION.match(line)
            if match and match.group(1) == "__construct":
                sig = _php_signature(lines, index, match, 0)
                return [p for p in (sig.params if sig else []) if p.promoted]
        depth += _braces(line)
        if "{" in line:
            opened = True
        if opened and depth <= 0:
            break
    return []


def _php_class_members(lines: List[str], start: int, promoted: List[Param]) -> List[Tuple[str, str]]:
    members: List[Tuple[str, str]] = [(p.type, p.name[1:]) for p in promoted]
    depth = 0
    opened = False
    for index in range(start, len(lines)):
        line = lines[index]
        if opened and depth == 1 and "(" not in line:
            match = PHP_PROPERTY.match(line)
            if match and match.group("name") not in [name for _t, name in members]:
                members.append((match.group("type") or "", match.group("name")))
        depth += _braces(line)
        if "{" in line:
            opened = True
        if opened and depth <= 0:
            break
    return members


def _php_signature(lines: List[str], line_index: int, match, text_lines_offset: int) -> Signature:
    """Signature of a PHP function or method whose declaration line is line_index."""
    line = lines[line_index]
    if PHP_CLASS.match(line):
        return None  # classes are read by _php_class
    open_char = line.index("(", match.start(1))
    joined = "\n".join(lines[line_index:line_index + 12])
    close = _close_paren(joined, open_char)
    params_text = joined[open_char + 1:close] if close > 0 else ""
    rest = joined[close + 1:] if close > 0 else ""
    return_match = re.match(r"\s*:\s*(\??[\w\\|]+)", rest)
    returns = return_match.group(1) if return_match else ""
    params = _php_params(params_text)
    return Signature(kind="function", name=match.group(1), params=params, returns=returns)


# ------------------------------------------------------------------ TypeScript and JavaScript

def _js_params(params_text: str) -> List[Param]:
    found = []
    for part in _split_top(params_text):
        match = TS_PARAM.match(part)
        if not match:
            continue
        found.append(Param(name=match.group("name"), type=(match.group("type") or "").strip(),
                           default=(match.group("default") or "").strip(),
                           variadic=bool(match.group("variadic")),
                           promoted=bool(re.match(r"^\s*(?:public|private|protected|readonly)\b", part))))
    return found


def _js_return(rest: str) -> str:
    match = re.match(r"\s*:\s*([^{=;]+?)\s*(?:\{|=>|;|$)", rest)
    return match.group(1) if match else ""


def _js_class_members(lines: List[str], start: int, promoted: List[Param]) -> List[Tuple[str, str]]:
    members: List[Tuple[str, str]] = [(p.type, p.name) for p in promoted if p.type]
    depth = 0
    opened = False
    for index in range(start, len(lines)):
        line = lines[index]
        if opened and depth == 1 and "(" not in line:
            match = TS_FIELD.match(line)
            if match and match.group("name") not in [name for _t, name in members]:
                members.append((match.group("type").strip(), match.group("name")))
        depth += _braces(line)
        if "{" in line:
            opened = True
        if opened and depth <= 0:
            break
    return members


# ------------------------------------------------------------------ Python

def _py_params(params_text: str) -> List[Param]:
    found = []
    for part in _split_top(params_text):
        head, _sep, default = part.partition("=")
        name_part = head.strip()
        name, _colon, annotation = name_part.partition(":")
        name = name.strip()
        variadic = name.startswith("*")
        name = name.lstrip("*")
        if name in ("self", "cls", ""):
            continue
        found.append(Param(name=name, type=annotation.strip(), default=default.strip(), variadic=variadic))
    return found


# ------------------------------------------------------------------ rendering

def _php_block(sig: Signature, indent: str) -> str:
    out = ["/**", " *"]
    if sig.kind == "class":
        for type_name, name in sig.members:
            out.append(f" * @property {type_name or 'mixed'} ${name}")
    else:
        for param in sig.params:
            spread = "..." if param.variadic else ""
            out.append(f" * @param {param.type or 'mixed'} {spread}{param.name}")
        if sig.returns:
            out.append(f" * @return {sig.returns}")
    out.append(" */")
    return "\n".join(indent + line for line in out)


def _js_block(sig: Signature, indent: str) -> str:
    out = ["/**", " *"]
    if sig.kind == "class":
        for type_name, name in sig.members:
            out.append(f" * @property {{{type_name or '*'}}} {name}")
    else:
        for param in sig.params:
            name = param.name if not param.variadic else "..." + param.name
            out.append(f" * @param {{{param.type or '*'}}} {name}")
        if sig.returns:
            out.append(f" * @returns {{{sig.returns}}}")
    out.append(" */")
    return "\n".join(indent + line for line in out)


def _py_docstring(sig: Signature, indent: str) -> str:
    out = ['"""', ""]
    if sig.kind == "class":
        if sig.members:
            out += ["Attributes:"]
            for type_name, name in sig.members:
                out.append(f"    {name} ({type_name or 'Any'}):")
            out.append("")
    else:
        args = [p for p in sig.params]
        if args:
            out += ["Args:"]
            for param in args:
                star = "*" if param.variadic else ""
                out.append(f"    {star}{param.name} ({param.type or 'Any'}):")
            out.append("")
        if sig.returns:
            out += ["Returns:", f"    {sig.returns}:", ""]
    out.append('"""')
    while out and out[-1] == "":
        out.pop()
    return "\n".join(indent + line if line else "" for line in out)


# ------------------------------------------------------------------ entry point

def _decorators_start(lines: List[str], index: int) -> int:
    while index > 0 and re.match(r"^\s*(@|#\[)", lines[index - 1]):
        index -= 1
    return index


def generate(text: str, line: int, family: str) -> Optional[DocBlock]:
    """The doc comment for the declaration on line ``line`` (or the next few lines), or None."""
    lines = text.split("\n")
    start = max(line - 1, 0)
    for index in range(start, min(start + 6, len(lines))):
        block = _block_for(lines, index, family)
        if block is not None:
            return block
    return None


def _block_for(lines: List[str], index: int, family: str) -> Optional[DocBlock]:
    line = lines[index]
    indent = re.match(r"\s*", line).group(0)
    if family == "php":
        class_match = PHP_CLASS.match(line)
        if class_match:
            members = _php_class_members(lines, index, _php_promoted_in_class(lines, index))
            sig = Signature(kind="class", name=class_match.group(2), members=members)
            return DocBlock(_decorators_start(lines, index) + 1, _php_block(sig, indent))
        match = PHP_FUNCTION.match(line)
        if match:
            sig = _php_signature(lines, index, match, 0)
            if sig is None:
                return None
            if sig.name == "__construct":
                joined = "\n".join(lines[index:index + 12])
                promoted = [p for p in sig.params if p.promoted]
                class_index = _enclosing_class(lines, index)
                if class_index is not None:
                    members = _php_class_members(lines, class_index, promoted)
                    cls = Signature(kind="class", name="", members=members)
                    return DocBlock(_decorators_start(lines, class_index) + 1, _php_block(cls, indent))
            return DocBlock(_decorators_start(lines, index) + 1, _php_block(sig, indent))
        return None
    if family == "js":
        class_match = JS_CLASS.match(line)
        if class_match:
            members = _js_class_members(lines, index, [])
            sig = Signature(kind="class", name=class_match.group(2), members=members)
            return DocBlock(_decorators_start(lines, index) + 1, _js_block(sig, indent))
        for pattern in (JS_FUNCTION, JS_ARROW):
            match = pattern.match(line)
            if match:
                sig = _js_function(lines, index, match)
                return DocBlock(_decorators_start(lines, index) + 1, _js_block(sig, indent)) if sig else None
        method = JS_METHOD.match(line)
        if method and method.group(1) not in JS_NOT_A_METHOD and _is_declaration_line(line, method):
            sig = _js_function(lines, index, method)
            if sig is not None and method.group(1) == "constructor":
                class_index = _enclosing_class(lines, index)
                if class_index is not None:
                    members = _js_class_members(lines, class_index, [p for p in sig.params if p.promoted])
                    cls = Signature(kind="class", name="", members=members)
                    return DocBlock(_decorators_start(lines, class_index) + 1, _js_block(cls, indent))
            return DocBlock(_decorators_start(lines, index) + 1, _js_block(sig, indent)) if sig else None
        return None
    # Python
    class_match = PY_CLASS.match(line)
    if class_match:
        header_end = _header_end(lines, index)
        if header_end is None:
            return None
        members = []
        for body in lines[index + 1:]:
            if body and not body.startswith("    "):
                if body.strip():
                    break
                continue
            annotated = PY_ANNOTATED.match(body)
            if annotated:
                members.append((annotated.group(2), annotated.group(1)))
        sig = Signature(kind="class", name=class_match.group(2), members=members)
        return DocBlock(header_end + 2, _py_docstring(sig, class_match.group(1) + "    "))
    def_match = PY_DEF.match(line)
    if def_match:
        joined = "\n".join(lines[index:index + 12])
        open_char = joined.index("(")
        close = _close_paren(joined, open_char)
        params_text = joined[open_char + 1:close] if close > 0 else ""
        rest = joined[close + 1:] if close > 0 else ""
        returns_match = re.match(r"\s*->\s*([^:]+?)\s*:", rest)
        sig = Signature(kind="function", name=def_match.group(2), params=_py_params(params_text),
                        returns=returns_match.group(1) if returns_match else "")
        header_end = _header_end(lines, index)
        if header_end is None:
            return None
        return DocBlock(header_end + 2, _py_docstring(sig, def_match.group(1) + "    "))
    return None


def _enclosing_class(lines: List[str], index: int) -> Optional[int]:
    """The line of the class declaration whose body contains the line index (by indentation or braces)."""
    depth = 0
    for back in range(index - 1, -1, -1):
        depth -= _braces(lines[back])
        if depth < 0:
            if re.match(r"^\s*(?:(?:export|default|abstract|final|readonly)\s+)*(class|interface|trait|enum)\b",
                        lines[back]):
                return back
            depth = 0
    return None


def _is_declaration_line(line: str, match) -> bool:
    rest = line[match.end():]
    close = _close_paren("(" + rest, 0)
    if close < 0:
        return False
    after = ("(" + rest)[close + 1:]
    return "{" in after or ":" in after or "=>" in after


def _js_function(lines: List[str], index: int, match) -> Optional[Signature]:
    line = lines[index]
    open_index = line.find("(", match.start())
    if open_index < 0:
        return None
    joined = "\n".join(lines[index:index + 12])
    absolute_open = sum(len(part) + 1 for part in lines[index:index]) + open_index
    close = _close_paren(joined, absolute_open)
    if close < 0:
        return None
    params_text = joined[absolute_open + 1:close]
    rest = joined[close + 1:]
    name = match.group(1) if match.groups() else ""
    params = _js_params(params_text)
    return Signature(kind="function", name=name or "", params=params, returns=_js_return(rest))


def _header_end(lines: List[str], index: int) -> Optional[int]:
    """The line index where a Python header ends (the line with the colon after the parameter list)."""
    joined = ""
    for offset, line in enumerate(lines[index:index + 12]):
        joined += line + "\n"
        if re.search(r":\s*(#.*)?$", line):
            return index + offset
    return None
