"""TypeScript tokens for the highlighting.

The tokens are the ECMAScript tokens of :mod:`ogmkdev.lexers.ecmascript_lexer`, with the words that
TypeScript adds to the language (``type``, ``namespace``, ``readonly``, ``keyof``...) marked as
keywords and the predefined type names (``string``, ``number``...) as types. Error tokens are left
out: JSX text, which the ECMAScript tokens cannot read, would otherwise show as errors.
"""

from __future__ import annotations

from dataclasses import replace
from typing import List

from . import ecmascript_lexer as E

TYPESCRIPT_KEYWORDS = frozenset("""
abstract as asserts declare global infer is keyof module namespace override readonly satisfies
type unique
""".split())
PREDEFINED_TYPES = frozenset("""
any unknown number string boolean symbol bigint object never undefined
""".split())


def tokenize(source: str) -> List[E.Token]:
    """The TypeScript tokens of ``source``, comments included."""
    result: List[E.Token] = []
    for token in E.tokenize(source):
        if token.kind == "error":
            continue
        if token.kind == "identifier":
            word = source[token.start:token.end]
            if word in TYPESCRIPT_KEYWORDS:
                token = replace(token, kind="keyword")
            elif word in PREDEFINED_TYPES:
                token = replace(token, kind="type")
        result.append(token)
    return result
