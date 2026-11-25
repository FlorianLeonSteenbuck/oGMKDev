"""JavaScript parser for ECMAScript 2022, with JSX and, when typed, TypeScript: recursive descent, with
precise syntax errors.

It parses scripts and modules: var, let and const, functions (generators, async functions), classes
(fields, private names, static blocks, accessors), every statement, import and export, arrow
functions, destructuring with defaults and rest, spread, template literals with substitutions,
tagged templates, optional chaining, the nullish and logical assignments, ``**``, ``new.target``,
``import.meta``, dynamic ``import()``, ``await``, ``yield`` and JSX. With ``typed=True`` it also
reads TypeScript (see :mod:`ogmkdev.parsers.typescript`); JSX is read in JSX code (``jsx=True``).

The first error stops the parse. :class:`ParseError` gives the 1-based line and column of the token
where the error was found and a message that names it, for example ``missing ';' before identifier
'b'`` or ``expected ')' to match '(' on line 3 before ';'``. ``lexical`` tells a malformed token
(an unterminated string) from one that is out of place.

The tree is generic: :class:`Node` has a ``kind`` (``"Program"``, ``"BinaryExpression"``...), the
offsets of its text, its ``children``, a ``text`` (names, operators, literal text) and ``flags``
(``"parenthesized"``, ``"async"``, ``"computed"``, ...). Patterns and arrow parameters are made by
converting expressions that were parsed first (a cover grammar), so ``({a = 1}) => a`` and
``[a, b] = c`` need no second pass; typed code reads parameter lists directly where it must.

Leniencies, so that valid code never shows a false error: ``return`` at the top level (CommonJS
modules), ``with``, sloppy-mode names such as ``let`` and ``yield`` outside generators, and calls
as assignment targets (a run-time error in sloppy code). Scope checks, such as duplicate
declarations, are not made.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from ..lexers import ecmascript_lexer as L
from .jsx import JsxMixin
from .syntax import Node, ParseError, flags as _flags, position as _position
from .typescript import TypeMixin

__all__ = ["Node", "ParseError", "parse"]

RESERVED = frozenset("""
break case catch class const continue debugger default delete do else enum export extends false
finally for function if import in instanceof new null return super switch this throw true try
typeof var void while with
""".split())
# lexer keywords that are plain identifiers where the grammar does not use them as operators
CONTEXTUAL = frozenset("""
let static yield implements interface package private protected public
""".split())
ASSIGNMENT_OPERATORS = frozenset("""
= += -= *= /= %= **= <<= >>= >>>= &= |= ^= &&= ||= ??=
""".split())
BINARY_PRECEDENCE: Dict[str, int] = {
    "??": 1, "||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
    "==": 6, "!=": 6, "===": 6, "!==": 6,
    "<": 7, ">": 7, "<=": 7, ">=": 7, "instanceof": 7, "in": 7,
    "<<": 8, ">>": 8, ">>>": 8,
    "+": 9, "-": 9,
    "*": 10, "/": 10, "%": 10,
    "**": 11,
}
RELATIONAL_PRECEDENCE = 7
UNARY_WORDS = frozenset({"delete", "void", "typeof"})
UNARY_SIGNS = frozenset({"+", "-", "!", "~"})
UPDATE_OPERATORS = frozenset({"++", "--"})
YIELD_ENDS = frozenset({")", "]", "}", ",", ";", ":"})
REGEXP_FLAGS = frozenset("dgimsuvy")
SHORTHAND_INITIALIZER = "invalid shorthand property initializer"


@dataclass
class _Frame:
    """The function (or the top level) that the code being parsed is in."""
    is_async: bool = False                     # `await` is an operator
    is_generator: bool = False                 # `yield` is an operator
    super_ok: bool = False                     # `super.name` and `super(...)` are allowed
    labels: List[Tuple[str, bool]] = field(default_factory=list)  # (name, labels a loop)
    loops: int = 0                             # enclosing loops (for continue)
    breakable: int = 0                         # enclosing loops and switches (for break)


class _Parser(JsxMixin, TypeMixin):
    """One parse: the cursor (the current token and the end of the previous one), the function frame,
    and the shorthand initializers that wait for a pattern to claim them."""

    def __init__(self, source: str, typed: bool = False, jsx: bool = True) -> None:
        self.src = source
        self.typed = typed
        self.jsx = jsx
        self.ambient = 0                           # inside `declare`: no initializers, no bodies
        self.frame = _Frame(is_async=True)         # the top level: `await` is an operator
        self.covers: List[Tuple[int, str]] = []    # (offset, message) of {a = 1} awaiting a pattern
        self.prev_end = 0
        self.tok = self._scan_from(0)
        self._check(self.tok)

    # ----------------------------------------------------------------- tokens

    def _scan_from(self, position: int) -> L.Token:
        newline = False
        while True:
            token = L.scan_token(self.src, position, substitutions=True)
            if token.kind != "comment" or token.error:
                if newline and not token.newline_before:
                    token = replace(token, newline_before=True)
                return token
            newline = newline or token.newline_before
            position = token.end

    def _next(self) -> None:
        self.prev_end = self.tok.end
        self.tok = self._scan_from(self.tok.end)
        self._check(self.tok)

    def _peek(self) -> L.Token:
        return self._scan_from(self.tok.end)

    def _peek_is_punct(self, text: str) -> bool:
        following = self._peek()
        return following.kind == "punctuator" and self._text(following) == text

    def _peek_is_word(self, word: str) -> bool:
        following = self._peek()
        return following.kind == "keyword" and self._text(following) == word

    def _peek_is_name(self, name: str) -> bool:
        following = self._peek()
        return following.kind == "identifier" and self._text(following) == name

    def _peek_starts_name(self) -> bool:
        following = self._peek()
        return following.kind == "identifier" or (following.kind == "keyword" and self._text(following) in CONTEXTUAL)

    def _mark(self) -> Tuple[L.Token, int, int]:
        """The cursor, for a speculative reading that may have to be undone."""
        return self.tok, self.prev_end, len(self.covers)

    def _reset(self, mark: Tuple[L.Token, int, int]) -> None:
        self.tok, self.prev_end, covers = mark
        del self.covers[covers:]

    def _check(self, token: L.Token) -> None:
        if token.error:
            message = token.error
            if message == "unexpected character":
                message = f"unexpected character {self.src[token.start]!r}"
            line, column = _position(self.src, token.start)
            raise ParseError(line, column, message, lexical=True)

    def _text(self, token: Optional[L.Token] = None) -> str:
        token = self.tok if token is None else token
        return self.src[token.start:token.end]

    def _is_punct(self, text: str) -> bool:
        return self.tok.kind == "punctuator" and self._text() == text

    def _is_word(self, word: str) -> bool:
        return self.tok.kind == "keyword" and self._text() == word

    def _is_name(self, name: str) -> bool:
        """An identifier with this spelling, such as ``of``, ``from``, ``async`` or ``get``."""
        return self.tok.kind == "identifier" and self._text() == name

    def _is_binding_name(self) -> bool:
        if self.tok.kind == "identifier":
            return True
        return self.tok.kind == "keyword" and self._text() in CONTEXTUAL

    def _describe(self, token: L.Token) -> str:
        text = self._text(token)
        if token.kind == "eof":
            return "end of input"
        if token.kind == "identifier":
            return f"identifier '{text}'"
        if token.kind == "keyword":
            return f"keyword '{text}'"
        if token.kind == "number":
            return f"numeric literal {text}"
        if token.kind == "string":
            return "string literal"
        if token.kind in ("template", "template-open"):
            return "template literal"
        if token.kind == "regexp":
            return "regular expression"
        if token.kind == "private-name":
            return f"private name '{text}'"
        return f"'{text}'"

    def _error(self, offset: int, message: str) -> ParseError:
        line, column = _position(self.src, offset)
        return ParseError(line, column, message)

    def _lexical_error(self, offset: int, message: str) -> ParseError:
        line, column = _position(self.src, offset)
        return ParseError(line, column, message, lexical=True)

    def _unexpected(self, token: Optional[L.Token] = None) -> ParseError:
        token = self.tok if token is None else token
        if token.kind == "eof":
            return self._error(token.start, "unexpected end of input")
        return self._error(token.start, f"unexpected {self._describe(token)}")

    def _expect(self, text: str) -> None:
        if not self._is_punct(text):
            raise self._error(self.tok.start, f"expected '{text}' before {self._describe(self.tok)}")
        self._next()

    def _expect_word(self, word: str) -> None:
        if not self._is_word(word):
            raise self._error(self.tok.start, f"expected '{word}' before {self._describe(self.tok)}")
        self._next()

    def _expect_name(self, name: str) -> None:
        if not self._is_name(name):
            raise self._error(self.tok.start, f"expected '{name}' before {self._describe(self.tok)}")
        self._next()

    def _close(self, close: str, opener: L.Token) -> None:
        if self._is_punct(close):
            self._next()
            return
        line_open, _ = _position(self.src, opener.start)
        line_here, _ = _position(self.src, self.tok.start)
        where = f" to match '{self._text(opener)}' on line {line_open}" if line_open != line_here else ""
        raise self._error(self.tok.start, f"expected '{close}'{where} before {self._describe(self.tok)}")

    def _separator(self, close: str) -> bool:
        """Consume the comma between two list items. False when the list closes here."""
        if self._is_punct(","):
            self._next()
            return True
        if self._is_punct(close):
            return False
        raise self._error(self.tok.start, f"expected ',' or '{close}' before {self._describe(self.tok)}")

    def _semicolon(self) -> None:
        """A semicolon, or an automatic one before a line break, a closing brace or the end."""
        if self._is_punct(";"):
            self._next()
            return
        if self.tok.kind == "eof" or self._is_punct("}") or self.tok.newline_before:
            return
        raise self._error(self.tok.start, f"missing ';' before {self._describe(self.tok)}")

    # ----------------------------------------------------------- lookahead

    def _async_function_follows(self) -> bool:
        following = self._peek()
        return (following.kind == "keyword" and self._text(following) == "function"
                and not following.newline_before)

    def _async_arrow_follows(self) -> bool:
        following = self._peek()
        return following.kind == "identifier" and not following.newline_before

    def _let_declaration_follows(self) -> bool:
        following = self._peek()
        if following.kind == "identifier":
            return True
        if following.kind == "punctuator":
            return self._text(following) in ("[", "{")
        return following.kind == "keyword" and self._text(following) in CONTEXTUAL

    def _import_call_or_meta_follows(self) -> bool:
        following = self._peek()
        return following.kind == "punctuator" and self._text(following) in ("(", ".")

    def _modifier_follows(self, no_line_break: bool = False) -> bool:
        """After async, get, set or static: is it a modifier, followed by a name, or the name of a
        property that has punctuation after it?"""
        following = self._peek()
        if following.kind == "eof" or (no_line_break and following.newline_before):
            return False
        if following.kind == "punctuator":
            return self._text(following) in ("*", "[")
        return True

    def _typed_async_arrow(self, start: int) -> Optional[Node]:
        """``async (x: T) => ...`` and ``async <T>(x) => ...``: None when ``async`` is an identifier."""
        following = self._peek()
        if following.newline_before or following.kind != "punctuator" or self._text(following) not in ("(", "<"):
            return None
        mark = self._mark()
        self._next()  # async
        arrow = self._typed_arrow(start, True, False)
        if arrow is None:
            self._reset(mark)
        return arrow

    # ----------------------------------------------------------- frames, covers

    def _enter(self, frame: _Frame) -> _Frame:
        saved, self.frame = self.frame, frame
        return saved

    def _leave(self, saved: _Frame) -> None:
        self.frame = saved

    def _finish_covers(self, mark: int, cover: bool) -> None:
        """A shorthand initializer that no pattern claimed is an error where the expression ends."""
        if not cover and len(self.covers) > mark:
            offset, message = self.covers[mark]
            raise self._error(offset, message)

    # ----------------------------------------------------------- program and statements

    def program(self) -> Node:
        body: List[Node] = []
        while self.tok.kind != "eof":
            body.append(self._statement_list_item(top_level=True))
        return Node("Program", 0, len(self.src), body)

    def _statement_list_item(self, top_level: bool = False) -> Node:
        if self.typed:
            declaration = self._typed_statement(top_level)
            if declaration is not None:
                return declaration
        token = self.tok
        if token.kind == "keyword":
            word = self._text()
            if word == "function":
                return self._function(token.start, is_async=False, declaration=True)
            if word == "class":
                return self._class(token.start, declaration=True)
            if word == "const" or (word == "let" and self._let_declaration_follows()):
                return self._variable_statement(word)
            if word in ("import", "export") and not (word == "import" and self._import_call_or_meta_follows()):
                if not top_level:
                    raise self._error(token.start, f"'{word}' may only appear at the top level of a module")
                return self._import_declaration() if word == "import" else self._export_declaration()
        elif token.kind == "identifier" and self._text() == "async" and self._async_function_follows():
            self._next()
            return self._function(token.start, is_async=True, declaration=True)
        return self._statement()

    def _statement(self) -> Node:
        token = self.tok
        if token.kind == "punctuator":
            if self._is_punct("{"):
                return self._block()
            if self._is_punct(";"):
                self._next()
                return Node("EmptyStatement", token.start, token.end)
        elif token.kind == "keyword":
            word = self._text()
            if word == "var":
                return self._variable_statement(word)
            if word == "if":
                return self._if()
            if word == "for":
                return self._for()
            if word == "while":
                return self._while()
            if word == "do":
                return self._do_while()
            if word == "return":
                return self._return()
            if word in ("break", "continue"):
                return self._jump(word)
            if word == "throw":
                return self._throw()
            if word == "try":
                return self._try_statement()
            if word == "switch":
                return self._switch()
            if word == "with":
                return self._with()
            if word == "debugger":
                self._next()
                self._semicolon()
                return Node("DebuggerStatement", token.start, self.prev_end)
            if word == "function":  # a function declaration as the body of an `if` (sloppy code)
                return self._function(token.start, is_async=False, declaration=True)
            if word == "class":
                raise self._error(token.start, "a class declaration is not allowed here")
            if word == "const" or (word == "let" and self._let_declaration_follows()):
                raise self._error(token.start, f"lexical declaration '{word}' is not allowed here")
            if word in ("import", "export") and not (word == "import" and self._import_call_or_meta_follows()):
                raise self._error(token.start, f"'{word}' may only appear at the top level of a module")
        if self._is_binding_name() and self._peek_is_punct(":"):
            return self._labeled()
        return self._expression_statement()

    def _expression_statement(self) -> Node:
        start = self.tok.start
        expression = self._expression()
        self._semicolon()
        return Node("ExpressionStatement", start, self.prev_end, [expression])

    def _block(self) -> Node:
        opener = self.tok
        self._expect("{")
        body: List[Node] = []
        while not self._is_punct("}") and self.tok.kind != "eof":
            body.append(self._statement_list_item())
        self._close("}", opener)
        return Node("BlockStatement", opener.start, self.prev_end, body)

    def _variable_statement(self, kind: str) -> Node:
        start = self.tok.start
        self._next()
        declarators = self._declarators(kind, in_head=False, no_in=False)
        self._semicolon()
        return Node("VariableDeclaration", start, self.prev_end, declarators, text=kind)

    def _declarators(self, kind: str, in_head: bool, no_in: bool) -> List[Node]:
        declarators: List[Node] = []
        while True:
            target = self._binding_target("variable name")
            children = [target]
            if self.typed:
                if self._is_punct("!"):  # definite assignment: let x!: T
                    self._next()
                annotation = self._type_annotation()
                if annotation is not None:
                    children.append(annotation)
            initializer = False
            if self._is_punct("="):
                self._next()
                children.append(self._assignment(no_in=no_in))
                initializer = True
            elif not in_head and not self.ambient and not (self.typed and len(children) > 1):
                if target.kind != "Identifier":
                    raise self._error(target.start, "missing initializer in destructuring declaration")
                if kind == "const":
                    raise self._error(target.start, "missing initializer in const declaration")
            declarators.append(Node("VariableDeclarator", target.start, self.prev_end, children,
                                    flags=_flags("init" if initializer else "")))
            if not self._is_punct(","):
                return declarators
            self._next()

    # ----------------------------------------------------------- binding patterns

    def _binding_target(self, what: str) -> Node:
        if self._is_punct("["):
            return self._array_binding()
        if self._is_punct("{"):
            return self._object_binding()
        return self._binding_identifier(what)

    def _binding_identifier(self, what: str) -> Node:
        token = self.tok
        if not self._is_binding_name():
            raise self._error(token.start, f"expected {what}, found {self._describe(token)}")
        self._next()
        return Node("Identifier", token.start, token.end, text=self._text(token))

    def _binding_element(self, what: str) -> Node:
        target = self._binding_target(what)
        if not self._is_punct("="):
            return target
        self._next()
        default = self._assignment()
        return Node("AssignmentPattern", target.start, self.prev_end, [target, default])

    def _rest_binding(self, what: str) -> Node:
        start = self.tok.start
        self._next()  # ...
        target = self._binding_target(what)
        return Node("RestElement", start, self.prev_end, [target])

    def _array_binding(self) -> Node:
        opener = self.tok
        self._next()
        elements: List[Node] = []
        while not self._is_punct("]") and self.tok.kind != "eof":
            if self._is_punct(","):
                elements.append(Node("Elision", self.tok.start, self.tok.end))
                self._next()
                continue
            if self._is_punct("..."):
                elements.append(self._rest_binding("a name or a pattern"))
                if self._is_punct(","):
                    raise self._error(self.tok.start, "rest element must be last in a destructuring pattern")
                break
            elements.append(self._binding_element("a name or a pattern"))
            if not self._separator("]"):
                break
        self._close("]", opener)
        return Node("ArrayPattern", opener.start, self.prev_end, elements)

    def _object_binding(self) -> Node:
        opener = self.tok
        self._next()
        properties: List[Node] = []
        while not self._is_punct("}") and self.tok.kind != "eof":
            start = self.tok.start
            if self._is_punct("..."):
                properties.append(self._rest_binding("a name"))
                if self._is_punct(","):
                    raise self._error(self.tok.start, "rest element must be last in a destructuring pattern")
                break
            key, computed = self._property_key()
            flags = _flags("computed" if computed else "")
            if self._is_punct(":"):
                self._next()
                value = self._binding_element("a name or a pattern")
                properties.append(Node("Property", start, self.prev_end, [key, value], text="init", flags=flags))
            else:
                if computed or key.kind != "Identifier" or key.text in RESERVED:
                    raise self._error(self.tok.start, f"expected ':' before {self._describe(self.tok)}")
                shorthand = Node("Identifier", key.start, key.end, text=key.text)
                value = shorthand
                if self._is_punct("="):
                    self._next()
                    default = self._assignment()
                    value = Node("AssignmentPattern", key.start, self.prev_end, [shorthand, default])
                properties.append(Node("Property", start, self.prev_end, [key, value], text="init",
                                       flags=_flags("shorthand")))
            if not self._separator("}"):
                break
        self._close("}", opener)
        return Node("ObjectPattern", opener.start, self.prev_end, properties)

    def _property_key(self, allow_private: bool = False) -> Tuple[Node, bool]:
        """A property name: the key node and whether the name is computed (``[expression]``)."""
        token = self.tok
        if self._is_punct("["):
            self._next()
            expression = self._assignment()
            self._close("]", token)
            return expression, True
        if token.kind in ("identifier", "keyword"):
            self._next()
            return Node("Identifier", token.start, token.end, text=self._text(token)), False
        if token.kind in ("string", "number"):
            self._next()
            return Node("Literal", token.start, token.end, text=self._text(token)), False
        if token.kind == "private-name" and allow_private:
            self._next()
            return Node("PrivateName", token.start, token.end, text=self._text(token)), False
        raise self._error(token.start, f"expected a property name, found {self._describe(token)}")

    # ----------------------------------------------------------- control flow

    def _condition(self, word: str) -> Node:
        if not self._is_punct("("):
            raise self._error(self.tok.start, f"expected '(' after '{word}', found {self._describe(self.tok)}")
        opener = self.tok
        self._next()
        expression = self._expression()
        self._close(")", opener)
        return expression

    def _if(self) -> Node:
        start = self.tok.start
        self._next()
        test = self._condition("if")
        children = [test, self._statement()]
        if self._is_word("else"):
            self._next()
            children.append(self._statement())
        return Node("IfStatement", start, self.prev_end, children)

    def _loop_body(self) -> Node:
        frame = self.frame
        frame.loops += 1
        frame.breakable += 1
        body = self._statement()
        frame.loops -= 1
        frame.breakable -= 1
        return body

    def _while(self) -> Node:
        start = self.tok.start
        self._next()
        test = self._condition("while")
        body = self._loop_body()
        return Node("WhileStatement", start, self.prev_end, [test, body])

    def _do_while(self) -> Node:
        start = self.tok.start
        self._next()
        body = self._loop_body()
        if not self._is_word("while"):
            raise self._error(self.tok.start,
                              f"expected 'while' after the body of 'do', found {self._describe(self.tok)}")
        self._next()
        test = self._condition("while")
        if self._is_punct(";"):
            self._next()
        return Node("DoWhileStatement", start, self.prev_end, [body, test])

    def _empty_at(self, offset: int) -> Node:
        return Node("Empty", offset, offset)

    def _for(self) -> Node:
        start = self.tok.start
        self._next()
        is_await = self._is_name("await") and self.frame.is_async
        if is_await:
            self._next()
        opener = self.tok
        self._expect("(")
        mark = len(self.covers)
        init: Optional[Node] = None
        if self._is_word("var") or self._is_word("const") or (
                self._is_word("let") and self._let_declaration_follows()):
            kind = self._text()
            declaration_start = self.tok.start
            self._next()
            declarators = self._declarators(kind, in_head=True, no_in=True)
            head = Node("VariableDeclaration", declaration_start, self.prev_end, declarators, text=kind)
            if self._is_name("of") or self._is_word("in"):
                return self._for_in_of(start, opener, head, is_await)
            if kind == "const":
                for declarator in declarators:
                    if "init" not in declarator.flags:
                        raise self._error(declarator.start, "missing initializer in const declaration")
            init = head
        elif not self._is_punct(";"):
            init = self._expression(no_in=True, cover=True)
            if self._is_name("of") or self._is_word("in"):
                target = self._for_target(init, mark)
                return self._for_in_of(start, opener, target, is_await)
            self._finish_covers(mark, cover=False)
        self._expect(";")
        test = self._empty_at(self.prev_end) if self._is_punct(";") else self._expression()
        self._expect(";")
        update = self._empty_at(self.prev_end) if self._is_punct(")") else self._expression()
        self._close(")", opener)
        body = self._loop_body()
        if init is None:
            init = self._empty_at(opener.end)
        return Node("ForStatement", start, self.prev_end, [init, test, update, body])

    def _for_target(self, expression: Node, mark: int) -> Node:
        if expression.kind in ("ObjectLiteral", "ArrayLiteral") and "parenthesized" not in expression.flags:
            target = self._to_pattern(expression, binding=False)
            del self.covers[mark:]
            return target
        self._finish_covers(mark, cover=False)
        self._check_simple_target(expression, "for loop")
        return expression

    def _for_in_of(self, start: int, opener: L.Token, head: Node, is_await: bool) -> Node:
        word = self._text()
        self._next()
        right = self._assignment() if word == "of" else self._expression()
        self._close(")", opener)
        body = self._loop_body()
        kind = "ForOfStatement" if word == "of" else "ForInStatement"
        return Node(kind, start, self.prev_end, [head, right, body], flags=_flags("await" if is_await else ""))

    def _return(self) -> Node:
        start = self.tok.start
        self._next()
        children: List[Node] = []
        if not (self._is_punct(";") or self._is_punct("}") or self.tok.kind == "eof" or self.tok.newline_before):
            children.append(self._expression())
        self._semicolon()
        return Node("ReturnStatement", start, self.prev_end, children)

    def _jump(self, word: str) -> Node:
        start = self.tok.start
        self._next()
        label = ""
        if self._is_binding_name() and not self.tok.newline_before:
            token = self.tok
            label = self._text()
            self._next()
            matches = [is_loop for name, is_loop in self.frame.labels if name == label]
            if not matches:
                raise self._error(token.start, f"undefined label '{label}'")
            if word == "continue" and not matches[-1]:
                raise self._error(token.start, f"label '{label}' does not label a loop")
        elif word == "break" and self.frame.breakable == 0:
            raise self._error(start, "illegal break statement")
        elif word == "continue" and self.frame.loops == 0:
            raise self._error(start, "illegal continue statement: no enclosing loop")
        self._semicolon()
        kind = "BreakStatement" if word == "break" else "ContinueStatement"
        return Node(kind, start, self.prev_end, text=label)

    def _throw(self) -> Node:
        start = self.tok.start
        self._next()
        if self.tok.newline_before:
            raise self._error(self.tok.start, "illegal newline after 'throw'")
        argument = self._expression()
        self._semicolon()
        return Node("ThrowStatement", start, self.prev_end, [argument])

    def _try_statement(self) -> Node:
        start = self.tok.start
        self._next()
        children = [self._block()]
        if self._is_word("catch"):
            catch_start = self.tok.start
            self._next()
            parameters: List[Node] = []
            if self._is_punct("("):
                opener = self.tok
                self._next()
                parameters.append(self._binding_target("a catch parameter name"))
                self._close(")", opener)
            body = self._block()
            children.append(Node("CatchClause", catch_start, self.prev_end, parameters + [body]))
        if self._is_word("finally"):
            self._next()
            children.append(self._block())
        if len(children) == 1:
            raise self._error(self.tok.start, "expected 'catch' or 'finally' after the try block, found "
                                              f"{self._describe(self.tok)}")
        return Node("TryStatement", start, self.prev_end, children)

    def _switch(self) -> Node:
        start = self.tok.start
        self._next()
        discriminant = self._condition("switch")
        opener = self.tok
        self._expect("{")
        frame = self.frame
        frame.breakable += 1
        cases: List[Node] = [discriminant]
        has_default = False
        while not self._is_punct("}") and self.tok.kind != "eof":
            case_start = self.tok.start
            if self._is_word("case"):
                self._next()
                labels = [self._expression()]
            elif self._is_word("default"):
                if has_default:
                    raise self._error(self.tok.start, "more than one default clause in switch statement")
                has_default = True
                self._next()
                labels = []
            else:
                raise self._error(self.tok.start, f"expected 'case' or 'default', found {self._describe(self.tok)}")
            self._expect(":")
            body: List[Node] = []
            while not (self._is_word("case") or self._is_word("default") or self._is_punct("}")
                       or self.tok.kind == "eof"):
                body.append(self._statement_list_item())
            cases.append(Node("SwitchCase", case_start, self.prev_end, labels + body))
        frame.breakable -= 1
        self._close("}", opener)
        return Node("SwitchStatement", start, self.prev_end, cases)

    def _with(self) -> Node:
        start = self.tok.start
        self._next()
        subject = self._condition("with")
        body = self._statement()
        return Node("WithStatement", start, self.prev_end, [subject, body])

    def _labeled(self) -> Node:
        token = self.tok
        name = self._text()
        if any(existing == name for existing, _ in self.frame.labels):
            raise self._error(token.start, f"label '{name}' has already been declared")
        self._next()
        self._next()  # the colon
        is_loop = self.tok.kind == "keyword" and self._text() in ("for", "while", "do")
        self.frame.labels.append((name, is_loop))
        body = self._statement()
        self.frame.labels.pop()
        return Node("LabeledStatement", token.start, self.prev_end, [body], text=name)

    # ----------------------------------------------------------- modules

    def _module_source(self) -> Node:
        token = self.tok
        if token.kind != "string":
            raise self._error(token.start, f"expected a module name in quotes, found {self._describe(token)}")
        self._next()
        return Node("Literal", token.start, token.end, text=self._text(token))

    def _module_export_name(self) -> Node:
        token = self.tok
        if token.kind == "string":
            return self._module_source()
        if token.kind in ("identifier", "keyword"):
            self._next()
            return Node("Identifier", token.start, token.end, text=self._text(token))
        raise self._error(token.start, f"expected a name, found {self._describe(token)}")

    def _import_attributes(self) -> None:
        """The optional `with { ... }` clause (or the older `assert { ... }`): read, not checked."""
        if (self._is_word("with") or self._is_name("assert")) and not self.tok.newline_before:
            self._next()
            self._object_literal()

    def _named_specifiers(self, kind: str, imports: bool) -> List[Node]:
        opener = self.tok
        self._expect("{")
        specifiers: List[Node] = []
        while not self._is_punct("}") and self.tok.kind != "eof":
            start = self.tok.start
            spec_flags = _flags()
            if self.typed and self._is_name("type") and self._peek().kind in ("identifier", "keyword", "string"):
                self._next()  # `type` marks a type-only specifier
                spec_flags = _flags("type")
            first = self._module_export_name()
            second = first
            if self._is_name("as"):
                self._next()
                second = self._binding_identifier("an import name") if imports else self._module_export_name()
            elif imports and (first.kind != "Identifier" or first.text in RESERVED):
                raise self._error(first.start, f"{first.text} cannot be imported without 'as'")
            specifiers.append(Node(kind, start, self.prev_end, [first, second], flags=spec_flags))
            if not self._separator("}"):
                break
        self._close("}", opener)
        return specifiers

    def _import_declaration(self) -> Node:
        start = self.tok.start
        self._next()
        type_only = False
        if self.typed and self._is_name("type") and self._type_import_follows():
            self._next()
            type_only = True
        if self.typed and self._is_binding_name() and self._peek_is_punct("="):
            return self._import_equals(start, type_only)
        children: List[Node] = []
        if self.tok.kind == "string":
            children.append(self._module_source())
            self._import_attributes()
            self._semicolon()
            return Node("ImportDeclaration", start, self.prev_end, children, flags=_flags("type" if type_only else ""))
        if self._is_binding_name():
            local = self._binding_identifier("an import name")
            children.append(Node("ImportDefaultSpecifier", local.start, local.end, [local]))
            if self._is_punct(","):
                self._next()
        if self._is_punct("*"):
            star = self.tok.start
            self._next()
            self._expect_name("as")
            local = self._binding_identifier("a namespace import name")
            children.append(Node("ImportNamespaceSpecifier", star, self.prev_end, [local]))
        elif self._is_punct("{"):
            children.extend(self._named_specifiers("ImportSpecifier", imports=True))
        elif not children:
            raise self._error(self.tok.start, "expected a name, '*' or '{' after 'import', found "
                                              f"{self._describe(self.tok)}")
        self._expect_name("from")
        children.append(self._module_source())
        self._import_attributes()
        self._semicolon()
        return Node("ImportDeclaration", start, self.prev_end, children, flags=_flags("type" if type_only else ""))

    def _type_import_follows(self) -> bool:
        following = self._peek()
        if following.kind == "punctuator":
            return self._text(following) in ("{", "*")
        return following.kind in ("identifier", "keyword") and self._text(following) != "from"

    def _export_declaration(self) -> Node:
        start = self.tok.start
        self._next()
        if self.typed:
            if self._is_punct("="):
                self._next()
                expression = self._assignment()
                self._semicolon()
                return Node("ExportAssignment", start, self.prev_end, [expression])
            if self._is_name("as") and self._peek_is_name("namespace"):
                self._next()
                self._next()
                name = self._binding_identifier("a namespace name")
                self._semicolon()
                return Node("NamespaceExport", start, self.prev_end, [name])
            if self._is_word("import"):
                declaration = self._import_declaration()
                return Node("ExportNamedDeclaration", start, self.prev_end, [declaration])
        if self._is_word("default"):
            self._next()
            if self._is_word("function"):
                declaration = self._function(self.tok.start, is_async=False, declaration=True, name_optional=True)
            elif self._is_name("async") and self._async_function_follows():
                async_start = self.tok.start
                self._next()
                declaration = self._function(async_start, is_async=True, declaration=True, name_optional=True)
            elif self._is_word("class"):
                declaration = self._class(self.tok.start, declaration=True, name_optional=True)
            elif self.typed and self._is_word("interface"):
                declaration = self._interface(self.tok.start)
            else:
                declaration = self._assignment()
                self._semicolon()
            return Node("ExportDefaultDeclaration", start, self.prev_end, [declaration])
        type_only = False
        if self.typed and self._is_name("type") and (self._peek_is_punct("{") or self._peek_is_punct("*")):
            self._next()
            type_only = True
        if self._is_punct("*"):
            self._next()
            children: List[Node] = []
            if self._is_name("as"):
                self._next()
                children.append(self._module_export_name())
            self._expect_name("from")
            children.append(self._module_source())
            self._import_attributes()
            self._semicolon()
            return Node("ExportAllDeclaration", start, self.prev_end, children, flags=_flags("type" if type_only else ""))
        if self._is_punct("{"):
            specifiers = self._named_specifiers("ExportSpecifier", imports=False)
            if self._is_name("from"):
                self._next()
                specifiers.append(self._module_source())
                self._import_attributes()
            self._semicolon()
            return Node("ExportNamedDeclaration", start, self.prev_end, specifiers,
                        flags=_flags("type" if type_only else ""))
        if self.typed and self._typed_declaration_follows():
            declaration = self._statement_list_item(top_level=True)
            return Node("ExportNamedDeclaration", start, self.prev_end, [declaration])
        if (self._is_word("var") or self._is_word("const") or self._is_word("let") or self._is_word("function")
                or self._is_word("class") or (self._is_name("async") and self._async_function_follows())):
            declaration = self._statement_list_item(top_level=True)
            return Node("ExportNamedDeclaration", start, self.prev_end, [declaration])
        raise self._error(self.tok.start, "expected a declaration, '*' or '{' after 'export', found "
                                          f"{self._describe(self.tok)}")

    def _typed_declaration_follows(self) -> bool:
        token = self.tok
        if token.kind == "punctuator":
            return self._text() == "@"
        return token.kind in ("identifier", "keyword") and self._text() in (
            "interface", "type", "enum", "declare", "namespace", "module", "abstract", "const")

    # ----------------------------------------------------------- functions and classes

    def _function(self, start: int, is_async: bool, declaration: bool, name_optional: bool = False) -> Node:
        self._expect_word("function")
        generator = self._is_punct("*")
        if generator:
            self._next()
        children: List[Node] = []
        if self._is_binding_name():
            children.append(self._binding_identifier("a function name"))
        elif declaration and not name_optional:
            raise self._error(self.tok.start, f"expected a function name before {self._describe(self.tok)}")
        if self.typed and self._is_punct("<"):
            children.append(self._type_parameters())
        saved = self._enter(_Frame(is_async=is_async, is_generator=generator))
        children.append(self._formal_parameters())
        if self.typed:
            return_type = self._return_type()
            if return_type is not None:
                children.append(return_type)
        body = self._optional_body()
        self._leave(saved)
        if body is not None:
            children.append(body)
        kind = "FunctionDeclaration" if declaration else "FunctionExpression"
        return Node(kind, start, self.prev_end, children,
                    flags=_flags("async" if is_async else "", "generator" if generator else ""))

    def _parameter(self) -> Node:
        if self.typed:
            return self._typed_parameter()
        if self._is_punct("..."):
            return self._rest_binding("a parameter name")
        return self._binding_element("a parameter name")

    def _formal_parameters(self) -> Node:
        opener = self.tok
        self._expect("(")
        params: List[Node] = []
        while not self._is_punct(")") and self.tok.kind != "eof":
            param = self._parameter()
            params.append(param)
            if param.kind == "RestElement":
                if self._is_punct(","):
                    raise self._error(self.tok.start, "rest parameter must be last in a parameter list")
                break
            if not self._separator(")"):
                break
        self._close(")", opener)
        return Node("FormalParameters", opener.start, self.prev_end, params)

    def _function_body(self) -> Node:
        if not self._is_punct("{"):
            raise self._error(self.tok.start, f"expected '{{' before {self._describe(self.tok)}")
        return self._block()

    def _optional_body(self) -> Optional[Node]:
        """A body, or in typed code the semicolon of an overload or an ambient declaration."""
        if self.typed and not self._is_punct("{"):
            self._semicolon()
            return None
        return self._function_body()

    def _method(self, start: int, is_async: bool, generator: bool) -> Node:
        children: List[Node] = []
        if self.typed and self._is_punct("<"):
            children.append(self._type_parameters())
        saved = self._enter(_Frame(is_async=is_async, is_generator=generator, super_ok=True))
        children.append(self._formal_parameters())
        if self.typed:
            return_type = self._return_type()
            if return_type is not None:
                children.append(return_type)
        body = self._optional_body()
        self._leave(saved)
        if body is not None:
            children.append(body)
        return Node("FunctionExpression", start, self.prev_end, children, text="method",
                    flags=_flags("async" if is_async else "", "generator" if generator else ""))

    def _check_accessor(self, accessor: str, method: Node, key: Node) -> None:
        parameters = next(child for child in method.children if child.kind == "FormalParameters")
        count = len(parameters.children)
        if accessor == "get" and count:
            raise self._error(key.start, "getter must not have any parameters")
        if accessor == "set" and count != 1:
            raise self._error(key.start, "setter must have exactly one parameter")

    def _class(self, start: int, declaration: bool, name_optional: bool = False) -> Node:
        self._expect_word("class")
        children: List[Node] = []
        if self._is_binding_name():
            children.append(self._binding_identifier("a class name"))
        elif declaration and not name_optional:
            raise self._error(self.tok.start, f"expected a class name before {self._describe(self.tok)}")
        if self.typed and self._is_punct("<"):
            children.append(self._type_parameters())
        if self._is_word("extends"):
            self._next()
            children.append(self._call_expression())
            if self.typed and self._is_punct("<"):
                children.append(self._type_arguments())
        if self.typed and self._is_word("implements"):
            self._next()
            children.append(self._type_reference())
            while self._is_punct(","):
                self._next()
                children.append(self._type_reference())
        opener = self.tok
        self._expect("{")
        constructors = 0
        while not self._is_punct("}") and self.tok.kind != "eof":
            if self._is_punct(";"):
                self._next()
                continue
            member = self._class_member()
            has_body = any(child.kind == "BlockStatement" for child in member.children[-1].children)
            if member.text == "constructor" and has_body:  # overload signatures have no body
                constructors += 1
                if constructors > 1:
                    raise self._error(member.start, "a class may only have one constructor")
            children.append(member)
        self._close("}", opener)
        kind = "ClassDeclaration" if declaration else "ClassExpression"
        return Node(kind, start, self.prev_end, children)

    def _class_member(self) -> Node:
        start = self.tok.start
        if self.typed and self._is_punct("@"):
            decorators = self._decorators()
            member = self._class_member()
            return Node("Decorated", start, self.prev_end, decorators + [member])
        is_static = False
        if self._is_word("static"):
            following = self._peek()
            if following.kind == "punctuator" and self._text(following) == "{":
                self._next()
                return self._static_block(start)
            if self._modifier_follows():
                is_static = True
                self._next()
        modifiers: List[str] = []
        if self.typed:
            while self.tok.kind in ("identifier", "keyword") and self._text() in _MEMBER_MODIFIERS \
                    and self._modifier_follows():
                modifiers.append(self._text())
                self._next()
            is_static = is_static or "static" in modifiers
        is_async = False
        if self._is_name("async") and self._modifier_follows(no_line_break=True):
            is_async = True
            self._next()
        generator = self._is_punct("*")
        if generator:
            self._next()
        accessor = ""
        if not is_async and not generator and (self._is_name("get") or self._is_name("set")) \
                and self._modifier_follows():
            accessor = self._text()
            self._next()
        if self.typed and self._is_punct("[") and self._looks(self._index_signature_head):
            index = self._index_signature(start, readonly="readonly" in modifiers)
            self._semicolon()
            return index
        key, computed = self._property_key(allow_private=True)
        optional = definite = False
        if self.typed:
            if self._is_punct("?"):
                optional = True
                self._next()
            elif self._is_punct("!"):
                definite = True
                self._next()
        member_flags = _flags(*modifiers, "static" if is_static else "", "computed" if computed else "",
                              "optional" if optional else "", "definite" if definite else "")
        if self._is_punct("(") or (self.typed and self._is_punct("<")):
            method = self._method(start, is_async, generator)
            self._check_accessor(accessor, method, key)
            constructor = (not is_static and not computed and not accessor and not is_async and not generator
                           and self._static_name(key) == "constructor")
            text = "constructor" if constructor else (accessor or "method")
            return Node("MethodDefinition", start, self.prev_end, [key, method], text=text, flags=member_flags)
        if accessor or is_async or generator:
            raise self._error(self.tok.start, f"expected '(' after the method name before {self._describe(self.tok)}")
        allowed = ("=", ";", "}", ":") if self.typed else ("=", ";", "}")
        if not (self.tok.kind == "eof" or self.tok.newline_before
                or (self.tok.kind == "punctuator" and self._text() in allowed)):
            raise self._error(self.tok.start, "expected '(' or '=' after the class member name before "
                                              f"{self._describe(self.tok)}")
        children = [key]
        if self.typed:
            annotation = self._type_annotation()
            if annotation is not None:
                children.append(annotation)
        if self._is_punct("="):
            self._next()
            saved = self._enter(_Frame(super_ok=True))
            children.append(self._assignment())
            self._leave(saved)
        self._semicolon()
        return Node("FieldDefinition", start, self.prev_end, children, flags=member_flags)

    @staticmethod
    def _static_name(key: Node) -> str:
        if key.kind == "Identifier":
            return key.text
        if key.kind == "Literal" and key.text[:1] in ("'", '"'):
            return key.text[1:-1]
        return ""

    def _static_block(self, start: int) -> Node:
        saved = self._enter(_Frame(super_ok=True))
        body = self._block()
        self._leave(saved)
        return Node("StaticBlock", start, self.prev_end, [body])

    # ----------------------------------------------------------- expressions

    def _expression(self, no_in: bool = False, cover: bool = False) -> Node:
        first = self._assignment(no_in=no_in, cover=cover)
        if not self._is_punct(","):
            return first
        items = [first]
        while self._is_punct(","):
            self._next()
            items.append(self._assignment(no_in=no_in, cover=cover))
        return Node("SequenceExpression", first.start, self.prev_end, items)

    def _assignment(self, no_in: bool = False, cover: bool = False) -> Node:
        """An assignment expression. ``cover`` says that the caller may still turn the result into a
        pattern (an array or object element, a parenthesized list, the arguments of ``async(...)``)."""
        token = self.tok
        mark = len(self.covers)
        if self._is_word("yield") and self.frame.is_generator:
            return self._yield(no_in)
        if self._is_name("async") and self._async_arrow_follows():
            self._next()
            parameter = self._binding_identifier("a parameter name")
            if not self._is_punct("=>") or self.tok.newline_before:
                raise self._error(self.tok.start, f"expected '=>' after 'async {parameter.text}' before "
                                                  f"{self._describe(self.tok)}")
            return self._arrow_body(token.start, [parameter], True, no_in)
        left = self._conditional(no_in)
        if self._is_punct("=>"):
            return self._arrow_from(left, mark, no_in)
        if self.tok.kind == "punctuator" and self._text() in ASSIGNMENT_OPERATORS:
            operator = self._text()
            if operator == "=" and left.kind in ("ObjectLiteral", "ArrayLiteral") and "parenthesized" not in left.flags:
                left = self._to_pattern(left, binding=False)
                del self.covers[mark:]
            else:
                self._check_simple_target(left, "assignment")
            self._next()
            right = self._assignment(no_in=no_in)
            return Node("AssignmentExpression", left.start, self.prev_end, [left, right], text=operator)
        self._finish_covers(mark, cover)
        return left

    def _yield(self, no_in: bool) -> Node:
        token = self.tok
        self._next()
        delegate = False
        children: List[Node] = []
        if self._is_punct("*") and not self.tok.newline_before:
            delegate = True
            self._next()
            children.append(self._assignment(no_in=no_in))
        elif (not self.tok.newline_before and self.tok.kind != "eof"
              and not (self.tok.kind == "punctuator" and self._text() in YIELD_ENDS)):
            children.append(self._assignment(no_in=no_in))
        return Node("YieldExpression", token.start, self.prev_end, children,
                    flags=_flags("delegate" if delegate else ""))

    def _arrow_from(self, left: Node, mark: int, no_in: bool) -> Node:
        arrow = self.tok
        if arrow.newline_before:
            raise self._error(arrow.start, "unexpected line break before '=>'")
        is_async = False
        if left.kind == "Identifier" and "parenthesized" not in left.flags:
            params = [left]
        elif left.kind == "CoverParenthesized":
            params = [self._to_param(item) for item in left.children]
        elif (left.kind == "CallExpression" and left.children[0].kind == "Identifier"
              and left.children[0].text == "async" and "parenthesized" not in left.children[0].flags):
            is_async = True
            params = [self._to_param(item) for item in left.children[1].children]
        else:
            raise self._error(left.start, "invalid parameter list before '=>'")
        del self.covers[mark:]
        return self._arrow_body(left.start, params, is_async, no_in)

    def _arrow_body(self, start: int, params: List[Node], is_async: bool, no_in: bool,
                    prefix: Optional[List[Node]] = None) -> Node:
        """The body of an arrow function; the cursor is on its '=>'. ``prefix`` holds the type
        parameters and return type of a typed arrow function."""
        self._expect("=>")
        saved = self._enter(_Frame(is_async=is_async, super_ok=self.frame.super_ok))
        body = self._block() if self._is_punct("{") else self._assignment(no_in=no_in)
        self._leave(saved)
        end = params[-1].end if params else start
        formal = Node("FormalParameters", start, end, params)
        return Node("ArrowFunction", start, self.prev_end, [formal] + (prefix or []) + [body],
                    flags=_flags("async" if is_async else ""))

    def _to_param(self, node: Node) -> Node:
        if node.kind == "SpreadElement":
            return Node("RestElement", node.start, node.end, [self._to_pattern(node.children[0], binding=True)])
        return self._to_pattern(node, binding=True)

    def _to_pattern(self, node: Node, binding: bool) -> Node:
        """Turn an expression into a pattern: a parameter (``binding``) or an assignment target."""
        kind = node.kind
        parenthesized = "parenthesized" in node.flags
        if kind == "Identifier":
            if binding and parenthesized:
                raise self._error(node.start, "invalid parameter: a name in parentheses cannot be bound")
            return node
        if kind == "MemberExpression" and not binding and "optional" not in node.flags:
            return node
        if kind in ("ObjectPattern", "ArrayPattern", "AssignmentPattern", "RestElement"):
            return node
        if kind == "AssignmentExpression" and node.text == "=":
            target = self._to_pattern(node.children[0], binding)
            return Node("AssignmentPattern", node.start, node.end, [target, node.children[1]])
        if kind == "ArrayLiteral" and not parenthesized:
            return self._array_pattern(node, binding)
        if kind == "ObjectLiteral" and not parenthesized:
            return self._object_pattern(node, binding)
        raise self._error(node.start, "invalid parameter" if binding else "invalid destructuring assignment target")

    def _array_pattern(self, node: Node, binding: bool) -> Node:
        items: List[Node] = []
        last = len(node.children) - 1
        for index, element in enumerate(node.children):
            if element.kind == "Elision":
                items.append(element)
            elif element.kind == "SpreadElement":
                if index != last:
                    raise self._error(element.start, "rest element must be last in a destructuring pattern")
                target = self._to_pattern(element.children[0], binding)
                items.append(Node("RestElement", element.start, element.end, [target]))
            else:
                items.append(self._to_pattern(element, binding))
        return Node("ArrayPattern", node.start, node.end, items)

    def _object_pattern(self, node: Node, binding: bool) -> Node:
        items: List[Node] = []
        last = len(node.children) - 1
        for index, prop in enumerate(node.children):
            if prop.kind == "SpreadElement":
                if index != last:
                    raise self._error(prop.start, "rest element must be last in a destructuring pattern")
                target = self._to_pattern(prop.children[0], binding)
                items.append(Node("RestElement", prop.start, prop.end, [target]))
            elif prop.kind == "Property" and prop.text == "init":
                key, value = prop.children
                if "shorthand" in prop.flags:
                    items.append(prop)
                else:
                    target = self._to_pattern(value, binding)
                    items.append(Node("Property", prop.start, prop.end, [key, target], text="init", flags=prop.flags))
            else:
                raise self._error(prop.start, "invalid destructuring assignment target")
        return Node("ObjectPattern", node.start, node.end, items)

    def _conditional(self, no_in: bool) -> Node:
        test = self._binary(1, no_in)
        if not self._is_punct("?"):
            return test
        self._next()
        consequent = self._assignment()
        self._expect(":")
        alternate = self._assignment(no_in=no_in)
        return Node("ConditionalExpression", test.start, self.prev_end, [test, consequent, alternate])

    def _binary(self, min_precedence: int, no_in: bool) -> Node:
        left = self._unary()
        while True:
            token = self.tok
            if self.typed and token.kind == "identifier" and self._text() in ("as", "satisfies") \
                    and not token.newline_before and min_precedence <= RELATIONAL_PRECEDENCE:
                left = self._type_cast(left)
                continue
            if token.kind not in ("punctuator", "keyword"):
                return left
            operator = self._text()
            precedence = BINARY_PRECEDENCE.get(operator)
            if precedence is None or precedence < min_precedence or (operator == "in" and no_in):
                return left
            if operator == "**" and left.kind in ("UnaryExpression", "AwaitExpression") and \
                    "parenthesized" not in left.flags:
                raise self._error(token.start, "unary operator before '**' needs parentheses")
            self._next()
            right = self._binary(precedence if operator == "**" else precedence + 1, no_in)
            self._check_nullish_mix(operator, left, right, token)
            kind = "LogicalExpression" if operator in ("||", "&&", "??") else "BinaryExpression"
            left = Node(kind, left.start, self.prev_end, [left, right], text=operator)

    @staticmethod
    def _is_unparenthesized_logical(node: Node, operators: Tuple[str, ...]) -> bool:
        return node.kind == "LogicalExpression" and node.text in operators and "parenthesized" not in node.flags

    def _check_nullish_mix(self, operator: str, left: Node, right: Node, token: L.Token) -> None:
        if operator == "??":
            mixed = (self._is_unparenthesized_logical(left, ("||", "&&"))
                     or self._is_unparenthesized_logical(right, ("||", "&&")))
        elif operator in ("||", "&&"):
            mixed = (self._is_unparenthesized_logical(left, ("??",))
                     or self._is_unparenthesized_logical(right, ("??",)))
        else:
            mixed = False
        if mixed:
            raise self._error(token.start, "'??' cannot be mixed with '||' or '&&' without parentheses")

    def _unary(self) -> Node:
        token = self.tok
        text = self._text()
        if (token.kind == "keyword" and text in UNARY_WORDS) or (token.kind == "punctuator" and text in UNARY_SIGNS):
            self._next()
            operand = self._unary()
            return Node("UnaryExpression", token.start, self.prev_end, [operand], text=text)
        if token.kind == "punctuator" and text in UPDATE_OPERATORS:
            self._next()
            operand = self._unary()
            self._check_simple_target(operand, "prefix operation")
            return Node("UpdateExpression", token.start, self.prev_end, [operand], text=text,
                        flags=_flags("prefix"))
        if self._is_name("await") and self.frame.is_async:
            self._next()
            operand = self._unary()
            return Node("AwaitExpression", token.start, self.prev_end, [operand])
        expression = self._call_expression()
        following = self.tok
        if (following.kind == "punctuator" and self._text() in UPDATE_OPERATORS
                and not following.newline_before and expression.kind != "CoverParenthesized"):
            operator = self._text()
            self._check_simple_target(expression, "postfix operation")
            self._next()
            return Node("UpdateExpression", expression.start, self.prev_end, [expression], text=operator)
        return expression

    def _check_simple_target(self, node: Node, what: str) -> None:
        """Identifiers and member expressions are targets. Calls are accepted: sloppy code fails only
        when they run."""
        if node.kind in ("Identifier", "MemberExpression", "CallExpression") and "optional" not in node.flags:
            return
        raise self._error(node.start, f"invalid left-hand side in {what}")

    def _call_expression(self) -> Node:
        if self._is_word("new"):
            expression = self._new_expression()
        elif self._is_word("super"):
            expression = self._super()
        elif self._is_word("import"):
            expression = self._import_expression()
        else:
            expression = self._primary()
        if expression.kind == "CoverParenthesized":
            return expression
        return self._member_tail(expression, allow_call=True)

    def _super(self) -> Node:
        token = self.tok
        self._next()
        if not self.frame.super_ok:
            raise self._error(token.start, "'super' keyword unexpected here")
        if not (self._is_punct(".") or self._is_punct("[") or self._is_punct("(")):
            raise self._error(self.tok.start, f"expected '.', '[' or '(' after 'super' before {self._describe(self.tok)}")
        return Node("Super", token.start, token.end, text="super")

    def _new_expression(self) -> Node:
        token = self.tok
        self._next()
        if self._is_punct("."):
            self._next()
            if not self._is_name("target"):
                raise self._error(self.tok.start, f"expected 'target' after 'new.' before {self._describe(self.tok)}")
            self._next()
            return Node("MetaProperty", token.start, self.prev_end, text="new.target")
        if self._is_word("new"):
            callee = self._new_expression()
        elif self._is_word("super"):
            callee = self._super()
        elif self._is_word("import"):
            raise self._error(self.tok.start, "'new' cannot be used with 'import'")
        else:
            callee = self._primary()
        callee = self._member_tail(callee, allow_call=False)
        children = [callee]
        if self.typed and self._is_punct("<"):
            type_arguments = self._try(self._type_arguments)
            if type_arguments is not None:
                children.append(type_arguments)
        if self._is_punct("("):
            children.append(self._arguments())
        return Node("NewExpression", token.start, self.prev_end, children)

    def _import_expression(self) -> Node:
        token = self.tok
        self._next()
        if self._is_punct("."):
            self._next()
            if not self._is_name("meta"):
                raise self._error(self.tok.start, f"expected 'meta' after 'import.' before {self._describe(self.tok)}")
            self._next()
            return Node("MetaProperty", token.start, self.prev_end, text="import.meta")
        if not self._is_punct("("):
            raise self._error(token.start, "'import' needs import(...) or import.meta here")
        arguments = self._arguments()
        return Node("ImportCall", token.start, self.prev_end, [arguments])

    def _member_tail(self, expression: Node, allow_call: bool) -> Node:
        in_chain = False  # inside an optional chain
        while True:
            token = self.tok
            if token.kind in ("template", "template-open"):
                if in_chain:
                    raise self._error(token.start, "a tagged template cannot be used in an optional chain")
                template = self._template()
                expression = Node("TaggedTemplate", expression.start, self.prev_end, [expression, template])
                continue
            if token.kind != "punctuator":
                return expression
            text = self._text()
            if text == ".":
                self._next()
                expression = self._member_name(expression, optional=False)
            elif text == "?.":
                if not allow_call:
                    return expression
                in_chain = True
                self._next()
                if self._is_punct("("):
                    arguments = self._arguments()
                    expression = Node("CallExpression", expression.start, self.prev_end,
                                      [expression, arguments], flags=_flags("optional"))
                elif self._is_punct("["):
                    bracket = self.tok
                    self._next()
                    index = self._expression()
                    self._close("]", bracket)
                    expression = Node("MemberExpression", expression.start, self.prev_end, [expression, index],
                                      flags=_flags("computed", "optional"))
                else:
                    expression = self._member_name(expression, optional=True)
            elif text == "[":
                self._next()
                index = self._expression()
                self._close("]", token)
                expression = Node("MemberExpression", expression.start, self.prev_end, [expression, index],
                                  flags=_flags("computed"))
            elif text == "(" and allow_call:
                cover = (expression.kind == "Identifier" and expression.text == "async"
                         and "parenthesized" not in expression.flags and not token.newline_before)
                arguments = self._arguments(cover=cover)
                expression = Node("CallExpression", expression.start, self.prev_end, [expression, arguments])
            elif text == "!" and self.typed and not token.newline_before:
                self._next()  # non-null assertion: value!
                expression = Node("NonNullExpression", expression.start, self.prev_end, [expression])
            elif text == "<" and self.typed and allow_call:
                type_arguments = self._try(self._call_type_arguments)
                if type_arguments is None:
                    return expression
                if self._is_punct("("):
                    arguments = self._arguments()
                    expression = Node("CallExpression", expression.start, self.prev_end,
                                      [expression, type_arguments, arguments])
                else:
                    template = self._template()
                    expression = Node("TaggedTemplate", expression.start, self.prev_end,
                                      [expression, type_arguments, template])
            else:
                return expression

    def _member_name(self, expression: Node, optional: bool) -> Node:
        token = self.tok
        if token.kind not in ("identifier", "keyword", "private-name"):
            dot = "?." if optional else "."
            raise self._error(token.start, f"expected a property name after '{dot}', found {self._describe(token)}")
        self._next()
        kind = "PrivateName" if token.kind == "private-name" else "Identifier"
        name = Node(kind, token.start, token.end, text=self._text(token))
        return Node("MemberExpression", expression.start, self.prev_end, [expression, name],
                    flags=_flags("optional" if optional else ""))

    def _arguments(self, cover: bool = False) -> Node:
        opener = self.tok
        self._expect("(")
        args: List[Node] = []
        while not self._is_punct(")") and self.tok.kind != "eof":
            if self._is_punct("..."):
                start = self.tok.start
                self._next()
                argument = self._assignment(cover=cover)
                args.append(Node("SpreadElement", start, self.prev_end, [argument]))
            else:
                args.append(self._assignment(cover=cover))
            if not self._separator(")"):
                break
        self._close(")", opener)
        return Node("Arguments", opener.start, self.prev_end, args)

    def _primary(self) -> Node:
        token = self.tok
        kind = token.kind
        text = self._text()
        if kind == "identifier":
            if text == "async" and self.typed:
                arrow = self._typed_async_arrow(token.start)
                if arrow is not None:
                    return arrow
            if text == "async" and self._async_function_follows():
                self._next()
                return self._function(token.start, is_async=True, declaration=False, name_optional=True)
            self._next()
            return Node("Identifier", token.start, token.end, text=text)
        if kind == "keyword":
            if text in CONTEXTUAL:
                self._next()
                return Node("Identifier", token.start, token.end, text=text)
            if text == "this":
                self._next()
                return Node("ThisExpression", token.start, token.end, text=text)
            if text in ("null", "true", "false"):
                self._next()
                return Node("Literal", token.start, token.end, text=text)
            if text == "function":
                return self._function(token.start, is_async=False, declaration=False, name_optional=True)
            if text == "class":
                return self._class(token.start, declaration=False, name_optional=True)
        elif kind == "number":
            following = self.src[token.end:token.end + 1]
            if following and (following.isalnum() or following in "_$"):
                raise self._error(token.end, "identifier starts immediately after a numeric literal")
            self._next()
            return Node("Literal", token.start, token.end, text=text)
        elif kind == "string":
            self._next()
            return Node("Literal", token.start, token.end, text=text)
        elif kind in ("template", "template-open"):
            return self._template()
        elif kind == "private-name":
            self._next()
            if not self._is_word("in"):
                raise self._unexpected(token)
            return Node("PrivateName", token.start, token.end, text=text)
        elif kind == "punctuator":
            if text == "(":
                if self.typed:
                    arrow = self._typed_arrow(token.start, False, False)
                    if arrow is not None:
                        return arrow
                return self._parenthesized()
            if text == "[":
                return self._array_literal()
            if text == "{":
                return self._object_literal()
            if text in ("/", "/="):
                return self._regexp_literal()
            if text == "<":
                return self._angle_expression()
        raise self._unexpected()

    def _regexp_literal(self) -> Node:
        start = self.tok.start
        end, error = L._scan_regexp(self.src, start)
        if error:
            raise self._lexical_error(start, error)
        flags = self.src[self.src.rfind("/", start + 1, end) + 1:end]
        if len(set(flags)) != len(flags) or not set(flags) <= REGEXP_FLAGS:
            raise self._error(start, "invalid regular expression flags")
        self.tok = replace(self.tok, kind="regexp", end=end)
        node = Node("RegExpLiteral", start, end, text=self.src[start:end])
        self._next()
        return node

    def _template(self) -> Node:
        first = self.tok
        expressions: List[Node] = []
        while True:
            self._check(self.tok)
            if self.tok.kind == "template":
                self._next()
                break
            self._next()  # past the `${`
            expressions.append(self._expression())
            if not self._is_punct("}"):
                raise self._error(self.tok.start, "expected '}' to close the template substitution before "
                                                  f"{self._describe(self.tok)}")
            self.tok = L.scan_template_continuation(self.src, self.tok.start)
        return Node("TemplateLiteral", first.start, self.prev_end, expressions)

    def _parenthesized(self) -> Node:
        """A parenthesized expression, or the parameter list of an arrow function, which is decided by
        the ``=>`` after the closing parenthesis."""
        opener = self.tok
        mark = len(self.covers)
        self._next()
        items: List[Node] = []
        trailing_comma = False
        rest = False
        while not self._is_punct(")") and self.tok.kind != "eof":
            if self._is_punct("..."):
                items.append(self._rest_binding("a parameter name"))
                rest = True
                if self._is_punct(","):
                    raise self._error(self.tok.start, "rest parameter must be last in a parameter list")
                break
            items.append(self._assignment(cover=True))
            if self._is_punct(","):
                self._next()
                trailing_comma = self._is_punct(")")
                continue
            break
        self._close(")", opener)
        if self._is_punct("=>"):
            return Node("CoverParenthesized", opener.start, self.prev_end, items)
        if not items:
            raise self._error(opener.start, "expected '=>' after '()'")
        if rest or trailing_comma:
            raise self._error(opener.start, "expected '=>' after this parameter list")
        self._finish_covers(mark, cover=False)
        expression = items[0] if len(items) == 1 else Node("SequenceExpression", items[0].start,
                                                           items[-1].end, items)
        expression.flags = expression.flags | _flags("parenthesized")
        return expression

    def _array_literal(self) -> Node:
        opener = self.tok
        self._expect("[")
        elements: List[Node] = []
        while not self._is_punct("]") and self.tok.kind != "eof":
            if self._is_punct(","):
                elements.append(Node("Elision", self.tok.start, self.tok.end))
                self._next()
                continue
            if self._is_punct("..."):
                start = self.tok.start
                self._next()
                argument = self._assignment(cover=True)
                elements.append(Node("SpreadElement", start, self.prev_end, [argument]))
            else:
                elements.append(self._assignment(cover=True))
            if not self._separator("]"):
                break
        self._close("]", opener)
        return Node("ArrayLiteral", opener.start, self.prev_end, elements)

    def _object_literal(self) -> Node:
        opener = self.tok
        self._expect("{")
        properties: List[Node] = []
        while not self._is_punct("}") and self.tok.kind != "eof":
            if self._is_punct("..."):
                start = self.tok.start
                self._next()
                argument = self._assignment(cover=True)
                properties.append(Node("SpreadElement", start, self.prev_end, [argument]))
            else:
                properties.append(self._object_property())
            if not self._separator("}"):
                break
        self._close("}", opener)
        return Node("ObjectLiteral", opener.start, self.prev_end, properties)

    def _object_property(self) -> Node:
        start = self.tok.start
        is_async = False
        if self._is_name("async") and self._modifier_follows(no_line_break=True):
            is_async = True
            self._next()
        generator = self._is_punct("*")
        if generator:
            self._next()
        accessor = ""
        if not is_async and not generator and (self._is_name("get") or self._is_name("set")) \
                and self._modifier_follows():
            accessor = self._text()
            self._next()
        key, computed = self._property_key()
        property_flags = _flags("computed" if computed else "")
        if self._is_punct("(") or (self.typed and self._is_punct("<")):
            method = self._method(start, is_async, generator)
            self._check_accessor(accessor, method, key)
            return Node("Property", start, self.prev_end, [key, method], text=accessor or "method",
                        flags=property_flags)
        if is_async or generator or accessor:
            raise self._error(self.tok.start, f"expected '(' after the method name before {self._describe(self.tok)}")
        if self._is_punct(":"):
            self._next()
            value = self._assignment(cover=True)
            return Node("Property", start, self.prev_end, [key, value], text="init", flags=property_flags)
        if computed or key.kind != "Identifier" or key.text in RESERVED:
            raise self._error(self.tok.start, f"expected ':' before {self._describe(self.tok)}")
        shorthand = Node("Identifier", key.start, key.end, text=key.text)
        if self._is_punct("="):
            equals = self.tok
            self._next()
            default = self._assignment()
            self.covers.append((equals.start, SHORTHAND_INITIALIZER))
            value = Node("AssignmentPattern", key.start, self.prev_end, [shorthand, default])
            return Node("Property", start, self.prev_end, [key, value], text="init", flags=_flags("shorthand"))
        return Node("Property", start, self.prev_end, [key, shorthand], text="init", flags=_flags("shorthand"))


_MEMBER_MODIFIERS = frozenset({"public", "private", "protected", "readonly", "abstract", "override",
                               "declare", "accessor", "static"})


def parse(source: str, typed: bool = False, jsx: bool = True) -> Node:
    """Parse ``source`` as a script or a module. ``typed`` reads TypeScript; ``jsx`` reads JSX
    elements where an expression starts. Raises :class:`ParseError` at the first error."""
    return _Parser(source, typed=typed, jsx=jsx).program()
