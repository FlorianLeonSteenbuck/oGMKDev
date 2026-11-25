"""TypeScript for the JavaScript parser: type annotations and type syntax, and the declarations that
only TypeScript has (interfaces, type aliases, enums, namespaces, ambient declarations, decorators,
``import x = require(...)``, ``import type``, ``as`` and ``satisfies``, generic calls).

The mixin is used when the parser is typed. Speculation (:meth:`TypeMixin._try`) is used where the
grammar needs more than one token to decide, such as a parenthesized arrow function with a return
type, or the ``<`` that opens type arguments: a failed reading restores the cursor and the other
reading is parsed.
"""

from __future__ import annotations

from typing import List, Optional

from ..lexers import ecmascript_lexer as L
from .syntax import Node, ParseError, flags

PREDEFINED_TYPES = frozenset({"any", "unknown", "number", "string", "boolean", "symbol", "bigint",
                              "object", "never", "undefined"})
PARAMETER_MODIFIERS = frozenset({"public", "private", "protected", "readonly", "override"})
MEMBER_MODIFIERS = frozenset({"public", "private", "protected", "readonly", "abstract", "override",
                              "declare", "accessor"})
TYPE_LITERAL_WORDS = frozenset({"true", "false", "null", "void", "this", "const"})
DECLARATION_WORDS = frozenset({"const", "let", "var", "function", "class", "enum", "interface", "type",
                               "namespace", "module", "global", "abstract", "async"})


