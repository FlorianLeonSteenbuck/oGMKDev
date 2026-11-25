"""ECMAScript tokenizer ported from KDevelop's QML/JavaScript lexer.

Ported from kdevelop/plugins/qmljs/3rdparty/qtcreator-libs/qmljs/parser/qmljslexer.cpp
(``scanToken``, ``scanNumber``, the string escape rules, line terminators and the
automatic-semicolon information) and the token names of qmljs.g.

Known differences from the original, by design of a standalone tokenizer:

* KDevelop's parser decides whether ``/`` starts a regular expression. Here the previous
  significant token decides (after an identifier, number, string, ``)``, ``]`` or ``}``
  a slash is division; otherwise it starts a regular expression).
* Template literals are scanned as one ``string`` token. Substitutions are not parsed.
* The dialect argument is accepted for interface symmetry; the keyword list is ES5 plus the
  ES2015 reserved words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

KEYWORDS = frozenset("""
break case catch class const continue debugger default delete do else enum export extends
false finally for function if import in instanceof new null return super switch this throw
true try typeof var void while with yield let static implements interface package private
protected public
""".split())

PUNCTUATORS = sorted("""
{ } ( ) [ ] . ; , < > <= >= == != === !== + - * % ** ++ -- << >> >>> & | ^ ! ~ && || ? ?. :
= += -= *= %= **= <<= >>= >>>= &= |= ^= => ... / /=
""".split(), key=len, reverse=True)

LINE_TERMINATORS = frozenset("\n\r  ")
IDENTIFIER = re.compile(r"(?:[^\W\d]|\$)[\w$]*")
NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
NON_DIVISION_PUNCTUATORS = frozenset({")", "]", "}", "++", "--"})
REGEX_AFTER_KEYWORD_EXCLUSIONS = frozenset({"this", "null", "true", "false"})


@dataclass(frozen=True)
class Token:
    kind: str                 # identifier | keyword | number | string | regexp | punctuator | comment | error
    start: int
    end: int
    newline_before: bool = False   # a line terminator precedes this token (automatic semicolon rule)
    error: Optional[str] = None


def tokenize(source: str, dialect: Optional[str] = None) -> List[Token]:
    tokens: List[Token] = []
    length = len(source)
    position = 0
    newline = False
    previous: Optional[Token] = None
    while position < length:
        char = source[position]
        if char in LINE_TERMINATORS:
            newline = True
            position += 1
            continue
        if char.isspace() or char == "﻿":
            position += 1
            continue
        if source.startswith("//", position):
            end = position
            while end < length and source[end] not in LINE_TERMINATORS:
                end += 1
            tokens.append(Token("comment", position, end, newline))
            position = end
            continue
        if source.startswith("/*", position):
            close = source.find("*/", position + 2)
            end = length if close < 0 else close + 2
            error = "unterminated comment" if close < 0 else None
            if any(c in LINE_TERMINATORS for c in source[position:end]):
                newline = True
            tokens.append(Token("comment", position, end, newline, error))
            position = end
            continue

        if char in "\"'":
            end, error = _scan_string(source, position)
            token = Token("string", position, end, newline, error)
        elif char == "`":
            end, error = _scan_template(source, position)
            token = Token("string", position, end, newline, error)
        elif char == "/" and _regex_allowed(previous, source):
            end, error = _scan_regexp(source, position)
            token = Token("regexp", position, end, newline, error)
        elif char.isdigit() or (char == "." and position + 1 < length and source[position + 1].isdigit()):
            end = NUMBER.match(source, position).end()
            token = Token("number", position, end, newline)
        elif IDENTIFIER.match(source, position):
            end = IDENTIFIER.match(source, position).end()
            word = source[position:end]
            token = Token("keyword" if word in KEYWORDS else "identifier", position, end, newline)
        else:
            punctuator = next((p for p in PUNCTUATORS if source.startswith(p, position)), None)
            if punctuator == "?." and position + 2 < length and source[position + 2].isdigit():
                punctuator = "?"  # `a?.5:1` is a conditional, not optional chaining
            if punctuator is None:
                token = Token("error", position, position + 1, newline, "unexpected character")
            else:
                token = Token("punctuator", position, position + len(punctuator), newline)
            end = token.end
        tokens.append(token)
        previous = token if token.kind != "comment" else previous
        newline = False
        position = end
    return tokens


def _regex_allowed(previous: Optional[Token], source: str) -> bool:
    if previous is None:
        return True
    text = source[previous.start:previous.end]
    if previous.kind in ("identifier", "number", "string", "regexp"):
        return False
    if previous.kind == "keyword":
        return text not in REGEX_AFTER_KEYWORD_EXCLUSIONS
    if previous.kind == "punctuator":
        return text not in NON_DIVISION_PUNCTUATORS
    return True


def _scan_string(source: str, position: int):
    quote = source[position]
    index = position + 1
    length = len(source)
    while index < length:
        char = source[index]
        if char == quote:
            return index + 1, None
        if char in "\r\n":
            return index, "unterminated string literal"
        if char == "\\":
            index += 3 if source[index + 1:index + 3] == "\r\n" else 2
            continue
        index += 1
    return length, "unterminated string literal"


def _scan_template(source: str, position: int):
    index = position + 1
    length = len(source)
    while index < length:
        char = source[index]
        if char == "`":
            return index + 1, None
        index += 2 if char == "\\" else 1
    return length, "unterminated template literal"


def _scan_regexp(source: str, position: int):
    index = position + 1
    length = len(source)
    in_class = False
    while index < length:
        char = source[index]
        if char in LINE_TERMINATORS:
            return index, "unterminated regular expression"
        if char == "\\":
            index += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            index += 1
            while index < length and source[index].isalpha():
                index += 1  # flags
            return index, None
        index += 1
    return length, "unterminated regular expression"


def problems(source: str) -> List[tuple]:
    """(line, column, message) for every token with an error."""
    result = []
    for token in tokenize(source):
        if token.error:
            line = source.count("\n", 0, token.start) + 1
            column = token.start - (source.rfind("\n", 0, token.start) + 1) + 1
            result.append((line, column, token.error))
    return result
