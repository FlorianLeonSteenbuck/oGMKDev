import unittest

from ogmkdev import diagnostics
from ogmkdev.languages import Detection
from ogmkdev.parsers import ecmascript as LALR
from ogmkdev.parsers import javascript as J

MODERN_PROGRAMS = [
    "var x = 1;",
    "let a = [1, , 3,]; const {b, c: [d = 2, ...e], ...f} = obj;",
    "const f = (a, b = 2, ...c) => a + b; const g = x => x * 2; const h = async () => { await 1; };",
    "class A extends B { static #n = 0; #p; get v() { return this.#p; } set v(x) { this.#p = x; } "
    "static { A.#n++; } m() { return super.m(); } has(o) { return #p in o; } }",
    "function* gen() { yield 1; yield* other(); const x = yield; }",
    "async function f() { for await (const x of y) { await x; } }",
    "const s = `a${b}c${`nested ${d}`}e`; tag`x${1}`;",
    "a?.b?.[0]?.(1); a ??= b; a ||= c; a &&= d; x = a ?? b; y = 1_000_000n; z = 0x1F;",
    "import x, {a as b, default as c} from 'm'; import * as ns from 'n'; import 'side';",
    "export const q = 1; export default class {}; export {q as r}; export * from 'z'; "
    "export * as ns2 from 'w';",
    "label: for (const k in o) { if (k) continue label; else break label; }",
    "x = a ? b => 1 : c => 2; y = (a, b) => ({a, b}); z = async (p) => p;",
    "[a, b] = [b, a]; ({a, b: {c}} = d); ({a = 1} = {});",
    "for (const [k, v] of Object.entries(o)) {}",
    "for (let i = 0, n = a.length; i < n; i++) {}",
    "do x++; while (x < 3) y = 1",
    "switch (v) { case 1: break; default: x(); }",
    "try { a() } catch { b() } finally { c() }",
    "var re = /ab+c/gi.test(s); var d = a / b / c; if (x) /re/.test(y);",
    "obj = { get a() { return 1 }, set a(v) {}, async *g() {}, [k]: 1, 'q': 2, 3: 4, m() {}, ...rest };",
    "function f() { return\n1 }",
    "a\n++b",
    "x = new.target; y = import.meta.url; z = import('m'); w = new Foo; v = new a.b.C(1)(2);",
    "class C { 'constructor'() {} static async *[Symbol.iterator]() {} static static() {} get() {} }",
    "#!/usr/bin/env node\nconsole.log(1);",
    "x = a ? b : c; y = !a && ~b || -c === undefined;",
    "x = (-2) ** 2; p = typeof q === 'undefined'; delete o.p; void 0;",
    "if (a) function f() {}",
    "with (o) { x; }",
    "for (x of y) {} for (x.y in z) {} for ([a, b] of c) {}",
    "var {[key]: val = 1} = o;",
    "async\nfunction f2() {}",
    "return 1;",
    "(a, b)",
    "x = {async, get, set, static: 1};",
]


class ModernSyntaxIsAcceptedTests(unittest.TestCase):
    def test_valid_programs_parse(self):
        for source in MODERN_PROGRAMS:
            with self.subTest(source=source):
                J.parse(source)

    def test_es5_samples_parse_with_both_parsers(self):
        # the KDevelop LALR driver is the ES5 reference: everything it accepts, the new parser accepts
        samples = ["var x = 1;", "function f(a, b) { return a + b * 2; }",
                   "if (x) { y(); } else { z = 3; }", "var o = {a: [1, 2], 'b': function(){ return this; }};",
                   "x = a / b / c", "x = /ab+c/g.test(s);", "var r = /[/]/;", "a = b\n++c",
                   "function f() {\n  return x\n}", "return\n1", ""]
        for source in samples:
            with self.subTest(source=source):
                LALR.parse(source)
                J.parse(source)


