"""PHP tokenizer for PHP 8.0 to 8.6 syntax, used for highlighting and feature checks.

Covers inline HTML and the open and close tags, comments and doc comments, attributes (``#[``),
variables, names with namespaces (``\\Foo\\Bar``), keywords (including the PHP 8 keywords ``match``,
``enum``, ``readonly``, ``never``, ``mixed``), numbers with ``_`` separators and ``0o``/``0b``/``0x``
prefixes, single, double and backtick strings, heredoc and nowdoc (scanned with the rules of
:mod:`ogmkdev.heredoc`), casts, and the operators ``?->`` (PHP 8.0) and ``|>`` (PHP 8.5).
Placeholders ``?`` and ``...`` are ordinary operators here; :mod:`ogmkdev.php_features` decides
what they mean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .. import heredoc

KEYWORDS = frozenset("""
abstract and array as break callable case catch class clone const continue declare default die do
echo else elseif empty enddeclare endfor endforeach endif endswitch endwhile enum eval exit extends
final finally fn for foreach function global goto if implements include include_once instanceof
insteadof interface isset list match namespace new or print private protected public readonly
require require_once return static switch throw trait try unset use var while xor yield
__halt_compiler __class__ __dir__ __file__ __function__ __line__ __method__ __namespace__ __trait__
int float string bool void mixed never null false true iterable object self parent
""".split())

OPERATORS = sorted("""
<<= >>= **= ... <=> === !== ??= ?-> |> :: -> => ++ -- && || ?? == != <> <= >= += -= *= /= .= %= &= |= ^=
<< >> **
""".split(), key=len, reverse=True)
SINGLE_OPERATORS = frozenset("+-*/%=<>!.&|^~?:;,()[]{}@$\\")
CAST = re.compile(r"\(\s*(int|integer|bool|boolean|float|double|real|string|array|object|unset|binary)\s*\)",
                  re.IGNORECASE)
OPEN_TAG = re.compile(r"<\?(?:php(?![A-Za-z0-9_])|=)?", re.IGNORECASE)
NUMBER = re.compile(r"0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|"
                    r"\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d[\d_]*)?|\.\d[\d_]*(?:[eE][+-]?\d[\d_]*)?")
_IDENT = r"[A-Za-z_\x80-\U0010ffff][A-Za-z0-9_\x80-\U0010ffff]*"
NAME = re.compile(rf"\\?{_IDENT}(?:\\{_IDENT})*")
VARIABLE = re.compile(rf"\${_IDENT}")


@dataclass(frozen=True)
class Token:
    kind: str     # html | open | close | comment | doc | attr | variable | name | keyword | number |
                  # string | heredoc | nowdoc | cast | operator | error
    start: int
    end: int


def tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    length = len(source)
    position = 0
    in_code = False
    while position < length:
        if not in_code:
            match = OPEN_TAG.search(source, position)
            html_end = match.start() if match else length
            if html_end > position:
                tokens.append(Token("html", position, html_end))
            if not match:
                break
            tokens.append(Token("open", match.start(), match.end()))
            position = match.end()
            in_code = True
            continue
        position = _code_token(source, position, tokens)
        if position is None:
            break
        if source.startswith("?>", tokens[-1].start) and tokens[-1].kind == "close":
            in_code = False
    return tokens


def _code_token(source: str, position: int, tokens: List[Token]):
    length = len(source)
    char = source[position]
    if char.isspace():
        return position + 1
    if source.startswith("?>", position):
        end = position + 2
        if source[end:end + 1] == "\n":
            end += 1
        tokens.append(Token("close", position, end))
        return end
    if char == "#" and source.startswith("#[", position):
        tokens.append(Token("attr", position, position + 2))
        return position + 2
    if char == "#" or source.startswith("//", position):
        end = position
        while end < length and source[end] != "\n" and not source.startswith("?>", end):
            end += 1
        tokens.append(Token("comment", position, end))
        return end
    if source.startswith("/**", position) and not source.startswith("/**/", position):
        close = source.find("*/", position + 3)
        end = length if close < 0 else close + 2
        tokens.append(Token("doc", position, end))
        return end
    if source.startswith("/*", position):
        close = source.find("*/", position + 2)
        end = length if close < 0 else close + 2
        tokens.append(Token("comment", position, end))
        return end
    if char == "<" and source.startswith("<<<", position):
        match = heredoc._OPENER.match(source, position)
        if match:
            span, error, end = heredoc._read_heredoc(source, position, match)
            if error is not None:
                tokens.append(Token("error", position, end))
            else:
                tokens.append(Token("nowdoc" if span.kind == "nowdoc" else "heredoc", position, end))
            return end
    if char in "'\"`":
        end = _scan_quoted(source, position)
        tokens.append(Token("string", position, end))
        return end
    if char == "$" and VARIABLE.match(source, position):
        end = VARIABLE.match(source, position).end()
        tokens.append(Token("variable", position, end))
        return end
    if char.isdigit() or (char == "." and position + 1 < length and source[position + 1].isdigit()):
        end = NUMBER.match(source, position).end()
        tokens.append(Token("number", position, end))
        return end
    if char == "(":
        cast = CAST.match(source, position)
        if cast:
            tokens.append(Token("cast", position, cast.end()))
            return cast.end()
    match = NAME.match(source, position)
    if match and (char.isalpha() or char in "_\\" or ord(char) > 127):
        end = match.end()
        word = source[position:end]
        kind = "keyword" if "\\" not in word and word.lower() in KEYWORDS else "name"
        tokens.append(Token(kind, position, end))
        return end
    for operator in OPERATORS:
        if source.startswith(operator, position):
            tokens.append(Token("operator", position, position + len(operator)))
            return position + len(operator)
    if char in SINGLE_OPERATORS:
        tokens.append(Token("operator", position, position + 1))
        return position + 1
    tokens.append(Token("error", position, position + 1))
    return position + 1


def _scan_quoted(source: str, position: int) -> int:
    quote = source[position]
    index = position + 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return len(source)
