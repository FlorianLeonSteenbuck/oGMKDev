"""EditorConfig support (https://editorconfig.org) - the only IDE configuration format.

Implements the parts of the specification the editor needs:

* ``.editorconfig`` discovery from the file's directory up to the first file that
  declares ``root = true`` (or the filesystem root);
* section globs: ``*``, ``**``, ``?``, ``[abc]``, ``[!abc]``, ``{a,b}``, ``{1..3}``
  and ``\\`` escapes. A glob without a ``/`` matches at any depth below its
  ``.editorconfig``; a glob with a ``/`` is relative to it;
* precedence: nearer files win over farther ones, later sections win over earlier
  ones, and ``key = unset`` removes a property;
* normalisation of the core properties into :class:`EditorSettings`.

Language scoping (``ogmkdev_language`` / ``ogmkdev_dialect``) is read from the same
files, see :mod:`ogmkdev.languages`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Mapping, Optional, Tuple

CONFIG_FILE_NAME = ".editorconfig"
UNSET = "unset"
NUMERIC_RANGE_LIMIT = 10_000

INDENT_STYLES = frozenset({"tab", "space"})
END_OF_LINE_VALUES = frozenset({"lf", "cr", "crlf"})
CHARSETS = frozenset({"latin1", "utf-8", "utf-8-bom", "utf-16be", "utf-16le"})
CORE_KEYS = frozenset({
    "indent_style", "indent_size", "tab_width", "end_of_line", "charset",
    "trim_trailing_whitespace", "insert_final_newline", "max_line_length",
})


# --------------------------------------------------------------------------- globs

def _find_closing_brace(glob: str, start: int) -> int:
    depth = 0
    i = start
    while i < len(glob):
        c = glob[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_top_level(inner: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    i = 0
    while i < len(inner):
        c = inner[i]
        if c == "\\" and i + 1 < len(inner):
            current.append(inner[i:i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(c)
        i += 1
    parts.append("".join(current))
    return parts


def _class_end(glob: str, start: int) -> int:
    """Index of the ``]`` closing the bracket expression opened at ``start``, or -1."""
    j = start + 1
    if j < len(glob) and glob[j] == "!":
        j += 1
    if j < len(glob) and glob[j] == "]":  # a leading ] is a literal member
        j += 1
    while j < len(glob):
        if glob[j] == "\\":
            j += 2
            continue
        if glob[j] == "]":
            return j
        j += 1
    return -1


def _char_class(body: str) -> str:
    negate = body.startswith("!")
    if negate:
        body = body[1:]
    members: List[str] = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            members.append("\\" + body[i + 1])
            i += 2
            continue
        members.append("\\" + c if c in "[]^\\" else c)
        i += 1
    return "[" + ("^" if negate else "") + "".join(members) + "]"


def glob_to_regex(glob: str) -> str:
    """Translate one EditorConfig glob (without anchors) into regex source."""
    out: List[str] = []
    i, n = 0, len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            if glob.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
            elif glob.startswith("**", i):
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            end = _class_end(glob, i)
            if end < 0:
                out.append(re.escape(c))
                i += 1
            else:
                out.append(_char_class(glob[i + 1:end]))
                i = end + 1
        elif c == "{":
            close = _find_closing_brace(glob, i)
            if close < 0:
                out.append(re.escape(c))
                i += 1
                continue
            inner = glob[i + 1:close]
            numeric = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", inner)
            if numeric:
                lo, hi = sorted((int(numeric.group(1)), int(numeric.group(2))))
                if hi - lo <= NUMERIC_RANGE_LIMIT:
                    out.append("(?:" + "|".join(str(v) for v in range(lo, hi + 1)) + ")")
                else:
                    out.append(re.escape(glob[i:close + 1]))
            else:
                parts = _split_top_level(inner)
                if len(parts) == 1:  # no comma: braces are literal text
                    out.append(re.escape("{") + glob_to_regex(inner) + re.escape("}"))
                else:
                    out.append("(?:" + "|".join(glob_to_regex(p) for p in parts) + ")")
            i = close + 1
        elif c == "\\" and i + 1 < n:
            out.append(re.escape(glob[i + 1]))
            i += 2
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _has_path_separator(glob: str) -> bool:
    return "/" in re.sub(r"\[[^\]]*\]", "", glob)


def compile_section_glob(glob: str) -> "re.Pattern[str]":
    """Compile a section name into a pattern matched against a '/'-separated relative path."""
    if _has_path_separator(glob):
        body = glob_to_regex(glob[1:] if glob.startswith("/") else glob)
    else:
        body = "(?:.*/)?" + glob_to_regex(glob)
    return re.compile("^" + body + "$")


# --------------------------------------------------------------------- file model

@dataclass(frozen=True)
class Section:
    glob: str
    regex: "re.Pattern[str]"
    properties: Mapping[str, str]


@dataclass(frozen=True)
class EditorConfigFile:
    path: str
    root: bool
    sections: Tuple[Section, ...]


def parse(text: str, path: str = CONFIG_FILE_NAME) -> EditorConfigFile:
    root = False
    raw: List[Tuple[str, Dict[str, str]]] = []
    current: Optional[Dict[str, str]] = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {}
            raw.append((line[1:-1], current))
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip().lower()
        if current is None:
            if key == "root":
                root = value == "true"
            continue
        current[key] = value
    sections = tuple(Section(glob, compile_section_glob(glob), props) for glob, props in raw)
    return EditorConfigFile(path=path, root=root, sections=sections)


@lru_cache(maxsize=512)
def _load_cached(path: str, mtime_ns: int) -> EditorConfigFile:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse(handle.read(), path)


def load(path: str) -> EditorConfigFile:
    absolute = os.path.abspath(path)
    return _load_cached(absolute, os.stat(absolute).st_mtime_ns)


def find_config_files(file_path: str) -> List[EditorConfigFile]:
    """All applicable ``.editorconfig`` files, nearest first."""
    directory = os.path.dirname(os.path.abspath(file_path))
    found: List[EditorConfigFile] = []
    while True:
        candidate = os.path.join(directory, CONFIG_FILE_NAME)
        if os.path.isfile(candidate):
            config = load(candidate)
            found.append(config)
            if config.root:
                break
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return found


def effective_properties(file_path: str) -> Dict[str, str]:
    """Raw merged property map for ``file_path`` (keys and values lower-cased)."""
    absolute = os.path.abspath(file_path)
    props: Dict[str, str] = {}
    for config in reversed(find_config_files(absolute)):  # farthest first, nearest wins
        base = os.path.dirname(config.path)
        relative = os.path.relpath(absolute, base).replace(os.sep, "/")
        for section in config.sections:
            if section.regex.match(relative):
                for key, value in section.properties.items():
                    if value == UNSET:
                        props.pop(key, None)
                    else:
                        props[key] = value
    return props


# ------------------------------------------------------------------- settings

@dataclass(frozen=True)
class EditorSettings:
    indent_style: Optional[str] = None          # "tab" | "space"
    indent_size: Optional[int] = None           # columns per indent level
    tab_width: Optional[int] = None             # display width of a tab character
    end_of_line: Optional[str] = None           # "lf" | "cr" | "crlf"
    charset: Optional[str] = None
    trim_trailing_whitespace: Optional[bool] = None
    insert_final_newline: Optional[bool] = None
    max_line_length: Optional[int] = None       # None when unset or "off"
    custom: Mapping[str, str] = field(default_factory=dict)  # e.g. ogmkdev_* keys


def _choice(value: Optional[str], allowed: frozenset) -> Optional[str]:
    return value if value in allowed else None


def _int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number >= 0 else None


def _bool(value: Optional[str]) -> Optional[bool]:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def settings_from_properties(props: Mapping[str, str]) -> EditorSettings:
    indent_style = _choice(props.get("indent_style"), INDENT_STYLES)
    size_raw = props.get("indent_size")
    if size_raw is None and indent_style == "tab":
        size_raw = "tab"  # spec: tab indentation without an explicit size uses tab_width
    tab_width = _int(props.get("tab_width"))
    indent_size: Optional[int]
    if size_raw == "tab":
        indent_size = tab_width
    else:
        indent_size = _int(size_raw)
    if tab_width is None and indent_size is not None:
        tab_width = indent_size
    max_raw = props.get("max_line_length")
    max_line_length = None if max_raw in (None, "off") else _int(max_raw)
    return EditorSettings(
        indent_style=indent_style,
        indent_size=indent_size,
        tab_width=tab_width,
        end_of_line=_choice(props.get("end_of_line"), END_OF_LINE_VALUES),
        charset=_choice(props.get("charset"), CHARSETS),
        trim_trailing_whitespace=_bool(props.get("trim_trailing_whitespace")),
        insert_final_newline=_bool(props.get("insert_final_newline")),
        max_line_length=max_line_length,
        custom={k: v for k, v in props.items() if k not in CORE_KEYS},
    )


def settings_for(file_path: str) -> EditorSettings:
    return settings_from_properties(effective_properties(file_path))
