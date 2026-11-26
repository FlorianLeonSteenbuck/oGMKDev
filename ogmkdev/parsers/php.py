"""PHP parser for PHP 8.0 to 8.6 syntax: recursive descent over the tokens of
:mod:`ogmkdev.lexers.php_lexer`, with precise syntax errors.

It reads inline HTML and the tags (``<?=`` is an echo, ``?>`` ends a statement), every statement
including the alternative syntax (``if: ... endif;``), declarations (functions, classes, interfaces,
traits, enums, namespaces, ``use``, ``const``, ``declare``), attributes, closures and arrow
functions, ``match``, named arguments, first-class callables, nullsafe access, property and
method access, the assignment operators (a variable on the left, as in PHP's grammar), and the
precedence of PHP's operators.

The first error stops the parse. :class:`ParseError` gives the 1-based line and column of the
token where the error was found and a message that names it, for example ``missing ';' before
keyword 'echo'``. Deliberately not checked: scope rules (undefined variables, duplicate
declarations), and the meaning of the features that depend on the PHP version (see
:mod:`ogmkdev.php_features`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from ..lexers import php_lexer as L
from .syntax import Node, ParseError, flags as _flags, position as _position

__all__ = ["Node", "ParseError", "parse"]

ASSIGNMENT_OPERATORS = frozenset({"=", "+=", "-=", "*=", "/=", ".=", "%=", "**=", "&=", "|=", "^=",
                                  "<<=", ">>=", "??="})
# binary operators: precedence and associativity (PHP's table, lowest first)
BINARY = {
    "or": (1, "left"), "xor": (2, "left"), "and": (3, "left"),
    "??": (7, "right"), "||": (8, "left"), "&&": (9, "left"),
    "|": (10, "left"), "^": (11, "left"), "&": (12, "left"),
    "==": (13, "non"), "!=": (13, "non"), "===": (13, "non"), "!==": (13, "non"), "<>": (13, "non"),
    "<=>": (13, "non"),
    "<": (14, "non"), "<=": (14, "non"), ">": (14, "non"), ">=": (14, "non"),
    ".": (15, "left"), "<<": (16, "left"), ">>": (16, "left"),
    "+": (17, "left"), "-": (17, "left"),
    "*": (18, "left"), "/": (18, "left"), "%": (18, "left"),
    "|>": (19, "left"),
    "instanceof": (20, "non"),
    "**": (22, "right"),
}
ASSIGN_PRECEDENCE = 4
TERNARY_PRECEDENCE = 6
NOT_PRECEDENCE = 20          # operand of '!'
UNARY_PRECEDENCE = 21        # operand of unary '-', '+', '~', '@' and the casts: includes '**'
MODIFIERS = frozenset({"public", "protected", "private", "static", "abstract", "final", "readonly", "var"})
VISIBILITY = frozenset({"public", "protected", "private"})
CLOSERS = {"(": ")", "[": "]", "{": "}"}
LITERALS = frozenset({"number", "string", "heredoc", "nowdoc"})
# keywords that start an expression (other keywords are names where a name is expected)
EXPRESSION_WORDS = frozenset({
    "array", "list", "isset", "empty", "exit", "die", "eval", "include", "include_once", "require",
    "require_once", "new", "clone", "print", "yield", "throw", "function", "fn", "static", "match",
    "true", "false", "null", "self", "parent",
})
# reserved words that cannot be a name in an expression (contextual words such as match, enum, readonly
# and fn can be)
NOT_NAMES = frozenset("""
abstract and as break callable case catch class clone const continue declare default do echo else
elseif enddeclare endfor endforeach endif endswitch endwhile extends final finally for foreach
function global goto if implements include include_once instanceof insteadof interface namespace or
private protected public require require_once return switch trait try use var while xor
""".split())
SIMPLE_TYPES = frozenset({"int", "float", "string", "bool", "array", "callable", "iterable", "object",
                          "mixed", "void", "never", "null", "false", "true", "self", "parent", "static"})


@dataclass(frozen=True)
class _Tok:
    kind: str          # the lexer's kind
    start: int
    end: int


class _Parser:
    def __init__(self, source: str, partial: bool = False) -> None:
        self.src = source
        self.partial = partial  # collect the errors and go on (see parse_partial), instead of stopping at the first
        self.errors: List[ParseError] = []
        self.toks: List[L.Token] = []
        for token in L.tokenize(source):
            if token.kind in ("comment", "doc"):
                continue
            if token.kind == "error":
                error = self._lexical_error(token.start, self._error_text(token))
                if not partial:
                    raise error
                self.errors.append(error)
                continue
            self.toks.append(token)
        self.i = 0
        self.prev_end = 0

    # ------------------------------------------------------------ tokens

    @property
    def tok(self) -> L.Token:
        return self.toks[self.i] if self.i < len(self.toks) else L.Token("eof", len(self.src), len(self.src))

    def _at(self, offset: int) -> L.Token:
        index = self.i + offset
        return self.toks[index] if index < len(self.toks) else L.Token("eof", len(self.src), len(self.src))

    def _text(self, token: Optional[L.Token] = None) -> str:
        token = self.tok if token is None else token
        return self.src[token.start:token.end]

    def _lower(self, token: Optional[L.Token] = None) -> str:
        return self._text(token).lower()

    def _advance(self) -> L.Token:
        token = self.tok
        self.i += 1
        self.prev_end = token.end
        return token

    def _is_op(self, text: str, token: Optional[L.Token] = None) -> bool:
        token = self.tok if token is None else token
        return token.kind == "operator" and self._text(token) == text

    def _is_word(self, word: str, token: Optional[L.Token] = None) -> bool:
        token = self.tok if token is None else token
        return token.kind == "keyword" and self._lower(token) == word

    def _is_name(self, token: Optional[L.Token] = None) -> bool:
        token = self.tok if token is None else token
        return token.kind in ("name", "keyword")

    def _error_text(self, token: L.Token) -> str:
        return f"unexpected character {self._text(token)!r}"

    def _describe(self, token: L.Token) -> str:
        if token.kind == "eof":
            return "end of file"
        if token.kind == "variable":
            return f"variable '{self._text(token)}'"
        if token.kind == "keyword":
            return f"keyword '{self._text(token)}'"
        if token.kind == "name":
            return f"name '{self._text(token)}'"
        if token.kind in ("html",):
            return "inline HTML"
        if token.kind == "close":
            return "'?>'"
        if token.kind in LITERALS:
            return "literal"
        return f"'{self._text(token)}'"

    def _error(self, offset: int, message: str) -> ParseError:
        line, column = _position(self.src, offset)
        return ParseError(line, column, message)

    def _lexical_error(self, offset: int, message: str) -> ParseError:
        line, column = _position(self.src, offset)
        return ParseError(line, column, message, lexical=True)

    def _unexpected(self, token: Optional[L.Token] = None) -> ParseError:
        token = self.tok if token is None else token
        if token.kind == "eof":
            return self._error(token.start, "unexpected end of file")
        return self._error(token.start, f"unexpected {self._describe(token)}")

    def _expect_op(self, text: str) -> L.Token:
        if not self._is_op(text):
            raise self._error(self.tok.start, f"expected '{text}' before {self._describe(self.tok)}")
        return self._advance()

    def _expect_word(self, word: str) -> L.Token:
        if not self._is_word(word):
            raise self._error(self.tok.start, f"expected '{word}' before {self._describe(self.tok)}")
        return self._advance()

    def _close(self, close: str, opener: L.Token) -> L.Token:
        if self._is_op(close):
            return self._advance()
        line_open, _ = _position(self.src, opener.start)
        line_here, _ = _position(self.src, self.tok.start)
        where = f" to match '{self._text(opener)}' on line {line_open}" if line_open != line_here else ""
        raise self._error(self.tok.start, f"expected '{close}'{where} before {self._describe(self.tok)}")

    def _terminator(self) -> None:
        """The end of a statement: ';', or the closing tag '?>' (which ends it too)."""
        if self._is_op(";"):
            self._advance()
            return
        if self.tok.kind == "close":
            self._advance()
            return
        if self.tok.kind == "eof":
            raise self._error(self.tok.start, "missing ';' before end of file")
        raise self._error(self.tok.start, f"missing ';' before {self._describe(self.tok)}")

    def _separator(self, close: str) -> bool:
        if self._is_op(","):
            self._advance()
            return True
        if self._is_op(close):
            return False
        raise self._error(self.tok.start, f"expected ',' or '{close}' before {self._describe(self.tok)}")

    # ------------------------------------------------------------ program and statements

    def program(self) -> Node:
        body: List[Node] = []
        while self.tok.kind != "eof":
            if self.tok.kind == "close" or self.tok.kind == "open":
                if self.tok.kind == "open" and self._text() == "<?=":
                    body.append(self._echo_tag())
                else:
                    self._advance()
                continue
            if self._is_word("__halt_compiler"):
                break
            statement = self._guarded_statement()
            if statement is not None:
                body.append(statement)
        return Node("Program", 0, len(self.src), body)

    def _echo_tag(self) -> Node:
        start = self._advance().start
        values = [self.expression()]
        while self._is_op(","):
            self._advance()
            values.append(self.expression())
        self._terminator()
        return Node("EchoStatement", start, self.prev_end, values)

    def _statement(self) -> Node:
        token = self.tok
        kind = token.kind
        if kind == "html":
            self._advance()
            return Node("InlineHTML", token.start, token.end)
        if kind == "open":
            if self._text() == "<?=":
                return self._echo_tag()
            self._advance()
            return Node("Empty", token.start, token.end)
        if kind == "close":
            self._advance()
            return Node("Empty", token.start, token.end)
        if kind == "attr":
            attributes = self._attributes()
            return self._attributed(token.start, attributes)
        if kind == "operator":
            if self._text() == "{":
                return self._block()
            if self._text() == ";":
                self._advance()
                return Node("EmptyStatement", token.start, token.end)
        if kind == "keyword":
            if self._lower() in ("class", "interface", "trait", "enum", "abstract", "final", "readonly") \
                    and self._class_follows():
                return self._class_declaration([])
            handler = self._STATEMENT_WORDS.get(self._lower())
            if handler is not None:
                return handler(self)
        if kind == "name" and self._is_op(":", self._at(1)) and "\\" not in self._text():
            return self._label()
        if kind == "keyword" and self._lower() in ("abstract", "final", "readonly") and self._class_follows():
            return self._class_declaration([])
        return self._expression_statement()

    def _expression_statement(self) -> Node:
        start = self.tok.start
        expression = self.expression()
        self._terminator()
        return Node("ExpressionStatement", start, self.prev_end, [expression])

    def _guarded_statement(self) -> Optional[Node]:
        """A statement. In partial mode a syntax error is recorded, the rest of the statement is skipped, and the
        statement is None: the parser goes on with the next one."""
        before = self.i
        try:
            return self._statement()
        except ParseError as error:
            if not self.partial:
                raise
            self.errors.append(error)
            self._recover()
            if self.i == before:  # a token no statement can start with: move past it
                self._advance()
            return None

    def _recover(self) -> None:
        """Skips the rest of a broken statement or member: up to the ';' (or '?>') that ends it at its own nesting
        depth, or past the '}' that closes a block it opened. A '}' that closes the enclosing block stays."""
        depth = 0
        while self.tok.kind != "eof":
            if self.tok.kind == "close" and depth == 0:
                self._advance()
                return
            if self._is_op("(") or self._is_op("[") or self._is_op("{"):
                depth += 1
            elif self._is_op(")") or self._is_op("]"):
                depth = max(0, depth - 1)
            elif self._is_op("}"):
                if depth == 0:
                    return
                depth -= 1
                if depth == 0:
                    self._advance()
                    return
            elif self._is_op(";") and depth == 0:
                self._advance()
                return
            self._advance()

    def _block(self) -> Node:
        opener = self._expect_op("{")
        body: List[Node] = []
        while not self._is_op("}") and self.tok.kind != "eof":
            statement = self._guarded_statement()
            if statement is not None:
                body.append(statement)
        self._close("}", opener)
        return Node("BlockStatement", opener.start, self.prev_end, body)

    def _statements_until(self, words: Tuple[str, ...]) -> Node:
        """Statements of an alternative-syntax block, up to one of the words that ends it."""
        start = self.tok.start
        body: List[Node] = []
        while not (self.tok.kind == "keyword" and self._lower() in words) and self.tok.kind != "eof":
            statement = self._guarded_statement()
            if statement is not None:
                body.append(statement)
        if self.tok.kind == "eof":
            raise self._error(self.tok.start, f"expected '{words[0]}' before end of file")
        return Node("BlockStatement", start, self.prev_end, body)

    def _alternative_end(self, word: str) -> None:
        self._expect_word(word)
        self._terminator()

    def _paren_expression(self, word: str) -> Node:
        if not self._is_op("("):
            raise self._error(self.tok.start, f"expected '(' after '{word}', found {self._describe(self.tok)}")
        opener = self._advance()
        expression = self.expression()
        self._close(")", opener)
        return expression

    def _if(self) -> Node:
        start = self._advance().start
        test = self._paren_expression("if")
        if self._is_op(":"):
            self._advance()
            children = [test, self._statements_until(("elseif", "else", "endif"))]
            while self._is_word("elseif"):
                self._advance()
                children.append(self._paren_expression("elseif"))
                self._expect_op(":")
                children.append(self._statements_until(("elseif", "else", "endif")))
            if self._is_word("else"):
                self._advance()
                self._expect_op(":")
                children.append(self._statements_until(("endif",)))
            self._alternative_end("endif")
            return Node("IfStatement", start, self.prev_end, children)
        children = [test, self._statement()]
        while self._is_word("elseif"):
            self._advance()
            children.append(self._paren_expression("elseif"))
            children.append(self._statement())
        if self._is_word("else"):
            self._advance()
            children.append(self._statement())
        return Node("IfStatement", start, self.prev_end, children)

    def _loop_body(self, word: str, end_word: str) -> Node:
        if self._is_op(":"):
            self._advance()
            body = self._statements_until((end_word,))
            self._alternative_end(end_word)
            return body
        return self._statement()

    def _while(self) -> Node:
        start = self._advance().start
        test = self._paren_expression("while")
        body = self._loop_body("while", "endwhile")
        return Node("WhileStatement", start, self.prev_end, [test, body])

    def _do(self) -> Node:
        start = self._advance().start
        body = self._statement()
        self._expect_word("while")
        test = self._paren_expression("while")
        self._terminator()
        return Node("DoWhileStatement", start, self.prev_end, [body, test])

    def _expression_list(self, close: str) -> List[Node]:
        values: List[Node] = []
        while not self._is_op(close):
            values.append(self.expression())
            if not self._is_op(","):
                break
            self._advance()
        return values

    def _for(self) -> Node:
        start = self._advance().start
        opener = self._expect_op("(")
        init = self._expression_list(";")
        self._expect_op(";")
        test = self._expression_list(";")
        self._expect_op(";")
        step = self._expression_list(")")
        self._close(")", opener)
        body = self._loop_body("for", "endfor")
        return Node("ForStatement", start, self.prev_end, [Node("ExpressionList", start, start, init),
                                                          Node("ExpressionList", start, start, test),
                                                          Node("ExpressionList", start, start, step), body])

    def _foreach(self) -> Node:
        start = self._advance().start
        opener = self._expect_op("(")
        subject = self.expression()
        self._expect_word("as")
        children = [subject]
        target = self._foreach_target()
        if self._is_op("=>"):
            self._advance()
            children.append(target)
            target = self._foreach_target()
        children.append(target)
        self._close(")", opener)
        children.append(self._loop_body("foreach", "endforeach"))
        return Node("ForeachStatement", start, self.prev_end, children)

    def _foreach_target(self) -> Node:
        if self._is_op("&"):
            start = self._advance().start
            return Node("ByReference", start, self.prev_end, [self.unary()])
        return self.unary()

    def _switch(self) -> Node:
        start = self._advance().start
        subject = self._paren_expression("switch")
        alternative = self._is_op(":")
        if alternative:
            self._advance()
        else:
            opener = self._expect_op("{")
        cases: List[Node] = [subject]
        has_default = False
        while True:
            if alternative and self._is_word("endswitch"):
                break
            if not alternative and self._is_op("}"):
                break
            if self.tok.kind == "eof":
                raise self._error(self.tok.start, "expected '}' before end of file")
            case_start = self.tok.start
            if self._is_word("case"):
                self._advance()
                labels = [self.expression()]
            elif self._is_word("default"):
                if has_default:
                    raise self._error(self.tok.start, "more than one default clause in switch")
                has_default = True
                self._advance()
                labels = []
            else:
                raise self._error(self.tok.start, f"expected 'case' or 'default', found {self._describe(self.tok)}")
            if self._is_op(":") or self._is_op(";"):
                self._advance()
            else:
                raise self._error(self.tok.start, f"expected ':' before {self._describe(self.tok)}")
            body: List[Node] = []
            while not (self._is_word("case") or self._is_word("default") or self._is_op("}")
                       or self._is_word("endswitch") or self.tok.kind == "eof"):
                body.append(self._statement())
            cases.append(Node("SwitchCase", case_start, self.prev_end, labels + body))
        if alternative:
            self._alternative_end("endswitch")
        else:
            self._close("}", opener)
        return Node("SwitchStatement", start, self.prev_end, cases)

    def _jump(self) -> Node:
        token = self._advance()
        word = self._lower(token)
        children: List[Node] = []
        if self.tok.kind == "number":
            children.append(Node("Literal", self.tok.start, self.tok.end))
            self._advance()
        self._terminator()
        kind = "BreakStatement" if word == "break" else "ContinueStatement"
        return Node(kind, token.start, self.prev_end, children)

    def _return(self) -> Node:
        start = self._advance().start
        children: List[Node] = []
        if not (self._is_op(";") or self.tok.kind in ("close", "eof")):
            children.append(self.expression())
        self._terminator()
        return Node("ReturnStatement", start, self.prev_end, children)

    def _echo(self) -> Node:
        start = self._advance().start
        values = [self.expression()]
        while self._is_op(","):
            self._advance()
            values.append(self.expression())
        self._terminator()
        return Node("EchoStatement", start, self.prev_end, values)

    def _global(self) -> Node:
        start = self._advance().start
        names = [self._variable_token()]
        while self._is_op(","):
            self._advance()
            names.append(self._variable_token())
        self._terminator()
        return Node("GlobalStatement", start, self.prev_end, names)

    def _variable_token(self) -> Node:
        token = self.tok
        if token.kind != "variable":
            raise self._error(token.start, f"expected a variable, found {self._describe(token)}")
        self._advance()
        return Node("Variable", token.start, token.end, text=self._text(token))

    def _static(self) -> Node:
        """``static $x = 1, $y;`` (static variables); ``static::`` and ``static fn`` are expressions."""
        following = self._at(1)
        if following.kind == "variable":
            start = self._advance().start
            children: List[Node] = []
            while True:
                children.append(self._variable_token())
                if self._is_op("="):
                    self._advance()
                    children.append(self.expression())
                if not self._is_op(","):
                    break
                self._advance()
            self._terminator()
            return Node("StaticStatement", start, self.prev_end, children)
        return self._expression_statement()

    def _try(self) -> Node:
        start = self._advance().start
        children = [self._block()]
        while self._is_word("catch"):
            catch_start = self._advance().start
            opener = self._expect_op("(")
            types = [self._name()]
            while self._is_op("|"):
                self._advance()
                types.append(self._name())
            variables = [self._variable_token()] if self.tok.kind == "variable" else []
            self._close(")", opener)
            children.append(Node("CatchClause", catch_start, self.prev_end, types + variables + [self._block()]))
        if self._is_word("finally"):
            self._advance()
            children.append(self._block())
        if len(children) == 1:
            raise self._error(self.tok.start,
                              f"expected 'catch' or 'finally' after the try block, found {self._describe(self.tok)}")
        return Node("TryStatement", start, self.prev_end, children)

    def _unset(self) -> Node:
        start = self._advance().start
        opener = self._expect_op("(")
        values = self._expression_list(")")
        self._close(")", opener)
        self._terminator()
        return Node("UnsetStatement", start, self.prev_end, values)

    def _label(self) -> Node:
        token = self._advance()
        self._advance()  # the colon
        return Node("LabelStatement", token.start, self.prev_end, text=self._text(token))

    def _goto(self) -> Node:
        start = self._advance().start
        name = self._name()
        self._terminator()
        return Node("GotoStatement", start, self.prev_end, [name])

    def _function_statement(self) -> Node:
        """A declaration when a name follows ``function`` (or ``function &name``), else a closure."""
        after = self._at(1)
        if self._is_name(after) or (self._is_op("&", after) and self._is_name(self._at(2))):
            return self._function_declaration(self.tok.start, [], None)
        return self._expression_statement()

    def _function_declaration(self, start: int, attributes: List[Node], modifiers) -> Node:
        self._expect_word("function")
        by_ref = self._is_op("&")
        if by_ref:
            self._advance()
        name = self._member_name()
        parameters = self._parameters()
        return_type = self._return_type()
        body = self._block()
        return Node("FunctionDeclaration", start, self.prev_end,
                    attributes + [name, parameters] + ([return_type] if return_type else []) + [body],
                    flags=_flags("ref" if by_ref else ""))

    def _namespace(self) -> Node:
        start = self._advance().start
        if self.tok.kind == "name" or (self.tok.kind == "keyword" and self._lower() not in ("use",)):
            name = self._name()
        else:
            name = None
        if self._is_op("{"):
            body = self._block()
            return Node("NamespaceDeclaration", start, self.prev_end, ([name] if name else []) + [body])
        self._terminator()
        return Node("NamespaceDeclaration", start, self.prev_end, [name] if name else [])

    def _use(self) -> Node:
        start = self._advance().start
        kind = ""
        if self._is_word("function") or self._is_word("const"):
            kind = self._lower()
            self._advance()
        children: List[Node] = []
        while True:
            name = self._name()
            if self._is_op("\\") and self._is_op("{", self._at(1)):
                self._advance()
                opener = self._expect_op("{")
                while not self._is_op("}") and self.tok.kind != "eof":
                    group_start = self.tok.start
                    group_name = self._name()
                    alias = self._alias()
                    children.append(Node("UseItem", group_start, self.prev_end,
                                         [group_name] + ([alias] if alias else []), text=name.text))
                    if not self._separator("}"):
                        break
                self._close("}", opener)
            else:
                alias = self._alias()
                children.append(Node("UseItem", name.start, self.prev_end, [name] + ([alias] if alias else [])))
            if not self._is_op(","):
                break
            self._advance()
        self._terminator()
        return Node("UseStatement", start, self.prev_end, children, text=kind)

    def _alias(self) -> Optional[Node]:
        if self._is_word("as"):
            self._advance()
            return self._member_name()
        return None

    def _const_statement(self) -> Node:
        start = self._advance().start
        children: List[Node] = []
        while True:
            name = self._member_name()
            self._expect_op("=")
            children.append(Node("ConstElement", name.start, self.prev_end, [name, self.expression()]))
            if not self._is_op(","):
                break
            self._advance()
        self._terminator()
        return Node("ConstStatement", start, self.prev_end, children)

    def _declare(self) -> Node:
        start = self._advance().start
        opener = self._expect_op("(")
        values: List[Node] = []
        while not self._is_op(")") and self.tok.kind != "eof":  # directives: name = value
            directive_start = self.tok.start
            name = self._name()
            self._expect_op("=")
            values.append(Node("Directive", directive_start, self.prev_end, [name, self.expression()]))
            if not self._separator(")"):
                break
        self._close(")", opener)
        if self._is_op("{"):
            return Node("DeclareStatement", start, self.prev_end, values + [self._block()])
        if self._is_op(":"):
            self._advance()
            body = self._statements_until(("enddeclare",))
            self._alternative_end("enddeclare")
            return Node("DeclareStatement", start, self.prev_end, values + [body])
        self._terminator()
        return Node("DeclareStatement", start, self.prev_end, values)

    def _attributes(self) -> List[Node]:
        groups: List[Node] = []
        while self.tok.kind == "attr":
            opener = self._advance()
            items: List[Node] = []
            while not self._is_op("]") and self.tok.kind != "eof":
                item_start = self.tok.start
                name = self._name()
                arguments = self._arguments() if self._is_op("(") else None
                items.append(Node("Attribute", item_start, self.prev_end,
                                  [name] + ([arguments] if arguments else [])))
                if not self._separator("]"):
                    break
            self._close("]", opener)
            groups.append(Node("AttributeGroup", opener.start, self.prev_end, items))
        return groups

    def _attributed(self, start: int, attributes: List[Node]) -> Node:
        """A declaration or a closure after its attributes."""
        if self._is_word("function") and self._is_name(self._at(1)) or (
                self._is_word("function") and self._is_op("&", self._at(1))):
            return self._function_declaration(start, attributes, None)
        if self._is_word("function") or self._is_word("fn") or self._is_word("static"):
            expression = self._expression_from_primary()
            self._terminator()
            return Node("ExpressionStatement", start, self.prev_end, [expression] + attributes)
        if self._class_follows():
            return self._class_declaration(attributes)
        raise self._error(self.tok.start, f"unexpected {self._describe(self.tok)} after attributes")

    def _class_follows(self) -> bool:
        token = self.tok
        index = 0
        while self._lower(self._at(index)) in ("abstract", "final", "readonly") and self._at(index).kind == "keyword":
            index += 1
        following = self._at(index)
        return following.kind == "keyword" and self._lower(following) in ("class", "interface", "trait", "enum") \
            and not (self._lower(following) == "enum" and not self._is_name(self._at(index + 1)))

    def _class_declaration(self, attributes: List[Node]) -> Node:
        start = self.tok.start
        modifiers: List[str] = []
        while self._lower() in ("abstract", "final", "readonly") and self.tok.kind == "keyword":
            modifiers.append(self._lower())
            self._advance()
        keyword = self._lower()
        self._advance()
        name = self._member_name()
        children: List[Node] = attributes + [name]
        if keyword == "enum" and self._is_op(":"):
            self._advance()
            children.append(self._type())
        if self._is_word("extends"):
            self._advance()
            names = [self._name()]
            while self._is_op(","):
                self._advance()
                names.append(self._name())
            children.extend(names)
        if self._is_word("implements"):
            self._advance()
            names = [self._name()]
            while self._is_op(","):
                self._advance()
                names.append(self._name())
            children.extend(names)
        children.append(self._class_body(keyword))
        kind = "ClassDeclaration" if keyword == "class" else keyword.capitalize() + "Declaration"
        return Node(kind, start, self.prev_end, children, flags=_flags(*modifiers))

    def _class_body(self, keyword: str) -> Node:
        opener = self._expect_op("{")
        members: List[Node] = []
        while not self._is_op("}") and self.tok.kind != "eof":
            if self._is_op(";"):
                self._advance()
                continue
            before = self.i
            try:
                members.append(self._member(keyword))
            except ParseError as error:
                if not self.partial:
                    raise
                self.errors.append(error)
                self._recover()
                if self.i == before:
                    self._advance()
        self._close("}", opener)
        return Node("ClassBody", opener.start, self.prev_end, members)

    def _member(self, keyword: str) -> Node:
        start = self.tok.start
        attributes = self._attributes()
        if self._is_word("use"):
            return self._trait_use(start)
        if self._is_word("case") and keyword == "enum":
            self._advance()
            name = self._member_name()
            children = [name]
            if self._is_op("="):
                self._advance()
                children.append(self.expression())
            self._terminator()
            return Node("EnumCase", start, self.prev_end, attributes + children)
        member_flags: List[str] = []
        while self.tok.kind == "keyword" and self._lower() in MODIFIERS and not (
                (self._is_op("(", self._at(1)) and self._lower() not in VISIBILITY)  # but private(set) is a modifier
                or self._is_op("::", self._at(1)) or self._is_op("=", self._at(1))
                or self._is_op(";", self._at(1)) or self._is_op(",", self._at(1))):
            member_flags.append(self._lower())
            self._advance()
            if member_flags[-1] in VISIBILITY and self._is_op("("):  # asymmetric visibility: private(set)
                self._advance()
                self._member_name()
                self._expect_op(")")
                member_flags.append("asymmetric")
        if self._is_word("const"):
            self._advance()
            children: List[Node] = []
            if self._is_name() and self._is_name(self._at(1)):
                children.append(self._type())
            while True:
                name = self._member_name()
                self._expect_op("=")
                children.append(Node("ConstElement", name.start, self.prev_end, [name, self.expression()]))
                if not self._is_op(","):
                    break
                self._advance()
            self._terminator()
            return Node("ClassConstant", start, self.prev_end, attributes + children, flags=_flags(*member_flags))
        if self._is_word("function"):
            return self._method(start, attributes, member_flags)
        children = []
        if not self.tok.kind == "variable":
            children.append(self._type())
        while True:
            variable = self._variable_token()
            value = None
            if self._is_op("="):
                self._advance()
                value = self.expression()
            children.append(Node("PropertyElement", variable.start, self.prev_end,
                                 [variable] + ([value] if value else [])))
            if not self._is_op(","):
                break
            self._advance()
        if self._is_op("{"):  # property hooks (PHP 8.4): read as one balanced block, which is a PropertyHooks node
            hooks_start = self.tok.start
            self._balanced_block()
            children.append(Node("PropertyHooks", hooks_start, self.prev_end, []))
        else:
            self._terminator()
        return Node("PropertyDeclaration", start, self.prev_end, attributes + children, flags=_flags(*member_flags))

    def _balanced_block(self) -> None:
        opener = self._advance()
        depth = 1
        while depth and self.tok.kind != "eof":
            if self._is_op("{"):
                depth += 1
            elif self._is_op("}"):
                depth -= 1
            self._advance()
        if depth:
            self._close("}", opener)

    def _method(self, start: int, attributes: List[Node], member_flags: List[str]) -> Node:
        self._expect_word("function")
        by_ref = self._is_op("&")
        if by_ref:
            self._advance()
        name = self._member_name()
        parameters = self._parameters()
        return_type = self._return_type()
        if self._is_op(";"):
            self._advance()
            body = None
        else:
            body = self._block()
        children = attributes + [name, parameters] + ([return_type] if return_type else []) + ([body] if body else [])
        return Node("MethodDeclaration", start, self.prev_end, children,
                    flags=_flags(*member_flags, "ref" if by_ref else ""))

    def _trait_use(self, start: int) -> Node:
        self._advance()
        names = [self._name()]
        while self._is_op(","):
            self._advance()
            names.append(self._name())
        children: List[Node] = names
        if self._is_op("{"):
            opener = self._advance()
            while not self._is_op("}") and self.tok.kind != "eof":
                rule_start = self.tok.start
                first = self._name()
                if self._is_op("::"):
                    self._advance()
                    method = self._member_name()
                    rule_children = [first, method]
                else:
                    rule_children = [first]
                if self._is_word("insteadof"):
                    self._advance()
                    rule_children.extend(self._names())
                elif self._is_word("as"):
                    self._advance()
                    if self._is_word("public") or self._is_word("protected") or self._is_word("private"):
                        self._advance()
                    if self._is_name() and not self._is_op(";"):
                        rule_children.append(self._member_name())
                self._terminator()
                children.append(Node("TraitRule", rule_start, self.prev_end, rule_children))
            self._close("}", opener)
        else:
            self._terminator()
        return Node("TraitUse", start, self.prev_end, children)

    def _names(self) -> List[Node]:
        names = [self._name()]
        while self._is_op(","):
            self._advance()
            names.append(self._name())
        return names

    # ------------------------------------------------------------ names, types, parameters

    _STATEMENT_WORDS = {
        "if": _if, "while": _while, "do": _do, "for": _for, "foreach": _foreach, "switch": _switch,
        "break": _jump, "continue": _jump, "return": _return, "echo": _echo, "global": _global,
        "static": _static, "try": _try, "throw": _expression_statement, "unset": _unset,
        "goto": _goto, "namespace": _namespace, "use": _use, "const": _const_statement,
        "declare": _declare, "function": _function_statement,
    }

    def _name(self) -> Node:
        token = self.tok
        if token.kind not in ("name", "keyword"):
            raise self._error(token.start, f"expected a name, found {self._describe(token)}")
        self._advance()
        return Node("Name", token.start, token.end, text=self._text(token))

    def _member_name(self) -> Node:
        """A name where a keyword is allowed too: a method, a property, a constant, an enum case."""
        return self._name()

    def _type(self) -> Node:
        start = self.tok.start
        nullable = self._is_op("?")
        if nullable:
            self._advance()
        if self._is_op("("):
            opener = self._advance()
            inner = self._type()
            self._close(")", opener)
            types = [inner]
        else:
            types = [self._name()]
        while (self._is_op("|") or (self._is_op("&") and not self._reference_follows())) :
            self._advance()
            if self._is_op("("):
                opener = self._advance()
                types.append(self._type())
                self._close(")", opener)
            else:
                types.append(self._name())
        return Node("Type", start, self.prev_end, types, flags=_flags("nullable" if nullable else ""))

    def _reference_follows(self) -> bool:
        following = self._at(1)
        return following.kind == "variable" or self._is_op("...", following)

    def _return_type(self) -> Optional[Node]:
        if not self._is_op(":"):
            return None
        self._advance()
        return self._type()

    def _parameters(self) -> Node:
        opener = self._expect_op("(")
        parameters: List[Node] = []
        while not self._is_op(")") and self.tok.kind != "eof":
            parameters.append(self._parameter())
            if not self._separator(")"):
                break
        self._close(")", opener)
        return Node("ParameterList", opener.start, self.prev_end, parameters)

    def _parameter(self) -> Node:
        start = self.tok.start
        attributes = self._attributes()
        member_flags: List[str] = []
        while self.tok.kind == "keyword" and self._lower() in ("public", "protected", "private", "readonly"):
            member_flags.append(self._lower())
            self._advance()
        children: List[Node] = list(attributes)
        if not (self.tok.kind == "variable" or self._is_op("&") or self._is_op("...")):
            children.append(self._type())
        by_ref = self._is_op("&")
        if by_ref:
            self._advance()
        variadic = self._is_op("...")
        if variadic:
            self._advance()
        children.append(self._variable_token())
        if self._is_op("="):
            self._advance()
            children.append(self.expression())
        return Node("Parameter", start, self.prev_end, children,
                    flags=_flags(*member_flags, "ref" if by_ref else "", "variadic" if variadic else ""))

    def _arguments(self) -> Node:
        opener = self._expect_op("(")
        if self._is_op("...") and self._is_op(")", self._at(1)):
            self._advance()
            self._advance()
            return Node("Arguments", opener.start, self.prev_end, [], flags=_flags("callable"))
        args: List[Node] = []
        while not self._is_op(")") and self.tok.kind != "eof":
            start = self.tok.start
            if self._is_op("?") and (self._is_op(",", self._at(1)) or self._is_op(")", self._at(1))):
                self._advance()  # a placeholder of a partial application (PHP 8.6): f(?, 1)
                args.append(Node("ArgumentPlaceholder", start, self.prev_end, [], text="?"))
            elif self._is_op("...") and (self._is_op(",", self._at(1)) or self._is_op(")", self._at(1))):
                self._advance()  # f(1, ...): the rest of the arguments are placeholders too
                args.append(Node("ArgumentPlaceholder", start, self.prev_end, [], text="..."))
            elif self._is_op("..."):
                self._advance()
                args.append(Node("Spread", start, self.prev_end, [self.expression()]))
            elif self._is_name() and self._is_op(":", self._at(1)):
                name = self._name()
                self._advance()
                args.append(Node("NamedArgument", start, self.prev_end, [name, self.expression()]))
            else:
                args.append(self.expression())
            if not self._separator(")"):
                break
        self._close(")", opener)
        return Node("Arguments", opener.start, self.prev_end, args)

    def _array_items(self, close: str) -> List[Node]:
        items: List[Node] = []
        while not self._is_op(close) and self.tok.kind != "eof":
            start = self.tok.start
            if self._is_op(","):
                items.append(Node("Elision", start, start))
                self._advance()
                continue
            if self._is_op("..."):
                self._advance()
                items.append(Node("Spread", start, self.prev_end, [self.expression()]))
            else:
                by_ref = self._is_op("&")
                if by_ref:
                    self._advance()
                value = self.expression()
                if self._is_op("=>"):
                    self._advance()
                    ref = self._is_op("&")
                    if ref:
                        self._advance()
                    value = Node("KeyValue", start, self.prev_end, [value, self.expression()],
                                 flags=_flags("ref" if ref else ""))
                items.append(Node("ArrayItem", start, self.prev_end, [value], flags=_flags("ref" if by_ref else "")))
            if not self._separator(close):
                break
        return items

    # ------------------------------------------------------------ expressions

    def expression(self, min_precedence: int = 0) -> Node:
        left = self.unary()
        while True:
            token = self.tok
            if self._is_op("?") and min_precedence <= TERNARY_PRECEDENCE:
                self._advance()
                if self._is_op(":"):
                    self._advance()
                    alternate = self.expression(TERNARY_PRECEDENCE)
                    left = Node("TernaryExpression", left.start, self.prev_end, [left, alternate])
                    continue
                consequent = self.expression()
                self._expect_op(":")
                alternate = self.expression(TERNARY_PRECEDENCE)
                left = Node("TernaryExpression", left.start, self.prev_end, [left, consequent, alternate])
                continue
            text = self._lower(token) if token.kind == "keyword" else self._text(token)
            if token.kind not in ("operator", "keyword") or text not in BINARY:
                return left
            precedence, associativity = BINARY[text]
            if precedence < min_precedence:
                return left
            self._advance()
            next_min = precedence if associativity == "right" else precedence + 1
            if text == "instanceof":
                right = self.unary() if not self._is_name() else self._name()
            else:
                right = self.expression(next_min)
            kind = "LogicalExpression" if text in ("or", "xor", "and", "||", "&&", "??") else "BinaryExpression"
            left = Node(kind, left.start, self.prev_end, [left, right], text=text)

    def unary(self) -> Node:
        token = self.tok
        if token.kind == "operator":
            text = self._text(token)
            if text == "!":
                self._advance()
                return Node("UnaryExpression", token.start, self.prev_end, [self.expression(NOT_PRECEDENCE)], text="!")
            if text in ("-", "+", "~", "@"):
                self._advance()
                return Node("UnaryExpression", token.start, self.prev_end,
                            [self.expression(UNARY_PRECEDENCE)], text=text)
            if text in ("++", "--"):
                self._advance()
                operand = self.postfix(self.primary())
                return Node("UpdateExpression", token.start, self.prev_end, [operand], text=text,
                            flags=_flags("prefix"))
            if text == "&":  # by-reference assignment: $a = &$b
                self._advance()
                return Node("ByReference", token.start, self.prev_end, [self.unary()])
        if token.kind == "cast":
            self._advance()
            return Node("CastExpression", token.start, self.prev_end, [self.expression(UNARY_PRECEDENCE)],
                        text=self._text(token))
        if token.kind == "keyword":
            word = self._lower(token)
            if word == "print":
                self._advance()
                return Node("PrintExpression", token.start, self.prev_end, [self.expression(ASSIGN_PRECEDENCE)])
            if word == "throw":
                self._advance()
                return Node("ThrowExpression", token.start, self.prev_end, [self.expression()])
            if word == "yield":
                return self._yield()
            if word in ("include", "include_once", "require", "require_once"):
                self._advance()
                return Node("IncludeExpression", token.start, self.prev_end, [self.expression()], text=word)
            if word == "clone":
                self._advance()
                if self._is_op("("):  # clone($object) or, since PHP 8.5, clone($object, ['property' => value])
                    arguments = self._arguments()
                    if len(arguments.children) == 1 and arguments.children[0].kind != "Spread":
                        return Node("CloneExpression", token.start, self.prev_end, [self.postfix(arguments.children[0])])
                    return Node("CloneExpression", token.start, self.prev_end, [arguments], flags=_flags("with"))
                return Node("CloneExpression", token.start, self.prev_end, [self.postfix(self.primary())])
        return self.postfix(self.primary())

    def _yield(self) -> Node:
        start = self._advance().start
        if self.tok.kind == "name" and self._lower() == "from":  # `from` is a name for the lexer
            self._advance()
            return Node("YieldFrom", start, self.prev_end, [self.expression(ASSIGN_PRECEDENCE)])
        if self.tok.kind in ("close", "eof") or any(self._is_op(text) for text in (";", ")", ",", "]")):
            return Node("YieldExpression", start, self.prev_end, [])
        value = self.expression(ASSIGN_PRECEDENCE)
        if self._is_op("=>"):
            self._advance()
            value = Node("KeyValue", value.start, self.prev_end, [value, self.expression(ASSIGN_PRECEDENCE)])
        return Node("YieldExpression", start, self.prev_end, [value])

    def _lvalue(self, node: Node) -> bool:
        return node.kind in ("Variable", "PropertyAccess", "NullsafePropertyAccess", "IndexAccess",
                             "StaticProperty", "ArrayLiteral", "DynamicVariable", "ListLiteral")

    def postfix(self, node: Node) -> Node:
        while True:
            token = self.tok
            if token.kind != "operator" and token.kind != "keyword":
                return node
            text = self._text(token)
            if text == "[" and token.kind == "operator":
                self._advance()
                index = None if self._is_op("]") else self.expression()
                self._close("]", token)
                node = Node("IndexAccess", node.start, self.prev_end, [node] + ([index] if index else []))
                continue
            if text in ("->", "?->") and token.kind == "operator":
                self._advance()
                member = self._property_member()
                if self._is_op("("):
                    arguments = self._arguments()
                    node = Node("MethodCall", node.start, self.prev_end, [node, member, arguments],
                                flags=_flags("nullsafe" if text == "?->" else ""))
                else:
                    kind = "NullsafePropertyAccess" if text == "?->" else "PropertyAccess"
                    node = Node(kind, node.start, self.prev_end, [node, member])
                continue
            if text == "::" and token.kind == "operator":
                self._advance()
                if self.tok.kind == "variable":
                    variable = self._variable_token()
                    if self._is_op("("):
                        node = Node("StaticCall", node.start, self.prev_end,
                                    [node, variable, self._arguments()], flags=_flags("dynamic"))
                    else:
                        node = Node("StaticProperty", node.start, self.prev_end, [node, variable])
                elif self._is_op("{"):  # a dynamic name: $class::{$name}(), or the constant $class::{$name}
                    self._advance()
                    expression = self.expression()
                    self._expect_op("}")
                    if self._is_op("("):
                        node = Node("StaticCall", node.start, self.prev_end, [node, expression, self._arguments()])
                    else:
                        node = Node("ClassConstant", node.start, self.prev_end, [node, expression], flags=_flags("dynamic"))
                elif self._is_name():
                    member = self._name()
                    if self._is_op("("):
                        node = Node("StaticCall", node.start, self.prev_end, [node, member, self._arguments()])
                    else:
                        node = Node("ClassConstant", node.start, self.prev_end, [node, member])
                else:
                    raise self._error(self.tok.start, f"expected a member after '::', found {self._describe(self.tok)}")
                continue
            if text == "(" and token.kind == "operator":
                node = Node("Call", node.start, self.prev_end, [node, self._arguments()])
                continue
            if text in ("++", "--") and token.kind == "operator":
                if not self._lvalue(node):
                    raise self._error(token.start, f"invalid operand of '{text}'")
                self._advance()
                node = Node("UpdateExpression", node.start, self.prev_end, [node], text=text)
                continue
            if text in ASSIGNMENT_OPERATORS and token.kind == "operator":
                if not self._lvalue(node):
                    raise self._error(token.start, f"cannot assign to this expression with '{text}'")
                self._advance()
                if text == "=" and self._is_op("&"):
                    self._advance()
                    value = Node("ByReference", self.tok.start, self.tok.end, [self.expression(ASSIGN_PRECEDENCE)])
                else:
                    value = self.expression(ASSIGN_PRECEDENCE)
                return Node("AssignmentExpression", node.start, self.prev_end, [node, value], text=text)
            return node

    def _property_member(self) -> Node:
        token = self.tok
        if token.kind == "variable":
            return self._variable_token()
        if self._is_op("{"):
            self._advance()
            expression = self.expression()
            self._expect_op("}")
            return expression
        if self._is_name():
            return self._name()
        raise self._error(token.start, f"expected a property name, found {self._describe(token)}")

    def primary(self) -> Node:
        token = self.tok
        kind = token.kind
        if kind == "variable":
            return self._variable_token()
        if kind in LITERALS:
            self._advance()
            return Node("Literal", token.start, token.end, text=self._text(token))
        if kind == "operator":
            text = self._text(token)
            if text == "(":
                self._advance()
                expression = self.expression()
                self._close(")", token)
                return expression
            if text == "[":
                self._advance()
                items = self._array_items("]")
                self._close("]", token)
                return Node("ArrayLiteral", token.start, self.prev_end, items)
            if text == "$":
                return self._dynamic_variable()
        if kind == "attr":
            attributes = self._attributes()
            return self._expression_from_primary(attributes)
        if kind == "name":
            self._advance()
            return Node("Name", token.start, token.end, text=self._text(token))
        if kind == "keyword":
            word = self._lower(token)
            if word in ("true", "false", "null"):
                self._advance()
                return Node("Literal", token.start, token.end, text=word)
            if word in ("self", "parent"):
                self._advance()
                return Node("Name", token.start, token.end, text=word)
            if word == "static" and self._is_op("::", self._at(1)):
                self._advance()
                return Node("Name", token.start, token.end, text="static")
            if word in ("function", "fn", "static"):
                return self._expression_from_primary()
            if word == "new":
                return self._new()
            if word == "match":
                if self._is_op("(", self._at(1)):
                    return self._match()
            if word in ("array", "list"):
                return self._array_construct(word)
            if word == "isset":
                start = self._advance().start
                opener = self._expect_op("(")
                values = self._expression_list(")")
                self._close(")", opener)
                return Node("IssetExpression", start, self.prev_end, values)
            if word == "empty":
                start = self._advance().start
                opener = self._expect_op("(")
                value = self.expression()
                self._close(")", opener)
                return Node("EmptyExpression", start, self.prev_end, [value])
            if word in ("exit", "die"):
                start = self._advance().start
                values: List[Node] = []
                if self._is_op("("):
                    opener = self._advance()
                    values = self._expression_list(")")
                    self._close(")", opener)
                return Node("ExitExpression", start, self.prev_end, values)
            if word == "eval":
                start = self._advance().start
                opener = self._expect_op("(")
                value = self.expression()
                self._close(")", opener)
                return Node("EvalExpression", start, self.prev_end, [value])
            if word not in NOT_NAMES:
                # a name in an expression position: a function, a constant or a member name
                self._advance()
                return Node("Name", token.start, token.end, text=self._text(token))
        raise self._unexpected(token)

    def _dynamic_variable(self) -> Node:
        start = self._advance().start
        if self._is_op("{"):
            self._advance()
            expression = self.expression()
            self._expect_op("}")
            return Node("DynamicVariable", start, self.prev_end, [expression])
        if self._is_op("$"):
            return Node("DynamicVariable", start, self.prev_end, [self._dynamic_variable()])
        if self.tok.kind == "variable":
            return Node("DynamicVariable", start, self.prev_end, [self._variable_token()])
        raise self._error(self.tok.start, f"expected a variable after '$', found {self._describe(self.tok)}")

    def _expression_from_primary(self, attributes: Optional[List[Node]] = None) -> Node:
        """A closure or arrow function (``function``, ``fn``, ``static`` before either)."""
        start = self.tok.start
        is_static = False
        if self._is_word("static"):
            self._advance()
            is_static = True
        if self._is_word("fn"):
            self._advance()
            by_ref = self._is_op("&")
            if by_ref:
                self._advance()
            parameters = self._parameters()
            return_type = self._return_type()
            self._expect_op("=>")
            body = self.expression(ASSIGN_PRECEDENCE)
            return Node("ArrowFunction", start, self.prev_end,
                        (attributes or []) + [parameters] + ([return_type] if return_type else []) + [body],
                        flags=_flags("static" if is_static else "", "ref" if by_ref else ""))
        self._expect_word("function")
        by_ref = self._is_op("&")
        if by_ref:
            self._advance()
        parameters = self._parameters()
        uses: List[Node] = []
        if self._is_word("use"):
            self._advance()
            opener = self._expect_op("(")
            while not self._is_op(")") and self.tok.kind != "eof":
                use_start = self.tok.start
                ref = self._is_op("&")
                if ref:
                    self._advance()
                uses.append(Node("ClosureUse", use_start, self.prev_end, [self._variable_token()],
                                 flags=_flags("ref" if ref else "")))
                if not self._separator(")"):
                    break
            self._close(")", opener)
        return_type = self._return_type()
        body = self._block()
        return Node("Closure", start, self.prev_end,
                    (attributes or []) + [parameters] + uses + ([return_type] if return_type else []) + [body],
                    flags=_flags("static" if is_static else "", "ref" if by_ref else ""))

    def _new(self) -> Node:
        start = self._advance().start
        if self._is_word("class"):
            self._advance()
            arguments = self._arguments() if self._is_op("(") else None
            children: List[Node] = [arguments] if arguments else []
            if self._is_word("extends"):
                self._advance()
                children.append(self._name())
            if self._is_word("implements"):
                self._advance()
                children.extend(self._names())
            children.append(self._class_body("class"))
            return Node("AnonymousClass", start, self.prev_end, children)
        if self._is_op("("):
            opener = self._advance()
            target = self.expression()
            self._close(")", opener)
        elif self.tok.kind == "variable":
            target = self._variable_token()
            while self._is_op("[") or self._is_op("->") or self._is_op("::"):
                if self._is_op("["):
                    opener = self._advance()
                    index = self.expression()
                    self._close("]", opener)
                    target = Node("IndexAccess", target.start, self.prev_end, [target, index])
                elif self._is_op("->"):
                    self._advance()
                    target = Node("PropertyAccess", target.start, self.prev_end, [target, self._property_member()])
                else:
                    self._advance()
                    target = Node("StaticProperty", target.start, self.prev_end, [target, self._variable_token()])
        elif self._is_name():
            target = self._name()
        else:
            raise self._error(self.tok.start, f"expected a class after 'new', found {self._describe(self.tok)}")
        arguments = self._arguments() if self._is_op("(") else None
        return Node("NewExpression", start, self.prev_end, [target] + ([arguments] if arguments else []))

    def _match(self) -> Node:
        start = self._advance().start
        subject = self._paren_expression("match")
        opener = self._expect_op("{")
        arms: List[Node] = [subject]
        while not self._is_op("}") and self.tok.kind != "eof":
            arm_start = self.tok.start
            conditions: List[Node] = []
            if self._is_word("default") and not self._is_op("(", self._at(1)):
                self._advance()
            else:
                conditions.append(self.expression())
                while self._is_op(","):
                    self._advance()
                    if self._is_op("=>"):
                        break
                    conditions.append(self.expression())
            self._expect_op("=>")
            value = self.expression()
            arms.append(Node("MatchArm", arm_start, self.prev_end, conditions + [value]))
            if not self._separator("}"):
                break
        self._close("}", opener)
        return Node("MatchExpression", start, self.prev_end, arms)

    def _array_construct(self, word: str) -> Node:
        start = self._advance().start
        if self._is_op("("):
            opener = self._advance()
            items = self._array_items(")")
            self._close(")", opener)
        else:
            raise self._error(self.tok.start, f"expected '(' after '{word}', found {self._describe(self.tok)}")
        return Node("ListLiteral" if word == "list" else "ArrayLiteral", start, self.prev_end, items)


def parse(source: str) -> Node:
    """Parse ``source`` as PHP. Raises :class:`ParseError` at the first error."""
    return _Parser(source).program()


def parse_partial(source: str) -> Tuple[Node, List[ParseError]]:
    """Parse ``source`` as far as it goes: the tree holds every statement and member that parsed, and the errors, in
    source order, say what did not. An analysis uses it, so that one broken statement keeps the rest of the file."""
    parser = _Parser(source, partial=True)
    tree = parser.program()
    return tree, sorted(parser.errors, key=lambda error: (error.line, error.column))
