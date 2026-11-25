"""TODO words inside comments, found in the files of the workspace (no GUI code here).

Keywords come from the setting ogmkdev_todo_keywords (``FIXME:1,TODO:3``: the number is the
priority, 1 the most urgent). Comments are found per language: line comments (``//``, ``#``,
``--``) and block comments (``/* */``, ``<!-- -->``); strings are skipped.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from . import languages

DEFAULT_KEYWORDS = "FIXME:1,XXX:2,HACK:2,TODO:3,NOTE:5"

# (line comment markers, block comment (start, end)) per language
_C_LIKE = (("//",), ("/*", "*/"))
COMMENT_RULES: Dict[str, Tuple[Tuple[str, ...], Optional[Tuple[str, str]]]] = {
    "php": (("//", "#"), ("/*", "*/")),
    "ecmascript": _C_LIKE,
    "typescript": _C_LIKE,
    "tsx": _C_LIKE,
    "jsx": _C_LIKE,
    "css": ((), ("/*", "*/")),
    "python": (("#",), None),
    "pypy": (("#",), None),
    "sql": (("--",), ("/*", "*/")),
    "html": ((), ("<!--", "-->")),
    "markdown": ((), ("<!--", "-->")),
    "baredown": ((), ("<!--", "-->")),
}


@dataclass(frozen=True)
class Todo:
    path: str
    line: int
    keyword: str
    priority: int
    text: str


def parse_keywords(text: str) -> List[Tuple[str, int]]:
    """``FIXME:1,TODO:3`` to [("FIXME", 1), ("TODO", 3)]; entries that do not parse are skipped."""
    keywords = []
    for entry in re.split(r"[,\s]+", text or ""):
        match = re.fullmatch(r"(\w+):(\d+)", entry)
        if match:
            keywords.append((match.group(1), int(match.group(2))))
    return keywords


def comment_lines(text: str, line_markers: Sequence[str], block: Optional[Tuple[str, str]]) -> List[Tuple[int, str]]:
    """(line number, comment text on that line) for every comment in ``text``."""
    found: List[Tuple[int, str]] = []
    line = 1
    index = 0
    end_of_text = len(text)
    quote: Optional[str] = None
    while index < end_of_text:
        char = text[index]
        if char == "\n":
            line += 1
            index += 1
            continue
        if quote:
            if char == "\\" and index + 1 < end_of_text and text[index + 1] != "\n":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            index += 1
            continue
        if block and text.startswith(block[0], index):
            close = text.find(block[1], index + len(block[0]))
            stop = end_of_text if close < 0 else close + len(block[1])
            for offset, piece in enumerate(text[index:stop].split("\n")):
                found.append((line + offset, piece))
            line += text[index:stop].count("\n")
            index = stop
            continue
        marker = next((m for m in line_markers if text.startswith(m, index)), None)
        if marker:
            stop = text.find("\n", index)
            stop = end_of_text if stop < 0 else stop
            found.append((line, text[index:stop]))
            index = stop
            continue
        index += 1
    return found


def todos_in_text(path: str, text: str, keywords: Sequence[Tuple[str, int]], language: Optional[str] = None) -> List[Todo]:
    language = language or languages.detect(path).language
    rules = COMMENT_RULES.get(language)
    if not rules or not keywords:
        return []
    markers, block = rules
    priorities = dict(keywords)
    pattern = re.compile(r"\b(" + "|".join(re.escape(word) for word, _ in keywords) + r")\b")
    result: List[Todo] = []
    for line, comment in comment_lines(text, markers, block):
        for match in pattern.finditer(comment):
            word = match.group(1)
            result.append(Todo(path, line, word, priorities[word], comment[match.start():].strip()[:200]))
    return result


def todos_in_file(path: str, keywords: Sequence[Tuple[str, int]]) -> List[Todo]:
    try:
        if os.path.getsize(path) > 2_000_000:
            return []
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return []
    return todos_in_text(path, text, keywords)


def todos_in_files(paths: Iterable[str], keywords: Sequence[Tuple[str, int]]) -> List[Todo]:
    found: List[Todo] = []
    for path in paths:
        found.extend(todos_in_file(path, keywords))
    return sorted(found, key=lambda todo: (todo.priority, todo.path, todo.line))
