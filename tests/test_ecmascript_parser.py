import unittest

from ogmkdev.parsers import ecmascript as J


def leaves(source):
    return [leaf.text for leaf in J.parse(source).leaves() if leaf.text]


class ParserAcceptsTests(unittest.TestCase):
    def test_declarations_statements_and_functions(self):
        self.assertEqual(leaves("var x = 1;"), ["var", "x", "=", "1", ";"])
        J.parse("function f(a, b) { return a + b * 2; }")
        J.parse("if (x) { y(); } else { z = 3; }")
        J.parse("var o = {a: [1, 2], 'b': function(){ return this; }};")

    def test_regular_expression_is_decided_by_the_grammar(self):
        self.assertEqual(leaves("x = a / b / c"), ["x", "=", "a", "/", "b", "/", "c"])
        self.assertIn("/ab+c/g", leaves("x = /ab+c/g.test(s);"))
        self.assertIn("/[/]/", leaves("var r = /[/]/;"))

    def test_automatic_semicolon_at_line_break_and_before_brace(self):
        self.assertEqual(leaves("a = b\n++c").count("++"), 1)
        J.parse("function f() {\n  return x\n}")

    def test_restricted_return_ends_the_statement(self):
        tree = J.parse("return\n1")
        self.assertIn("1", leaves("return\n1"))
        self.assertIsNotNone(tree)

    def test_empty_program_has_only_the_start_token(self):
        self.assertEqual(leaves(""), [])
        self.assertEqual(leaves("x"), ["x"])


class ParserErrorTests(unittest.TestCase):
    def assertError(self, source, line, column, fragment):
        with self.assertRaises(J.ParseError) as caught:
            J.parse(source)
        self.assertEqual((caught.exception.line, caught.exception.column), (line, column))
        self.assertIn(fragment, caught.exception.message)

    def test_unexpected_token_position(self):
        self.assertError("var = 3;", 1, 5, "unexpected '='")

    def test_missing_operand_at_end_of_input(self):
        self.assertError("x = 1 +", 1, 8, "end of file")

    def test_unterminated_string_and_regexp(self):
        self.assertError("x = 'open", 1, 5, "unterminated string literal")
        self.assertError("var y = /x", 1, 9, "unterminated regular expression")

    def test_constructs_the_grammar_lacks_are_reported_clearly(self):
        self.assertError("a => 1", 1, 3, "'=>' is not supported")
        self.assertError("class A {}", 1, 7, "unexpected identifier 'A'")


if __name__ == "__main__":
    unittest.main()