class SyntaxErrorTests(unittest.TestCase):
    def assertError(self, source, line, column, fragment):
        with self.assertRaises(J.ParseError) as caught:
            J.parse(source)
        error = caught.exception
        self.assertEqual((error.line, error.column), (line, column), error.message)
        self.assertIn(fragment, error.message)

    def test_missing_semicolon_names_the_token_that_follows(self):
        self.assertError("let a = 1\nlet b = 2 c", 2, 11, "missing ';' before identifier 'c'")

    def test_unexpected_end_of_input_after_an_operator(self):
        self.assertError("x = 1 +", 1, 8, "unexpected end of input")

    def test_binding_name_expected(self):
        self.assertError("var = 3;", 1, 5, "expected variable name, found '='")

    def test_unclosed_parenthesis_on_the_same_line(self):
        self.assertError("if (a { b }", 1, 7, "expected ')' before '{'")

    def test_unclosed_parenthesis_on_an_earlier_line_names_its_opener(self):
        self.assertError("f(a,\n  b;", 2, 4, "expected ',' or ')' before ';'")
        self.assertError("x = (1 +\n2;", 2, 2, "expected ')' to match '(' on line 1 before ';'")

    def test_class_member_with_a_type_annotation_is_not_a_field(self):
        self.assertError("class A { x: 1 }", 1, 12, "expected '(' or '=' after the class member name")

    def test_missing_initializers(self):
        self.assertError("const x;", 1, 7, "missing initializer in const declaration")
        self.assertError("const {a} ;", 1, 7, "missing initializer in destructuring declaration")

    def test_arrow_and_parameter_list_errors(self):
        self.assertError("(a, b)\n=> 1", 2, 1, "unexpected line break before '=>'")
        self.assertError("(a, ...b, c) => 1", 1, 9, "rest parameter must be last")

    def test_assignment_targets(self):
        self.assertError("1 = 2;", 1, 1, "invalid left-hand side in assignment")
        self.assertError("x = {a = 1};", 1, 8, "invalid shorthand property initializer")
        self.assertError("x++ = 1", 1, 1, "invalid left-hand side in assignment")

    def test_module_syntax_only_at_top_level(self):
        self.assertError("function f() {\n  export const z = 1;\n}", 2, 3,
                         "'export' may only appear at the top level of a module")

    def test_jumps_need_a_target(self):
        self.assertError("break;", 1, 1, "illegal break statement")
        self.assertError("while (1) { continue foo; }", 1, 22, "undefined label 'foo'")
        self.assertError("foo: { continue foo; }", 1, 17, "label 'foo' does not label a loop")

    def test_try_needs_catch_or_finally(self):
        self.assertError("try { }", 1, 8, "expected 'catch' or 'finally' after the try block")

    def test_nullish_coalescing_does_not_mix_with_logical_operators(self):
        self.assertError("x = a ?? b || c;", 1, 12, "'??' cannot be mixed")
        J.parse("x = (a ?? b) || c;")

    def test_exponent_needs_parentheses_after_unary(self):
        self.assertError("x = -2 ** 2;", 1, 8, "unary operator before '**' needs parentheses")

    def test_unterminated_template_substitution(self):
        self.assertError("x = `open ${a", 1, 14, "expected '}' to close the template substitution")

    def test_regexp_flags(self):
        self.assertError("var r = /a/gg;", 1, 9, "invalid regular expression flags")

    def test_class_and_accessor_rules(self):
        self.assertError("class A { constructor() {} constructor() {} }", 1, 28,
                         "a class may only have one constructor")
        self.assertError("obj = { get x(a) {} }", 1, 13, "getter must not have any parameters")
        self.assertError("obj = { set x() {} }", 1, 13, "setter must have exactly one parameter")

    def test_super_outside_a_method(self):
        self.assertError("super.x;", 1, 1, "'super' keyword unexpected here")

    def test_no_line_break_after_throw(self):
        self.assertError("throw\nnew Error()", 2, 1, "illegal newline after 'throw'")

    def test_characters_the_lexer_does_not_know(self):
        self.assertError("x = 1 @ 2", 1, 7, "missing ';' before '@'")

    def test_numbers_followed_by_identifiers(self):
        self.assertError("x = 3in y", 1, 6, "identifier starts immediately after a numeric literal")

    def test_unterminated_string_and_regexp(self):
        self.assertError("x = 'open", 1, 5, "unterminated string literal")
        self.assertError("var y = /x", 1, 9, "unterminated regular expression")


