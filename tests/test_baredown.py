import unittest

from ogmkdev import baredown as B


class ParseTests(unittest.TestCase):
    def test_block_kinds_and_heading_levels(self):
        src = "= Title\n== Sub\n====== Deep\n- one\n+ first\n> quoted\n%% hidden\n----\n"
        kinds = [(b.kind, b.level) if b.kind == "heading" else b.kind for b in B.parse(src)]
        self.assertEqual(kinds, [("heading", 1), ("heading", 2), ("heading", 6), "bullet", "ordered",
                                 "quote", "comment", "rule"])

    def test_paragraph_lines_join_until_blank_line(self):
        blocks = B.parse("first line\nsecond line\n\nnext")
        self.assertEqual([(b.kind, b.text) for b in blocks],
                         [("paragraph", "first line second line"), ("paragraph", "next")])

    def test_fenced_code_keeps_text_verbatim_and_reports_unclosed(self):
        blocks = B.parse("~~~ python\n- not a list\n  **not bold**\n~~~\n")
        self.assertEqual((blocks[0].kind, blocks[0].language), ("code", "python"))
        self.assertEqual(blocks[0].text, "- not a list\n  **not bold**")
        self.assertEqual(B.problems("~~~\nx\n"), [(1, "unterminated code block: missing closing ~~~")])
        self.assertEqual(B.problems("~~~\nx\n~~~\n"), [])

    def test_fourth_dash_rule_is_not_a_bullet(self):
        self.assertEqual(B.parse("----")[0].kind, "rule")
        self.assertEqual(B.parse("- item")[0].kind, "bullet")


class InlineTests(unittest.TestCase):
    def test_inline_spans(self):
        spans = B.inline("a **b** //c// |d| [[Page]] [[Other|label]] e")
        self.assertEqual([(s.kind, s.text) for s in spans],
                         [("text", "a "), ("bold", "b"), ("text", " "), ("italic", "c"), ("text", " "),
                          ("code", "d"), ("text", " "), ("link", "Page"), ("text", " "),
                          ("link", "label"), ("text", " e")])
        self.assertEqual(spans[7].target, "Page")
        self.assertEqual(spans[9].target, "Other")

    def test_markdown_syntax_is_not_special(self):
        self.assertEqual([s.kind for s in B.inline("*not bold* _not italic_ # no")], ["text"])


class HtmlAndTokenTests(unittest.TestCase):
    def test_html_escapes_and_groups_lists(self):
        out = B.to_html("= <Hi>\n- a & b\n- c\n\n~~~\n<x>\n~~~")
        self.assertIn("<h1>&lt;Hi&gt;</h1>", out)
        self.assertIn("<ul>\n<li>a &amp; b</li>\n<li>c</li>\n</ul>", out)
        self.assertIn("<pre><code>&lt;x&gt;</code></pre>", out)
        self.assertNotIn("%%", B.to_html("%% secret"))

    def test_tokenize_marks_heading_and_inline_spans(self):
        src = "= Title **b**\n"
        kinds = [(t.kind, src[t.start:t.end]) for t in B.tokenize(src)]
        self.assertIn(("marker", "="), kinds)
        self.assertIn(("heading", "= Title **b**"), kinds)
        self.assertIn(("bold", "**b**"), kinds)

    def test_tokenize_code_block_lines(self):
        src = "~~~\nlet x\n~~~\n"
        kinds = [t.kind for t in B.tokenize(src)]
        self.assertEqual(kinds, ["fence", "code", "fence"])


if __name__ == "__main__":
    unittest.main()