class TypeMixin:
    """The TypeScript methods of the parser. ``typed`` and ``ambient`` are set by the parser."""

    typed: bool
    ambient: int

    # ------------------------------------------------------------ speculation

    def _try(self, parse):
        """Run ``parse``. On a syntax error restore the cursor and return None, so that the caller can
        read the same tokens another way; a successful parse is kept."""
        mark = self._mark()
        try:
            return parse()
        except ParseError:
            self._reset(mark)
            return None

    def _looks(self, parse) -> bool:
        """Would ``parse`` succeed here? The cursor is restored either way."""
        mark = self._mark()
        try:
            parse()
            return True
        except ParseError:
            return False
        finally:
            self._reset(mark)

    def _at_closing_angle(self) -> bool:
        token = self.tok
        return token.kind == "punctuator" and self.src[token.start] == ">"

    # ------------------------------------------------------------ annotations

    def _type_annotation(self) -> Optional[Node]:
        if not self._is_punct(":"):
            return None
        self._next()
        return self._type()

    def _return_type(self) -> Optional[Node]:
        if not self._is_punct(":"):
            return None
        self._next()
        predicate = self._try(self._type_predicate)
        return predicate if predicate is not None else self._type()

    def _type_predicate(self) -> Node:
        """``x is T``, ``asserts x``, ``asserts x is T`` and ``this is T``."""
        start = self.tok.start
        asserts = False
        if self._is_name("asserts"):
            following = self._peek()
            if not following.newline_before and (following.kind == "identifier" or self._text(following) == "this"):
                self._next()
                asserts = True
        if not (self.tok.kind == "identifier" or self._is_word("this")):
            raise self._error(self.tok.start, "expected a type predicate")
        subject = self.tok
        self._next()
        children = [Node("Identifier", subject.start, subject.end, text=self._text(subject))]
        if self._is_name("is") and not self.tok.newline_before:
            self._next()
            children.append(self._type())
        elif not asserts:
            raise self._error(self.tok.start, "expected 'is' in a type predicate")
        return Node("TypePredicate", start, self.prev_end, children, flags=flags("asserts" if asserts else ""))

    # ------------------------------------------------------------ type syntax

    def _type(self, conditional: bool = True) -> Node:
        start = self.tok.start
        check = self._union_type()
        if conditional and self._is_word("extends") and not self.tok.newline_before:
            self._next()
            extends = self._type(conditional=False)
            self._expect("?")
            when_true = self._type()
            self._expect(":")
            when_false = self._type()
            return Node("ConditionalType", start, self.prev_end, [check, extends, when_true, when_false])
        return check

    def _union_type(self) -> Node:
        start = self.tok.start
        leading = self._is_punct("|")
        if leading:
            self._next()
        types = [self._intersection_type()]
        while self._is_punct("|"):
            self._next()
            types.append(self._intersection_type())
        if len(types) == 1 and not leading:
            return types[0]
        return Node("UnionType", start, self.prev_end, types)

    def _intersection_type(self) -> Node:
        start = self.tok.start
        leading = self._is_punct("&")
        if leading:
            self._next()
        types = [self._type_operator()]
        while self._is_punct("&"):
            self._next()
            types.append(self._type_operator())
        if len(types) == 1 and not leading:
            return types[0]
        return Node("IntersectionType", start, self.prev_end, types)

    def _type_operator(self) -> Node:
        token = self.tok
        if token.kind == "identifier" and self._text() in ("keyof", "unique", "readonly"):
            operator = self._text()
            self._next()
            operand = self._type_operator()
            return Node("TypeOperator", token.start, self.prev_end, [operand], text=operator)
        if token.kind == "identifier" and self._text() == "infer":
            self._next()
            children = [self._binding_identifier("a type parameter name")]
            if self._is_word("extends"):
                def bound():
                    self._next()
                    return self._type(conditional=False)
                constraint = self._try(bound)
                if constraint is not None:
                    children.append(constraint)
            return Node("InferType", token.start, self.prev_end, children)
        return self._postfix_type()

    def _postfix_type(self) -> Node:
        node = self._primary_type()
        while self._is_punct("[") and not self.tok.newline_before:
            opener = self.tok
            self._next()
            if self._is_punct("]"):
                self._next()
                node = Node("ArrayType", node.start, self.prev_end, [node])
            else:
                index = self._type()
                self._close("]", opener)
                node = Node("IndexedAccessType", node.start, self.prev_end, [node, index])
        return node

    def _primary_type(self) -> Node:
        token = self.tok
        kind = token.kind
        text = self._text()
        if kind == "punctuator":
            if text == "(":
                return self._parenthesized_type()
            if text == "<":  # a generic function type: <T>(x: T) => T
                return self._function_type_head()
            if text == "[":
                return self._tuple_type()
            if text == "{":
                return self._object_type()
            if text == "-":
                self._next()
                number = self.tok
                if number.kind != "number":
                    raise self._error(number.start, "expected a number after '-' in a type")
                self._next()
                return Node("LiteralType", token.start, self.prev_end, text=self.src[token.start:number.end])
            raise self._error(token.start, f"expected a type, found {self._describe(token)}")
        if kind in ("string", "number"):
            self._next()
            return Node("LiteralType", token.start, token.end, text=text)
        if kind in ("template", "template-open"):
            return self._template_type()
        if kind == "keyword":
            if text in TYPE_LITERAL_WORDS:
                self._next()
                return Node("TypeKeyword", token.start, token.end, text=text)
            if text == "typeof":
                return self._type_query()
            if text == "new":
                return self._constructor_type(token.start, abstract=False)
            if text == "import":
                return self._import_type()
            raise self._error(token.start, f"expected a type, found {self._describe(token)}")
        if kind == "identifier":
            if text == "abstract" and self._peek_is_word("new"):
                self._next()
                return self._constructor_type(token.start, abstract=True)
            if text in PREDEFINED_TYPES and not self._peek_is_punct("."):
                self._next()
                return Node("TypeKeyword", token.start, token.end, text=text)
            return self._type_reference()
        raise self._error(token.start, f"expected a type, found {self._describe(token)}")

    def _type_reference(self) -> Node:
        start = self.tok.start
        name = self._entity_name()
        children = [name]
        if self._is_punct("<") and not self.tok.newline_before:
            children.append(self._type_arguments())
        return Node("TypeReference", start, self.prev_end, children)

    def _entity_name(self) -> Node:
        """``A``, ``A.B.C``; the parts after a dot may be keywords."""
        token = self.tok
        if token.kind not in ("identifier", "keyword"):
            raise self._error(token.start, f"expected a type name, found {self._describe(token)}")
        self._next()
        node = Node("Identifier", token.start, token.end, text=self._text(token))
        while self._is_punct(".") and not self.tok.newline_before:
            self._next()
            part = self.tok
            if part.kind not in ("identifier", "keyword"):
                raise self._error(part.start, f"expected a name after '.', found {self._describe(part)}")
            self._next()
            right = Node("Identifier", part.start, part.end, text=self._text(part))
            node = Node("QualifiedName", node.start, self.prev_end, [node, right])
        return node

    def _type_arguments(self) -> Node:
        opener = self.tok
        self._expect("<")
        types: List[Node] = []
        while not self._at_closing_angle() and self.tok.kind != "eof":
            types.append(self._type())
            if not self._is_punct(","):
                break
            self._next()
        self._expect_angle()
        return Node("TypeArguments", opener.start, self.prev_end, types)

    def _expect_angle(self) -> None:
        """A closing '>' of type arguments or parameters. A longer token such as '>>' or '>=' is split:
        its first character closes the list and the rest stays the current token."""
        token = self.tok
        if self._at_closing_angle():
            if token.end - token.start == 1:
                self._next()
            else:
                self.prev_end = token.start + 1
                self.tok = L.Token("punctuator", token.start + 1, token.end, token.newline_before)
            return
        raise self._error(token.start, f"expected '>' before {self._describe(token)}")

    def _type_parameters(self) -> Node:
        opener = self.tok
        self._expect("<")
        params: List[Node] = []
        while not self._at_closing_angle() and self.tok.kind != "eof":
            start = self.tok.start
            modifiers: List[str] = []
            while ((self._is_word("in") or self._is_word("const") or self._is_name("out"))
                   and self._peek_starts_name()):
                modifiers.append(self._text())
                self._next()
            children = [self._binding_identifier("a type parameter name")]
            if self._is_word("extends"):
                self._next()
                children.append(self._type(conditional=False))
            if self._is_punct("="):
                self._next()
                children.append(self._type())
            params.append(Node("TypeParameter", start, self.prev_end, children, flags=flags(*modifiers)))
            if not self._is_punct(","):
                break
            self._next()
        self._expect_angle()
        return Node("TypeParameters", opener.start, self.prev_end, params)

    def _tuple_type(self) -> Node:
        opener = self.tok
        self._next()
        elements: List[Node] = []
        while not self._is_punct("]") and self.tok.kind != "eof":
            start = self.tok.start
            if self._is_punct("..."):
                self._next()
                inner = self._tuple_member()
                elements.append(Node("RestType", start, self.prev_end, [inner]))
            else:
                elements.append(self._tuple_member())
            if not self._separator("]"):
                break
        self._close("]", opener)
        return Node("TupleType", opener.start, self.prev_end, elements)

    def _tuple_member(self) -> Node:
        """An element of a tuple: ``T``, ``T?``, or a named member ``name: T`` and ``name?: T``."""
        start = self.tok.start
        name = self._try(self._named_tuple_head)
        if name is not None:
            return Node("NamedTupleMember", start, self.prev_end, [name, self._type()])
        element = self._type()
        if self._is_punct("?"):
            self._next()
            return Node("OptionalType", start, self.prev_end, [element])
        return element

    def _named_tuple_head(self) -> Node:
        token = self.tok
        if token.kind != "identifier":
            raise self._error(token.start, "expected a tuple member name")
        self._next()
        if self._is_punct("?"):
            self._next()
        self._expect(":")
        return Node("Identifier", token.start, token.end, text=self._text(token))

    def _parenthesized_type(self) -> Node:
        function = self._try(self._function_type_head)
        if function is not None:
            return function
        opener = self.tok
        self._next()
        inner = self._type()
        self._close(")", opener)
        return Node("ParenthesizedType", opener.start, self.prev_end, [inner])

    def _function_type_head(self) -> Node:
        start = self.tok.start
        children: List[Node] = []
        if self._is_punct("<"):
            children.append(self._type_parameters())
        children.append(self._formal_parameters())
        self._expect("=>")
        predicate = self._try(self._type_predicate)
        children.append(predicate if predicate is not None else self._type())
        return Node("FunctionType", start, self.prev_end, children)

    def _constructor_type(self, start: int, abstract: bool) -> Node:
        self._expect_word("new")
        children: List[Node] = []
        if self._is_punct("<"):
            children.append(self._type_parameters())
        children.append(self._formal_parameters())
        self._expect("=>")
        children.append(self._type())
        return Node("ConstructorType", start, self.prev_end, children, flags=flags("abstract" if abstract else ""))

    def _type_query(self) -> Node:
        start = self.tok.start
        self._next()  # typeof
        subject = self._import_type() if self._is_word("import") else self._entity_name()
        children = [subject]
        if self._is_punct("<") and not self.tok.newline_before:
            children.append(self._type_arguments())
        return Node("TypeQuery", start, self.prev_end, children)

    def _import_type(self) -> Node:
        start = self.tok.start
        self._next()  # import
        opener = self.tok
        self._expect("(")
        children = [self._module_source()]
        self._close(")", opener)
        if self._is_punct("."):
            self._next()
            children.append(self._entity_name())
        if self._is_punct("<"):
            children.append(self._type_arguments())
        return Node("ImportType", start, self.prev_end, children)

    def _template_type(self) -> Node:
        first = self.tok
        spans: List[Node] = []
        while True:
            self._check(self.tok)
            if self.tok.kind == "template":
                self._next()
                break
            self._next()  # past the `${`
            spans.append(self._type())
            if not self._is_punct("}"):
                raise self._error(self.tok.start, "expected '}' to close the template type before "
                                                  f"{self._describe(self.tok)}")
            self.tok = L.scan_template_continuation(self.src, self.tok.start)
        return Node("TemplateLiteralType", first.start, self.prev_end, spans)

    # ------------------------------------------------------------ object types

    def _object_type(self) -> Node:
        if self._looks(self._mapped_type_head):
            return self._mapped_type()
        return self._type_literal()

    def _type_literal(self) -> Node:
        opener = self.tok
        self._expect("{")
        members: List[Node] = []
        while not self._is_punct("}") and self.tok.kind != "eof":
            members.append(self._type_member())
            if self._is_punct(";") or self._is_punct(","):
                self._next()
            elif not (self._is_punct("}") or self.tok.newline_before):
                raise self._error(self.tok.start, "expected ';', ',' or '}' before "
                                                  f"{self._describe(self.tok)}")
        self._close("}", opener)
        return Node("TypeLiteral", opener.start, self.prev_end, members)

    def _mapped_type_head(self) -> None:
        self._expect("{")
        if self._is_punct("+") or self._is_punct("-"):
            self._next()
        if self._is_name("readonly"):
            self._next()
        self._expect("[")
        self._binding_identifier("a type parameter name")
        self._expect_word("in")

    def _mapped_type(self) -> Node:
        opener = self.tok
        self._next()  # {
        readonly = ""
        if self._is_punct("+") or self._is_punct("-"):
            readonly = self._text()
            self._next()
            self._expect_name("readonly")
        elif self._is_name("readonly"):
            readonly = "readonly"
            self._next()
        self._expect("[")
        name = self._binding_identifier("a type parameter name")
        self._expect_word("in")
        constraint = self._type()
        if self._is_name("as"):  # key remapping
            self._next()
            self._type()
        self._expect("]")
        optional = ""
        if self._is_punct("+") or self._is_punct("-"):
            optional = self._text()
            self._next()
            self._expect("?")
        elif self._is_punct("?"):
            optional = "?"
            self._next()
        children = [name, constraint]
        if self._is_punct(":"):
            self._next()
            children.append(self._type())
        if self._is_punct(";") or self._is_punct(","):
            self._next()
        self._close("}", opener)
        return Node("MappedType", opener.start, self.prev_end, children, text=optional,
                    flags=flags(readonly))

    def _type_member(self) -> Node:
        """A member of an interface or an object type: a property, a method, an accessor, a call or
        construct signature, or an index signature."""
        start = self.tok.start
        if self._is_punct("(") or self._is_punct("<"):
            return self._signature(start, "CallSignature")
        if self._is_word("new") and (self._peek_is_punct("(") or self._peek_is_punct("<")):
            self._next()
            return self._signature(start, "ConstructSignature")
        readonly = False
        if self._is_name("readonly") and self._peek_starts_member_key():
            readonly = True
            self._next()
        if self._is_punct("[") and self._looks(self._index_signature_head):
            return self._index_signature(start, readonly)
        accessor = ""
        if (self._is_name("get") or self._is_name("set")) and self._peek_starts_member_key():
            accessor = self._text()
            self._next()
        key, _computed = self._property_key()
        optional = False
        if self._is_punct("?"):
            optional = True
            self._next()
        if self._is_punct("(") or self._is_punct("<"):
            return self._signature(start, "MethodSignature", key=key, flags=flags("optional" if optional else ""))
        annotation = self._type_annotation()
        children = [key] + ([annotation] if annotation is not None else [])
        return Node("PropertySignature", start, self.prev_end, children, text=accessor,
                    flags=flags("readonly" if readonly else "", "optional" if optional else ""))

    def _signature(self, start: int, kind: str, key: Optional[Node] = None, flags=frozenset()) -> Node:
        children: List[Node] = [key] if key is not None else []
        if self._is_punct("<"):
            children.append(self._type_parameters())
        children.append(self._formal_parameters())
        return_type = self._return_type()
        if return_type is not None:
            children.append(return_type)
        return Node(kind, start, self.prev_end, children, flags=flags)

    def _index_signature_head(self) -> None:
        self._expect("[")
        self._binding_identifier("an index name")
        self._expect(":")

    def _index_signature(self, start: int, readonly: bool) -> Node:
        self._expect("[")
        name = self._binding_identifier("an index name")
        self._expect(":")
        key_type = self._type()
        self._expect("]")
        value = self._type_annotation()
        if value is None:
            raise self._error(self.tok.start, f"expected ':' and a type after the index signature, found "
                                              f"{self._describe(self.tok)}")
        return Node("IndexSignature", start, self.prev_end, [name, key_type, value],
                    flags=flags("readonly" if readonly else ""))

    def _peek_starts_member_key(self) -> bool:
        following = self._peek()
        if following.kind in ("identifier", "keyword", "string", "number"):
            return True
        return following.kind == "punctuator" and self._text(following) == "["

    # ------------------------------------------------------------ expressions

    def _angle_expression(self) -> Node:
        """A `<` where an expression starts: a generic arrow function or a type assertion in typed
        code, JSX in JSX code."""
        if self.typed:
            arrow = self._typed_arrow(self.tok.start, False, False)
            if arrow is not None:
                return arrow
        if self.jsx:
            return self._jsx_expression_element()
        if self.typed:
            return self._type_assertion()
        raise self._unexpected()

    def _type_assertion(self) -> Node:
        start = self.tok.start
        self._next()  # <
        target = self._type()
        self._expect_angle()
        operand = self._unary()
        return Node("TypeAssertion", start, self.prev_end, [target, operand])

    def _typed_arrow(self, start: int, is_async: bool, no_in: bool) -> Optional[Node]:
        """An arrow function with type parameters, parameter types or a return type. Speculative: None
        when the tokens are not such a head (then the caller reads them as something else)."""
        head = self._try(self._typed_arrow_head)
        if head is None:
            return None
        type_params, params, return_type = head
        prefix = [node for node in (type_params, return_type) if node is not None]
        return self._arrow_body(start, params.children, is_async, no_in, prefix)

    def _typed_arrow_head(self):
        type_params = self._type_parameters() if self._is_punct("<") else None
        if not self._is_punct("("):
            raise self._error(self.tok.start, "expected '(' before the parameters of an arrow function")
        params = self._formal_parameters()
        return_type = self._return_type()
        if not self._is_punct("=>") or self.tok.newline_before:
            raise self._error(self.tok.start, "expected '=>' after the parameters")
        return type_params, params, return_type

    def _call_type_arguments(self) -> Node:
        """Type arguments that a call or a tagged template follows: ``f<T>(x)``, ``f<T>`x```."""
        arguments = self._type_arguments()
        if not (self._is_punct("(") or self.tok.kind in ("template", "template-open")):
            raise self._error(self.tok.start, "type arguments are only valid before a call here")
        return arguments

    def _type_cast(self, expression: Node) -> Node:
        """``expression as Type`` and ``expression satisfies Type``."""
        operator = self._text()
        self._next()
        target = self._type(conditional=False)
        kind = "AsExpression" if operator == "as" else "SatisfiesExpression"
        return Node(kind, expression.start, self.prev_end, [expression, target])

    # ------------------------------------------------------------ parameters

    def _typed_parameter(self) -> Node:
        """A parameter with decorators, accessibility modifiers, ``?``, a type and a default value, or
        a rest parameter."""
        start = self.tok.start
        decorators = self._decorators()
        modifiers: List[str] = []
        while (self.tok.kind in ("identifier", "keyword") and self._text() in PARAMETER_MODIFIERS
               and self._modifier_follows_parameter()):
            modifiers.append(self._text())
            self._next()
        if self._is_punct("..."):
            self._next()
            target = self._parameter_target()
            children = [target]
            annotation = self._type_annotation()
            if annotation is not None:
                children.append(annotation)
            node = Node("RestElement", start, self.prev_end, children, flags=flags(*modifiers))
        else:
            target = self._parameter_target()
            children = [target]
            if self._is_punct("?"):
                self._next()
            annotation = self._type_annotation()
            if annotation is not None:
                children.append(annotation)
            if self._is_punct("="):
                self._next()
                children.append(self._assignment())
            node = Node("Parameter", start, self.prev_end, children, flags=flags(*modifiers))
        if decorators:
            return Node("Decorated", start, self.prev_end, decorators + [node])
        return node

    def _parameter_target(self) -> Node:
        if self._is_word("this"):
            token = self.tok
            self._next()
            return Node("Identifier", token.start, token.end, text="this")
        return self._binding_target("a parameter name")

    def _modifier_follows_parameter(self) -> bool:
        following = self._peek()
        if following.kind in ("identifier", "keyword"):
            return True
        return following.kind == "punctuator" and self._text(following) in ("{", "[")

    # ------------------------------------------------------------ decorators

    def _decorators(self) -> List[Node]:
        decorators: List[Node] = []
        while self._is_punct("@"):
            start = self.tok.start
            self._next()
            expression = self._call_expression()
            decorators.append(Node("Decorator", start, self.prev_end, [expression]))
        return decorators

    def _decorated(self) -> Node:
        """Decorators in front of a class or an exported class."""
        start = self.tok.start
        decorators = self._decorators()
        if self._is_word("export"):
            declaration = self._export_declaration()
        else:
            declaration = self._statement_list_item(top_level=True)
        return Node("Decorated", start, self.prev_end, decorators + [declaration])

    # ------------------------------------------------------------ declarations

    def _typed_statement(self, top_level: bool) -> Optional[Node]:
        """A TypeScript declaration that starts the statement, or None for any other statement."""
        token = self.tok
        if token.kind == "punctuator" and self._text() == "@":
            return self._decorated()
        if token.kind not in ("identifier", "keyword"):
            return None
        word = self._text()
        following = self._peek()
        start = token.start
        if word == "interface" and token.kind == "keyword" and following.kind == "identifier":
            return self._interface(start)
        if word == "type" and token.kind == "identifier" and following.kind == "identifier" \
                and not following.newline_before:
            return self._type_alias(start)
        if word == "enum" and token.kind == "keyword":
            return self._enum(start, const=False)
        if word == "const" and token.kind == "keyword" and following.kind == "keyword" \
                and self._text(following) == "enum":
            return self._enum(start, const=True)
        if word in ("namespace", "module") and token.kind == "identifier" and not following.newline_before \
                and following.kind in ("identifier", "string"):
            return self._namespace(start)
        if word == "global" and token.kind == "identifier" and following.kind == "punctuator" \
                and self._text(following) == "{":  # module augmentation inside a module
            self._next()
            return Node("GlobalDeclaration", start, self.prev_end, [self._module_block()])
        if word == "declare" and token.kind == "identifier" and not following.newline_before \
                and self._declaration_follows(following):
            return self._declare(start)
        if word == "abstract" and token.kind == "identifier" and not following.newline_before \
                and following.kind == "keyword" and self._text(following) == "class":
            self._next()
            declaration = self._class(start, declaration=True)
            declaration.flags = declaration.flags | flags("abstract")
            return declaration
        return None

    def _declaration_follows(self, following) -> bool:
        if following.kind == "keyword":
            return self._text(following) in DECLARATION_WORDS
        if following.kind == "identifier":
            return self._text(following) in DECLARATION_WORDS
        return False

    def _interface(self, start: int) -> Node:
        self._next()  # interface
        children: List[Node] = [self._binding_identifier("an interface name")]
        if self._is_punct("<"):
            children.append(self._type_parameters())
        if self._is_word("extends"):
            self._next()
            children.append(self._type_reference())
            while self._is_punct(","):
                self._next()
                children.append(self._type_reference())
        children.append(self._type_literal())
        return Node("InterfaceDeclaration", start, self.prev_end, children)

    def _type_alias(self, start: int) -> Node:
        self._next()  # type
        children: List[Node] = [self._binding_identifier("a type alias name")]
        if self._is_punct("<"):
            children.append(self._type_parameters())
        self._expect("=")
        children.append(self._type())
        self._semicolon()
        return Node("TypeAliasDeclaration", start, self.prev_end, children)

    def _enum(self, start: int, const: bool) -> Node:
        if const:
            self._next()  # const
        self._expect_word("enum")
        children: List[Node] = [self._binding_identifier("an enum name")]
        opener = self.tok
        self._expect("{")
        while not self._is_punct("}") and self.tok.kind != "eof":
            member_start = self.tok.start
            key, _computed = self._property_key()
            members_children = [key]
            if self._is_punct("="):
                self._next()
                members_children.append(self._assignment())
            children.append(Node("EnumMember", member_start, self.prev_end, members_children))
            if not self._separator("}"):
                break
        self._close("}", opener)
        return Node("EnumDeclaration", start, self.prev_end, children, flags=flags("const" if const else ""))

    def _namespace(self, start: int) -> Node:
        keyword = self._text()
        self._next()
        name = self._module_source() if self.tok.kind == "string" else self._entity_name()
        children = [name]
        if self._is_punct("{"):
            children.append(self._module_block())
        else:
            self._semicolon()
        return Node("NamespaceDeclaration", start, self.prev_end, children, text=keyword)

    def _module_block(self) -> Node:
        opener = self.tok
        self._expect("{")
        body: List[Node] = []
        while not self._is_punct("}") and self.tok.kind != "eof":
            body.append(self._statement_list_item(top_level=True))
        self._close("}", opener)
        return Node("ModuleBlock", opener.start, self.prev_end, body)

    def _declare(self, start: int) -> Node:
        self._next()  # declare
        self.ambient += 1
        try:
            if self._is_name("global"):
                self._next()
                body = self._module_block()
                return Node("GlobalDeclaration", start, self.prev_end, [body])
            declaration = self._statement_list_item(top_level=True)
            return Node("AmbientDeclaration", start, self.prev_end, [declaration])
        finally:
            self.ambient -= 1

    def _import_equals(self, start: int, type_only: bool) -> Node:
        """``import x = require("m")`` or ``import x = A.B``; the cursor is on the name."""
        name = self._binding_identifier("an import name")
        self._expect("=")
        value = self._assignment()
        self._semicolon()
        return Node("ImportEquals", start, self.prev_end, [name, value], flags=flags("type" if type_only else ""))
