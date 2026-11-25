"""Syntax highlighting spans computed by our own tokenizers (no external grammar files).

Each language returns ``(style, start, end)`` spans. The GUI turns each style into a text tag
named ``hl-<style>`` using :data:`TAG_STYLES`. Offsets are character offsets in the text.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from . import baredown
from .lexers import ecmascript_lexer, sql_lexer

Span = Tuple[str, int, int]

TAG_STYLES: Dict[str, Dict[str, object]] = {
    "keyword": {"foreground": "#7c3aed", "weight": 700},
    "string": {"foreground": "#15803d"},
    "comment": {"foreground": "#6b7280"},
    "number": {"foreground": "#b45309"},
    "regexp": {"foreground": "#be185d"},
    "operator": {"foreground": "#374151"},
    "engine": {"foreground": "#0e7490", "weight": 700},
    "error": {"background": "#fecaca"},
    "heading": {"foreground": "#1d4ed8", "weight": 800},
    "marker": {"foreground": "#9333ea", "weight": 700},
    "bullet": {"foreground": "#9333ea"},
    "ordered": {"foreground": "#9333ea"},
    "quote": {"foreground": "#4b5563"},
    "rule": {"foreground": "#6b7280"},
    "fence": {"foreground": "#6b7280"},
    "code": {"foreground": "#0f766e", "background": "#f3f4f6"},
    "code-inline": {"foreground": "#0f766e"},
    "bold": {"weight": 700},
    "italic": {"style": "italic"},
    "link": {"foreground": "#0369a1", "underline": True},
}

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
