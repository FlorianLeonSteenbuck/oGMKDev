"""ECMAScript parser: the LALR driver of KDevelop's QML/JavaScript parser, in Python.

The tables are in :mod:`ogmkdev.parsers.ecmascript_tables`, generated from KDevelop's QLALR output
by ``tools/generate_ecmascript_tables.py``. The driver follows the loop of
``kdevelop/plugins/qmljs/.../qmljsparser.cpp``:

* shift, reduce and accept through ``t_action`` / ``nt_action``;
* a regular expression literal is decided by the grammar: rules 96 and 97 reduce a slash that
  appears where a primary expression is expected, and rescan the literal from the slash;
* automatic semicolon insertion when the grammar cannot continue: before a token that begins a
  new line, before ``}``, or at end of input (KDevelop's ``canInsertAutomaticSemicolon``);
* ``return``, ``break``, ``continue`` and ``throw`` followed by a line break end the statement.

The reductions build a concrete tree of :class:`Node` (non-terminal number and rule number) and
:class:`Leaf` (token). No semantic actions are run; an AST can be built on top of this tree.

Limits: the first syntax error stops the parse (KDevelop's error recovery is not ported). The
grammar is ES5 plus the QML words, which are identifiers in JavaScript mode here. ES2015 syntax
that the grammar lacks (arrow functions, template substitutions, classes, modules) is reported as
a syntax error. Postfix ``++`` and ``--`` after a line break are restricted as in ECMAScript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union

from ..lexers import ecmascript_lexer as L
from . import ecmascript_tables as T

C = T.CONSTANTS
EOF_SYMBOL = 0
ACCEPT_STATE = C["ACCEPT_STATE"]
TERMINAL_COUNT = C["TERMINAL_COUNT"]
GOTO_INDEX_OFFSET = C["GOTO_INDEX_OFFSET"]
GOTO_INFO_OFFSET = C["GOTO_INFO_OFFSET"]
GOTO_CHECK_OFFSET = C["GOTO_CHECK_OFFSET"]
ASI_TERMINAL = C["T_AUTOMATIC_SEMICOLON"]
COMPATIBILITY_TERMINAL = C["T_COMPATIBILITY_SEMICOLON"]

SPELL_IDS = {}
for _index, _spelling in enumerate(T.SPELL):
    if _spelling is not None and _spelling not in SPELL_IDS:
        SPELL_IDS[_spelling] = _index
SEMICOLON_TERMINAL = SPELL_IDS[";"]
IDENTIFIER_TERMINAL = SPELL_IDS["identifier"]
NUMBER_TERMINAL = SPELL_IDS["numeric literal"]
STRING_TERMINAL = SPELL_IDS["string literal"]
REGEXP_TERMINAL = -2  # not a grammar terminal: a regular expression literal leaf

# Words the grammar spells as tokens but that are identifiers in JavaScript mode.
JAVASCRIPT_IDENTIFIERS = frozenset({"as", "on", "get", "set", "property", "signal", "readonly",
                                    "pragma", "import"})
RESTRICTED_KEYWORDS = frozenset({"continue", "break", "return", "throw"})
POSTFIX_OPERATORS = frozenset({"++", "--"})
EXPRESSION_END_TEXT = frozenset({")", "]", "this", "null", "true", "false"})


class ParseError(Exception):
    def __init__(self, line: int, column: int, message: str) -> None:
        super().__init__(f"{line}:{column}: {message}")
        self.line = line
        self.column = column
        self.message = message


@dataclass
class Leaf:
    token: L.Token
    terminal: int
    text: str

    @property
    def start(self) -> int:
        return self.token.start

    @property
    def end(self) -> int:
        return self.token.end


@dataclass
class Node:
    symbol: int                       # non-terminal number (lhs of the rule)
    rule: int
    children: List[Union["Node", Leaf]] = field(default_factory=list)

    @property
    def start(self) -> int:
        return self.children[0].start if self.children else 0

    @property
    def end(self) -> int:
        return self.children[-1].end if self.children else 0

    def leaves(self):
        for child in self.children:
            if isinstance(child, Leaf):
                yield child
            else:
                yield from child.leaves()


def _position(source: str, offset: int) -> Tuple[int, int]:
    line = source.count("\n", 0, offset) + 1
    column = offset - (source.rfind("\n", 0, offset) + 1) + 1
    return line, column


def _can_insert_asi(token: L.Token, source: str) -> bool:
    return token.kind == "eof" or source[token.start:token.end] == "}" or token.newline_before


class _Scanner:
    """Lexer that scans one token at a time, so the parser can rescan regular expressions."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.restricted = False     # the previous token was a restricted keyword

    def reset(self, position: int) -> None:
        self.pos = position
        self.restricted = False

    def next(self) -> L.Token:
        source = self.source
        length = len(source)
        newline = False
        while True:
            if self.pos >= length:
                return L.Token("eof", length, length, newline)
            char = source[self.pos]
            if char in L.LINE_TERMINATORS:
                newline = True
                if self.restricted:
                    self.restricted = False
                    return L.Token("virtual-semicolon", self.pos, self.pos, True)
                self.pos += 1
                continue
            if char.isspace() or char == "﻿":
                self.pos += 1
                continue
            if source.startswith("//", self.pos):
                end = self.pos
                while end < length and source[end] not in L.LINE_TERMINATORS:
                    end += 1
                self.pos = end
                continue
            if source.startswith("/*", self.pos):
                close = source.find("*/", self.pos + 2)
                if close < 0:
                    return L.Token("error", self.pos, length, newline, "unterminated comment")
                end = close + 2
                if any(c in L.LINE_TERMINATORS for c in source[self.pos:end]):
                    newline = True
                    if self.restricted:
                        self.restricted = False
                        self.pos = end
                        return L.Token("virtual-semicolon", end, end, True)
                self.pos = end
                continue
            break
        start = self.pos
        token = self._scan_word(start, newline)
        text = source[start:token.end]
        if token.kind == "punctuator" and text in POSTFIX_OPERATORS and newline \
                and self._follows_expression(start):
            # ECMAScript restricted production: `a\n++b` is `a; ++b`
            return L.Token("virtual-semicolon", start, start, True)
        self.restricted = token.kind == "keyword" and text in RESTRICTED_KEYWORDS
        self.pos = token.end
        return token

    def _follows_expression(self, start: int) -> bool:
        index = start - 1
        while index >= 0 and self.source[index].isspace():
            index -= 1
        if index < 0:
            return False
        if self.source[index] in ")]":
            return True
        word_start = index
        while word_start >= 0 and (self.source[word_start].isalnum() or self.source[word_start] in "_$"):
            word_start -= 1
        word = self.source[word_start + 1:index + 1]
        return bool(word) and (word in EXPRESSION_END_TEXT or not word.isdigit() and word not in L.KEYWORDS)

    def _scan_word(self, start: int, newline: bool) -> L.Token:
        source = self.source
        char = source[start]
        if char in "\"'":
            end, error = L._scan_string(source, start)
            return L.Token("string", start, end, newline, error)
        if char == "`":
            end, error = L._scan_template(source, start)
            return L.Token("string", start, end, newline, error)
        if char.isdigit() or (char == "." and start + 1 < len(source) and source[start + 1].isdigit()):
            return L.Token("number", start, L.NUMBER.match(source, start).end(), newline)
        match = L.IDENTIFIER.match(source, start)
        if match:
            word = match.group(0)
            return L.Token("keyword" if word in L.KEYWORDS else "identifier", start, match.end(), newline)
        punctuator = next((p for p in L.PUNCTUATORS if source.startswith(p, start)), None)
        if punctuator == "?." and start + 2 < len(source) and source[start + 2].isdigit():
            punctuator = "?"
        if punctuator is None:
            return L.Token("error", start, start + 1, newline, "unexpected character")
        return L.Token("punctuator", start, start + len(punctuator), newline)

    def scan_regexp(self, start: int) -> L.Token:
        end, error = L._scan_regexp(self.source, start)
        self.pos = end
        return L.Token("regexp", start, end, False, error)


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.scanner = _Scanner(source)
        # KDevelop feeds a start token before the program (Parser::parse(T_FEED_JS_PROGRAM))
        start = L.Token("start", 0, 0, False)
        self.pending: List[Tuple[int, L.Token]] = [(C["T_FEED_JS_PROGRAM"], start)]

    def _fetch(self) -> Tuple[int, L.Token]:
        if self.pending:
            return self.pending.pop()
        token = self.scanner.next()
        return self._terminal(token), token

    def _terminal(self, token: L.Token) -> int:
        source = self.source
        if token.kind == "eof":
            return EOF_SYMBOL
        if token.kind == "virtual-semicolon":
            return SEMICOLON_TERMINAL
        if token.kind == "error" or token.error:
            line, column = _position(source, token.start)
            raise ParseError(line, column, token.error or "invalid token")
        text = source[token.start:token.end]
        if token.kind == "identifier":
            return IDENTIFIER_TERMINAL
        if token.kind == "number":
            return NUMBER_TERMINAL
        if token.kind == "string":
            return STRING_TERMINAL
        if token.kind == "keyword":
            if text in SPELL_IDS and text not in JAVASCRIPT_IDENTIFIERS:
                return SPELL_IDS[text]
            return IDENTIFIER_TERMINAL
        if text in SPELL_IDS:
            return SPELL_IDS[text]
        line, column = _position(source, token.start)
        raise ParseError(line, column, f"'{text}' is not supported by the ECMAScript grammar")

    @staticmethod
    def _t_action(state: int, token: int) -> int:
        index = T.ACTION_INDEX[state] + token
        if index < 0 or index >= len(T.ACTION_CHECK) or T.ACTION_CHECK[index] != token:
            return -T.ACTION_DEFAULT[state]
        return T.ACTION_INFO[index]

    @staticmethod
    def _nt_action(state: int, nonterminal: int) -> int:
        index = T.ACTION_INDEX[GOTO_INDEX_OFFSET + state] + nonterminal
        check = GOTO_CHECK_OFFSET + index
        if index < 0 or check >= len(T.ACTION_CHECK) or T.ACTION_CHECK[check] != nonterminal:
            return T.GOTO_DEFAULT[nonterminal]
        return T.ACTION_INFO[GOTO_INFO_OFFSET + index]

    def _describe(self, token: L.Token, terminal: int) -> str:
        text = self.source[token.start:token.end]
        if token.kind == "eof":
            return "end of file"
        if token.kind == "virtual-semicolon":
            return "line break"
        if token.kind == "identifier":
            return f"identifier '{text}'"
        if token.kind == "number":
            return "numeric literal"
        if token.kind == "string":
            return "string literal"
        return f"'{text}'"

    def parse(self) -> Node:
        states: List[int] = [0]
        values: List[Union[Node, Leaf]] = []
        lookahead: Optional[Tuple[int, L.Token]] = None
        while True:
            state = states[-1]
            if lookahead is None and T.ACTION_INDEX[state] != -TERMINAL_COUNT:
                lookahead = self._fetch()
            terminal = lookahead[0] if lookahead is not None else -1
            action = self._t_action(state, terminal)

            if action > 0:
                if action == ACCEPT_STATE:
                    if terminal != EOF_SYMBOL or len(values) != 1:
                        raise ParseError(*_position(self.source, lookahead[1].start), "syntax error")
                    return values[0]
                token = lookahead[1]
                states.append(action)
                values.append(Leaf(token, terminal, self.source[token.start:token.end]))
                lookahead = None
            elif action < 0:
                rule = -action - 1
                length = T.RHS[rule]
                children = values[len(values) - length:] if length else []
                if length:
                    del values[-length:]
                    del states[-length:]
                if rule in T.REGEXP_RULES:
                    slash = children[0]
                    self.scanner.reset(slash.start)
                    literal = self.scanner.scan_regexp(slash.start)
                    if literal.error:
                        line, column = _position(self.source, literal.start)
                        raise ParseError(line, column, literal.error)
                    lookahead = None
                    node: Union[Node, Leaf] = Node(T.LHS[rule], rule,
                                                   [Leaf(literal, REGEXP_TERMINAL,
                                                         self.source[literal.start:literal.end])])
                else:
                    node = Node(T.LHS[rule], rule, children)
                goto = self._nt_action(states[-1], T.LHS[rule] - TERMINAL_COUNT)
                states.append(goto)
                values.append(node)
            else:
                if lookahead is None:
                    lookahead = self._fetch()
                    continue
                token = lookahead[1]
                if self._can_insert_asi_here(state, terminal, token):
                    self.pending.append(lookahead)
                    inserted = ASI_TERMINAL if self._t_action(state, ASI_TERMINAL) and \
                        _can_insert_asi(token, self.source) else COMPATIBILITY_TERMINAL
                    lookahead = (inserted, L.Token("virtual-asi", token.start, token.start, token.newline_before))
                    continue
                line, column = _position(self.source, token.start)
                raise ParseError(line, column, f"syntax error: unexpected {self._describe(token, terminal)}")

    def _can_insert_asi_here(self, state: int, terminal: int, token: L.Token) -> bool:
        if self._t_action(state, COMPATIBILITY_TERMINAL):
            return True
        return bool(self._t_action(state, ASI_TERMINAL)) and _can_insert_asi(token, self.source)


def parse(source: str) -> Node:
    """Parse ``source`` as an ECMAScript program. Raises :class:`ParseError` on the first error."""
    return _Parser(source).parse()


def dump(node: Union[Node, Leaf], source: str, indent: int = 0) -> str:
    """Indented text of the concrete tree, for tests and debugging."""
    pad = "  " * indent
    if isinstance(node, Leaf):
        return f"{pad}{node.text!r}\n"
    lines = [f"{pad}N{node.symbol}/r{node.rule}\n"]
    for child in node.children:
        lines.append(dump(child, source, indent + 1))
    return "".join(lines)
