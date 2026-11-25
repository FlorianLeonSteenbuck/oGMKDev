"""Syntax highlighting spans computed by our own tokenizers (no external grammar files).

Each language returns ``(style, start, end)`` spans. The GUI turns each style into a text tag
named ``hl-<style>``; the colors come from :mod:`ogmkdev.theme`. Offsets are character offsets in the text.
"""

from __future__ import annotations

from typing import List, Tuple

from . import baredown
from .lexers import ecmascript_lexer, sql_lexer

Span = Tuple[str, int, int]

_ECMASCRIPT_STYLE = {"keyword": "keyword", "string": "string", "comment": "comment", "number": "number",
                     "regexp": "regexp", "punctuator": "operator", "error": "error"}
_SQL_STYLE = {"keyword": "keyword", "string": "string", "comment": "comment", "number": "number",
              "engine": "engine", "operator": "operator"}


def spans(language: str, source: str) -> List[Span]:
    if language == "ecmascript":
        return [(_ECMASCRIPT_STYLE[t.kind], t.start, t.end)
                for t in ecmascript_lexer.tokenize(source) if t.kind in _ECMASCRIPT_STYLE]
    if language == "baredown":
        return [(t.kind, t.start, t.end) for t in baredown.tokenize(source)]
    if language == "sql":
        return [(_SQL_STYLE[t.kind], t.start, t.end)
                for t in sql_lexer.tokenize(source) if t.kind in _SQL_STYLE]
    return []
