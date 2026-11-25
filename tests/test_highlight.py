import unittest

from ogmkdev import highlight as H


class HighlightTests(unittest.TestCase):
    def test_ecmascript_spans(self):
        spans = H.spans("ecmascript", "var s = 'x'; // c")
        self.assertIn(("keyword", 0, 3), spans)
        self.assertIn(("string", 8, 11), spans)
        self.assertIn(("comment", 13, 17), spans)

    def test_sql_engine_span(self):
        source = "CREATE TABLE t (i INT) ENGINE=InnoDB;"
        spans = H.spans("sql", source)
        start = source.index("InnoDB")
        self.assertIn(("engine", start, start + 6), spans)

    def test_baredown_spans_cover_tags(self):
        styles = {s for s, _, _ in H.spans("baredown", "= Title\n- item **b**\n")}
        self.assertTrue({"heading", "marker", "bullet", "bold"} <= styles)

    def test_unknown_language_has_no_spans(self):
        self.assertEqual(H.spans("text", "anything"), [])

    def test_every_style_has_a_tag_definition(self):
        produced = set()
        for language, text in (("ecmascript", "a = /x/ // c\n'q'"), ("sql", "SELECT 1 -- c"),
                               ("baredown", "= t\n- b\n+ o\n> q\n%% c\n----\n~~~\nx\n~~~\n**b** //i// |c| [[l]]")):
            produced |= {style for style, _, _ in H.spans(language, text)}
        self.assertLessEqual(produced, set(H.TAG_STYLES), produced - set(H.TAG_STYLES))


if __name__ == "__main__":
    unittest.main()