class TreeTests(unittest.TestCase):
    def statement(self, source):
        return J.parse(source).children[0]

    def test_arrow_parameters_become_patterns(self):
        arrow = self.statement("(a, {b}, ...c) => a;").children[0]
        self.assertEqual(arrow.kind, "ArrowFunction")
        formal = arrow.children[0]
        self.assertEqual([child.kind for child in formal.children], ["Identifier", "ObjectPattern", "RestElement"])

    def test_async_arrow_has_the_async_flag_and_its_own_parameters(self):
        arrow = self.statement("async (x = 1) => x;").children[0]
        self.assertIn("async", arrow.flags)
        self.assertEqual([child.kind for child in arrow.children[0].children], ["AssignmentPattern"])

    def test_destructuring_assignment_converts_the_left_side(self):
        assignment = self.statement("[a, , ...b] = c;").children[0]
        self.assertEqual(assignment.kind, "AssignmentExpression")
        self.assertEqual([child.kind for child in assignment.children[0].children],
                         ["Identifier", "Elision", "RestElement"])

    def test_shorthand_initializer_inside_a_pattern(self):
        assignment = self.statement("({a = 1} = {});").children[0]
        prop = assignment.children[0].children[0]
        self.assertEqual(prop.children[1].kind, "AssignmentPattern")

    def test_template_literal_spans_its_substitutions(self):
        source = "`a${b}c${d}`;"
        template = self.statement(source).children[0]
        self.assertEqual(template.kind, "TemplateLiteral")
        self.assertEqual((template.start, template.end), (0, len(source) - 1))
        self.assertEqual([child.text for child in template.children], ["b", "d"])

    def test_operator_precedence_and_associativity(self):
        expression = self.statement("a + b * c - d;").children[0]
        self.assertEqual(expression.text, "-")
        self.assertEqual(expression.children[0].text, "+")
        self.assertEqual(expression.children[0].children[1].text, "*")
        power = self.statement("a ** b ** c;").children[0]
        self.assertEqual(power.children[1].text, "**")

    def test_automatic_semicolon_before_increment_on_the_next_line(self):
        statements = J.parse("a\n++b").children
        self.assertEqual([s.kind for s in statements], ["ExpressionStatement", "ExpressionStatement"])

    def test_slash_is_division_or_regexp_by_position(self):
        division = self.statement("x = a / b / c;").children[0].children[1]
        self.assertEqual(division.kind, "BinaryExpression")
        regexp = self.statement("x = /b/g;").children[0].children[1]
        self.assertEqual(regexp.kind, "RegExpLiteral")
        self.assertEqual(regexp.text, "/b/g")

    def test_class_members(self):
        cls = self.statement("class A { static x = 1; #y; get z() {} static { } constructor() {} }")
        self.assertEqual([m.kind for m in cls.children],
                         ["Identifier", "FieldDefinition", "FieldDefinition", "MethodDefinition",
                          "StaticBlock", "MethodDefinition"])
        self.assertEqual(cls.children[-1].text, "constructor")

    def test_import_and_export_specifiers(self):
        imports = self.statement("import d, {a as b} from 'm';")
        self.assertEqual(imports.kind, "ImportDeclaration")
        self.assertEqual([child.kind for child in imports.children],
                         ["ImportDefaultSpecifier", "ImportSpecifier", "Literal"])
        exports = J.parse("export {x as y};").children[0]
        self.assertEqual(exports.children[0].kind, "ExportSpecifier")

    def test_walk_lists_every_node_once(self):
        tree = J.parse("f(a, b);")
        kinds = [node.kind for node in tree.walk()]
        self.assertEqual(kinds[:3], ["Program", "ExpressionStatement", "CallExpression"])
        self.assertEqual(kinds.count("Identifier"), 3)


class DiagnosticsTests(unittest.TestCase):
    DETECTION = Detection("ecmascript", None, None, "extension")

    def test_modern_code_has_no_diagnostics(self):
        text = "class A {}\nconst f = (a) => `x${a}`;\n"
        self.assertEqual(diagnostics.analyze(text, self.DETECTION), [])

    def test_a_real_error_in_modern_code_is_reported_at_its_position(self):
        found = diagnostics.analyze("class A {}\nlet y = 1 +;\n", self.DETECTION)
        self.assertEqual([(d.line, d.column, d.code) for d in found], [(2, 12, "js-syntax")])
        self.assertEqual(found[0].message, "unexpected ';'")


if __name__ == "__main__":
    unittest.main()
