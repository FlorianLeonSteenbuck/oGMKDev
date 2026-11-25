"""JSX for the JavaScript and TypeScript parsers: elements, fragments, attributes and children.

Children are text, so after an opening tag the parser reads raw text up to the next ``<`` or ``{``:
the tokenizer would take an apostrophe in ``Don't`` for the start of a string. A finished element
leaves the pseudo token ``jsx-done`` at its end; the caller scans on from there with ``_next``.
"""

from __future__ import annotations

from typing import List, Optional

from ..lexers import ecmascript_lexer as L
from .syntax import Node


class JsxMixin:
    """Parser methods that read JSX. They work on the parser's cursor (``tok`` and ``prev_end``)."""

    def _jsx_done(self, end: int) -> None:
        self.prev_end = end
        self.tok = L.Token("jsx-done", end, end)

    def _jsx_expression_element(self) -> Node:
        """A JSX element where an expression starts; the cursor moves on to the next token."""
        node = self._jsx_element()
        self._next()
        return node

    def _jsx_element(self) -> Node:
        """A JSX element or fragment, starting at the ``<`` that is the current token."""
        start = self.tok.start
        self._next()  # past '<'
        if self._is_punct(">"):  # <> ... </>
            children = self._jsx_children(self.tok.end, start)
            self._jsx_closing(None)
            return Node("JSXFragment", start, self.prev_end, children)
        name = self._jsx_name()
        attributes: List[Node] = []
        if self.typed and self._is_punct("<"):  # <Component<T> prop={...} />
            attributes.append(self._type_arguments())
        while not (self._is_punct(">") or self._is_punct("/")):
            if self.tok.kind == "eof":
                raise self._error(start, f"unclosed JSX tag '<{name.text}': expected '>' or '/>'")
            attributes.append(self._jsx_attribute())
        if self._is_punct("/"):  # <name ... />
            self._next()
            if not self._is_punct(">"):
                raise self._error(self.tok.start, f"expected '>' after '/' in the JSX tag '<{name.text}'")
            self._jsx_done(self.tok.end)
            return Node("JSXElement", start, self.prev_end, [name] + attributes, text=name.text)
        children = self._jsx_children(self.tok.end, start)
        self._jsx_closing(name)
        return Node("JSXElement", start, self.prev_end, [name] + attributes + children, text=name.text)

    def _jsx_name(self) -> Node:
        """A tag or attribute name. Parts joined by '-', ':' or '.' without a space make one name."""
        token = self.tok
        if token.kind not in ("identifier", "keyword"):
            raise self._error(token.start, f"expected a JSX name, found {self._describe(token)}")
        self._next()
        text = self._text(token)
        while self.tok.kind == "punctuator" and self._text() in ("-", ":", ".") and self.tok.start == self.prev_end:
            separator = self._text()
            self._next()
            part = self.tok
            if part.kind not in ("identifier", "keyword", "number") or part.start != self.prev_end:
                raise self._error(part.start, f"expected a name after '{separator}' in a JSX name")
            self._next()
            text += separator + self._text(part)
        return Node("JSXName", token.start, self.prev_end, text=text)

    def _jsx_attribute(self) -> Node:
        if self._is_punct("{"):
            return self._jsx_spread_attribute()
        start = self.tok.start
        name = self._jsx_name()
        children = [name]
        if self._is_punct("="):
            self._next()
            value = self.tok
            if value.kind == "string":
                self._next()
                children.append(Node("Literal", value.start, value.end, text=self._text(value)))
            elif self._is_punct("{"):
                children.append(self._jsx_expression_container())
                self._next()
            elif self._is_punct("<"):
                children.append(self._jsx_expression_element())
            else:
                raise self._error(value.start,
                                  f"expected a string or '{{' after '=' in a JSX attribute, "
                                  f"found {self._describe(value)}")
        return Node("JSXAttribute", start, self.prev_end, children)

    def _jsx_spread_attribute(self) -> Node:
        start = self.tok.start
        self._next()  # past '{'
        self._expect("...")
        argument = self._assignment()
        if not self._is_punct("}"):
            raise self._error(self.tok.start, f"expected '}}' after the spread in a JSX tag before "
                                              f"{self._describe(self.tok)}")
        self._next()
        return Node("JSXSpreadAttribute", start, self.prev_end, [argument])

    def _jsx_expression_container(self) -> Node:
        """``{expression}``, or ``{}`` and ``{/* comment */}``. Leaves the cursor on ``jsx-done``
        after the closing brace."""
        start = self.tok.start
        self._next()  # past '{'
        children: List[Node] = []
        if not self._is_punct("}"):
            if self._is_punct("..."):
                self._next()
            children.append(self._expression())
        if not self._is_punct("}"):
            raise self._error(self.tok.start, "expected '}' to close the JSX expression before "
                                              f"{self._describe(self.tok)}")
        self._jsx_done(self.tok.end)
        return Node("JSXExpressionContainer", start, self.prev_end, children)

    def _jsx_children(self, position: int, opener: int) -> List[Node]:
        """The children from ``position`` (the end of the opening tag) up to the closing tag, which is
        left as the current token ``<``."""
        children: List[Node] = []
        source = self.src
        while True:
            end = L.jsx_text_end(source, position)
            if end > position:
                children.append(Node("JSXText", position, end, text=source[position:end]))
            if end >= len(source):
                raise self._error(opener, "unclosed JSX element: expected a closing tag")
            self.tok = self._scan_from(end)
            self._check(self.tok)
            if self._is_punct("{"):
                children.append(self._jsx_expression_container())
            elif self._is_punct("<") and self._jsx_closing_follows():
                return children
            elif self._is_punct("<"):
                children.append(self._jsx_expression_element_raw())
            else:
                raise self._error(self.tok.start, f"unexpected {self._describe(self.tok)} in JSX children")
            position = self.tok.end

    def _jsx_closing_follows(self) -> bool:
        """The current '<' starts a closing tag when a slash is right behind it."""
        return self.src[self.tok.end:self.tok.end + 1] == "/"

    def _jsx_expression_element_raw(self) -> Node:
        """A child element: the cursor stays on ``jsx-done`` so that the children go on as raw text."""
        return self._jsx_element()

    def _jsx_closing(self, name: Optional[Node]) -> None:
        """``</name>`` or ``</>``; the current token is the '<' that opens it."""
        label = name.text if name is not None else ""
        if not self._is_punct("<"):
            raise self._error(self.tok.start, f"expected '</{label}>' to close the JSX element before "
                                              f"{self._describe(self.tok)}")
        self._next()
        if not self._is_punct("/"):
            raise self._error(self.tok.start, f"expected '</{label}>' before {self._describe(self.tok)}")
        self._next()
        if name is not None:
            closing = self._jsx_name()
            if closing.text != name.text:
                raise self._error(closing.start, f"closing tag '</{closing.text}>' does not match "
                                                 f"'<{name.text}>'")
        if not self._is_punct(">"):
            raise self._error(self.tok.start, f"expected '>' to end the closing tag before "
                                              f"{self._describe(self.tok)}")
        self._jsx_done(self.tok.end)
