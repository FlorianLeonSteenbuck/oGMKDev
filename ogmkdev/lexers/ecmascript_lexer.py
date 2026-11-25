"""ECMAScript tokenizer ported from KDevelop's QML/JavaScript lexer.

Ported from kdevelop/plugins/qmljs/3rdparty/qtcreator-libs/qmljs/parser/qmljslexer.cpp
(``scanToken``, ``scanNumber``, the string escape rules, line terminators and the
automatic-semicolon information) and the token names of qmljs.g.

Known differences from the original, by design of a standalone tokenizer:

* KDevelop's parser decides whether ``/`` starts a regular expression. :func:`tokenize` decides
  from the previous significant token (after an identifier, number, string, ``)``, ``]`` or ``}``
  a slash is division; otherwise it starts a regular expression). A parser decides itself and
  passes ``regexp_allowed`` to :func:`scan_token`.
* :func:`tokenize` scans a template literal as one ``string`` token. A parser passes
  ``substitutions=True`` to :func:`scan_token` and gets the parts of the template around its
  substitutions (kinds ``template-open`` and ``template``); :func:`scan_template_continuation`
  scans the part that follows a substitution.
* The keyword list is ES5 plus the ES2015 reserved words; the dialect argument is accepted for
  interface symmetry.

Since ECMAScript 2022: ``??``, ``??=``, ``||=`` and ``&&=``, numeric separators and BigInt
literals, unicode escapes in identifiers, private names (``#name``, kind ``private-name``) and a
hashbang line (``#!`` at the start of the file, a comment).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

KEYWORDS = frozenset("""
break case catch class const continue debugger default delete do else enum export extends
false finally for function if import in instanceof new null return super switch this throw
true try typeof var void while with yield let static implements interface package private
protected public
""".split())

PUNCTUATORS = sorted("""
{ } ( ) [ ] . ; , < > <= >= == != === !== + - * % ** ++ -- << >> >>> & | ^ ! ~ && || ?? ?. ?
: = += -= *= %= **= <<= >>= >>>= &= |= ^= &&= ||= ??= => ... / /=
""".split(), key=len, reverse=True)

LINE_TERMINATORS = frozenset("\n\r  ")
IDENTIFIER = re.compile(r"(?:[^\W\d]|\$|\\u[0-9a-fA-F]{4}|\\u\{[0-9a-fA-F]+\})"
                        r"(?:[\w$]|\\u[0-9a-fA-F]{4}|\\u\{[0-9a-fA-F]+\})*")
NUMBER = re.compile(r"0[xX][0-9a-fA-F_]+n?|0[oO][0-7_]+n?|0[bB][01_]+n?"
                    r"|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d[\d_]*)?n?")
NON_DIVISION_PUNCTUATORS = frozenset({")", "]", "}", "++", "--"})
REGEX_AFTER_KEYWORD_EXCLUSIONS = frozenset({"this", "null", "true", "false"})

_PUNCTUATORS_BY_START: Dict[str, List[str]] = {}
for _punctuator in PUNCTUATORS:
    _PUNCTUATORS_BY_START.setdefault(_punctuator[0], []).append(_punctuator)


@dataclass(frozen=True)
class Token:
    kind: str                 # identifier | keyword | number | string | regexp | punctuator | comment | error
                              # | private-name | template | template-open | eof (see scan_token)
    start: int
    end: int
    newline_before: bool = False   # a line terminator precedes this token (automatic semicolon rule)
    error: Optional[str] = None


def tokenize(source: str, dialect: Optional[str] = None) -> List[Token]:
    """All tokens of ``source``, comments included (kind ``comment``)."""
    tokens: List[Token] = []
    previous: Optional[Token] = None
    position = 0
    while True:
        token = scan_token(source, position, regexp_allowed=_regex_allowed(previous, source))
        if token.kind == "eof":
            return tokens
        tokens.append(token)
        if token.kind != "comment":
            previous = token
        position = token.end


def scan_token(source: str, position: int, regexp_allowed: bool = False,
               substitutions: bool = False) -> Token:
    """The token at or after ``position``.

    Whitespace is skipped; the token records whether a line terminator came before it (a block
    comment that holds a line terminator counts). Comments are tokens of kind ``comment`` so that a
    caller can skip them. The end of the text is a token of kind ``eof``. A ``/`` is a regular
    expression only when ``regexp_allowed`` is true. With ``substitutions`` a template literal is
    scanned up to its first ``${`` (kind ``template-open``) or to its closing backtick (kind
    ``template``).
    """
    length = len(source)
    newline = False
    if position == 0 and source.startswith("#!"):
        return Token("comment", 0, _line_end(source, 0), False)
    while position < length:
        char = source[position]
        if char in LINE_TERMINATORS:
            newline = True
        elif not (char.isspace() or char == "﻿"):
            break
        position += 1
    if position >= length:
        return Token("eof", length, length, newline)

    char = source[position]
    if source.startswith("//", position):
        return Token("comment", position, _line_end(source, position), newline)
    if source.startswith("/*", position):
        close = source.find("*/", position + 2)
        if close < 0:
            return Token("comment", position, length, newline, "unterminated comment")
        breaks = newline or any(c in LINE_TERMINATORS for c in source[position:close + 2])
        return Token("comment", position, close + 2, breaks)
    if char in "\"'":
        end, error = _scan_string(source, position)
        return Token("string", position, end, newline, error)
    if char == "`":
        if substitutions:
            end, opens, error = scan_template_chunk(source, position + 1)
            return Token("template-open" if opens else "template", position, end, newline, error)
        end, error = _scan_template(source, position)
        return Token("string", position, end, newline, error)
    if char == "/" and regexp_allowed:
        end, error = _scan_regexp(source, position)
        return Token("regexp", position, end, newline, error)
    if char.isdigit() or (char == "." and position + 1 < length and source[position + 1].isdigit()):
        return Token("number", position, NUMBER.match(source, position).end(), newline)
    if char == "#":
        name = IDENTIFIER.match(source, position + 1)
        if name:
            return Token("private-name", position, name.end(), newline)
    word = IDENTIFIER.match(source, position)
    if word:
        text = word.group(0)
        return Token("keyword" if text in KEYWORDS else "identifier", position, word.end(), newline)
    punctuator = _punctuator_at(source, position)
    if punctuator is None:
        return Token("error", position, position + 1, newline, "unexpected character")
    return Token("punctuator", position, position + len(punctuator), newline)


def scan_template_chunk(source: str, position: int) -> Tuple[int, bool, Optional[str]]:
    """Template text from ``position``, just after a backtick or after the ``}`` that closes a
    substitution. Returns ``(end, opens_substitution, error)``: the end lies after the closing
    backtick, or after ``${`` when a substitution follows."""
    index = position
    length = len(source)
    while index < length:
        char = source[index]
        if char == "`":
            return index + 1, False, None
        if char == "$" and source.startswith("{", index + 1):
            return index + 2, True, None
        index += 2 if char == "\\" else 1
    return length, False, "unterminated template literal"


def scan_template_continuation(source: str, brace: int) -> Token:
    """The template part that follows the substitution whose closing brace is at ``brace``."""
    end, opens, error = scan_template_chunk(source, brace + 1)
    return Token("template-open" if opens else "template", brace, end, False, error)


def _line_end(source: str, position: int) -> int:
    end = position
    while end < len(source) and source[end] not in LINE_TERMINATORS:
        end += 1
    return end


def _punctuator_at(source: str, position: int) -> Optional[str]:
    for punctuator in _PUNCTUATORS_BY_START.get(source[position], ()):
        if source.startswith(punctuator, position):
            if punctuator == "?." and position + 2 < len(source) and source[position + 2].isdigit():
                return "?"  # `a?.5:1` is a conditional, not optional chaining
            return punctuator
    return None


def _regex_allowed(previous: Optional[Token], source: str) -> bool:
    if previous is None:
        return True
    text = source[previous.start:previous.end]
    if previous.kind in ("identifier", "number", "string", "regexp", "private-name"):
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
