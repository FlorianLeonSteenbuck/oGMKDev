"""SQL tokenizer following the rule order of Howl's SQL lexer.

Howl describes its lexers as ordered rules (whitespace, keyword, identifier, string, comment,
number, operator, any character) in bundles/basic_modes/lexers/sql.lua. This module keeps that
order and Howl's keyword list, and uses Python regular expressions instead of LPeg.

One addition: the storage engine after ``ENGINE=`` or ``ENGINE`` (a MySQL/MariaDB table option)
gets its own token kind, so ``ENGINE=InnoDB`` is visible in the token stream. The engine names
come from :mod:`ogmkdev.sql`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from ..sql import ENGINES_BY_DIALECT
from .sql_keywords import KEYWORDS

WHITESPACE = "whitespace"
KEYWORD = "keyword"
IDENTIFIER = "identifier"
STRING = "string"
COMMENT = "comment"
NUMBER = "number"
OPERATOR = "operator"
ENGINE = "engine"
OTHER = "other"

_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING = re.compile(r"'(?:[^'\\\n]|\\[^\n])*'?|\"(?:[^\"\\\n]|\\[^\n])*\"?|`(?:[^`\\\n]|\\[^\n])*`?")
_COMMENT = re.compile(r"(?:--|#)[^\n]*|/\*.*?(?:\*/|\Z)", re.DOTALL)
_NUMBER = re.compile(r"(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?")
_OPERATOR = re.compile(r"[(),]")
_ORDERED_RULES = ((STRING, _STRING), (COMMENT, _COMMENT), (NUMBER, _NUMBER), (OPERATOR, _OPERATOR))


@dataclass(frozen=True)
class Token:
    kind: str
    start: int
    end: int


def tokenize(text: str, dialect: Optional[str] = None) -> List[Token]:
    """Tokenize ``text``. The tokens cover the whole input, whitespace included."""
    engines = ENGINES_BY_DIALECT.get(dialect or "mysql", frozenset())
    engine_names = {name.lower() for name in engines}
    tokens: List[Token] = []
    recent: List[str] = []  # the last two significant token texts, lower-cased
    pos = 0
    while pos < len(text):
        kind, end = _next_token(text, pos, engine_names, recent)
        tokens.append(Token(kind, pos, end))
        if kind != WHITESPACE:
            recent = (recent + [text[pos:end].lower()])[-2:]
        pos = end
    return tokens


def _next_token(text: str, pos: int, engine_names, recent: List[str]):
    match = _WHITESPACE.match(text, pos)
    if match:
        return WHITESPACE, match.end()
    match = _WORD.match(text, pos)
    if match:
        word = match.group(0).lower()
        if word in KEYWORDS:
            return KEYWORD, match.end()
        if word in engine_names and _follows_engine(recent):
            return ENGINE, match.end()
        return IDENTIFIER, match.end()
    for kind, pattern in _ORDERED_RULES:
        match = pattern.match(text, pos)
        if match:
            return kind, match.end()
    return OTHER, pos + 1


def _follows_engine(recent: List[str]) -> bool:
    if not recent:
        return False
    if recent[-1] == "engine":
        return True
    return recent[-1] == "=" and len(recent) == 2 and recent[0] == "engine"
