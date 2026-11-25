import unittest

from ogmkdev.lexers import ecmascript_lexer as E


def kinds(source):
    return [(t.kind, source[t.start:t.end]) for t in E.tokenize(source) if t.kind != "comment"]


class EcmaScriptLexerTests(unittest.TestCase):
    def test_keywords_identifiers_numbers_and_punctuators(self):
        self.assertEqual(kinds("var x = 1.5e3 + y;"),
                         [("keyword", "var"), ("identifier", "x"), ("punctuator", "="),
                          ("number", "1.5e3"), ("punctuator", "+"), ("identifier", "y"),
                          ("punctuator", ";")])

    def test_longest_punctuator_wins(self):
        self.assertEqual([v for _, v in kinds("a >>>= b === c !== d ?.x")
                          if v in (">>>=", "===", "!==", "?.")], [">>>=", "===", "!==", "?."])

    def test_optional_chaining_before_digit_is_conditional(self):
        self.assertEqual([v for _, v in kinds("a?.5:1") if v in ("?", "?.")], ["?"])

    def test_numbers_hex_octal_binary_and_leading_dot(self):
        self.assertEqual([k for k, _ in kinds("0x1F 0o17 0b101 .5 10")], ["number"] * 5)

    def test_strings_with_escapes_and_line_continuation(self):
        self.assertEqual(kinds(r"'a\'b' " + '"c\\\nd"'), [("string", r"'a\'b'"), ("string", '"c\\\nd"')])

    def test_unterminated_string_is_an_error_token_on_its_line(self):
        found = E.problems("x = 'open\ny = 2")
        self.assertEqual(found, [(1, 5, "unterminated string literal")])

    def test_unterminated_comment_and_regexp_and_template(self):
        self.assertEqual(E.problems("/* never closed")[0][2], "unterminated comment")
        self.assertEqual(E.problems("var r = /abc\nx")[0][2], "unterminated regular expression")
        self.assertEqual(E.problems("s = `open")[0][2], "unterminated template literal")

    def test_slash_is_division_after_operands_and_regexp_after_operators(self):
        self.assertEqual([k for k, _ in kinds("a / b")], ["identifier", "punctuator", "identifier"])
        self.assertEqual([k for k, _ in kinds("x = /ab+c/gi")], ["identifier", "punctuator", "regexp"])
        self.assertEqual([k for k, _ in kinds("return /x/.test(s)")][:2], ["keyword", "regexp"])
        self.assertEqual([k for k, _ in kinds("(a) / 2")], ["punctuator", "identifier", "punctuator",
                                                             "punctuator", "number"])

    def test_regexp_class_may_contain_slash(self):
        self.assertEqual(kinds("r = /[/]x/")[-1], ("regexp", "/[/]x/"))

    def test_automatic_semicolon_information(self):
        tokens = E.tokenize("a\nb")
        self.assertFalse(tokens[0].newline_before)
        self.assertTrue(tokens[1].newline_before)

    def test_comments_are_tokens_and_do_not_hide_newlines(self):
        tokens = E.tokenize("a // note\nb")
        self.assertEqual([t.kind for t in tokens], ["identifier", "comment", "identifier"])
        self.assertTrue(tokens[2].newline_before)

    def test_unexpected_character_is_reported(self):
        self.assertEqual(E.problems("a # b")[0][2], "unexpected character")


if __name__ == "__main__":
    unittest.main()
