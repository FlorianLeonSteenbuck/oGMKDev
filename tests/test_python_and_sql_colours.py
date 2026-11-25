import unittest

from ogmkdev import highlight as H
from ogmkdev.lexers import python_lexer as P
from ogmkdev.lexers import sql_keywords as K
from ogmkdev.lexers import sql_lexer as S


def python_kinds(source):
    return [(t.kind, source[t.start:t.end]) for t in P.tokenize(source)]


class PythonLexerTests(unittest.TestCase):
    def test_keywords_names_strings_comments_numbers_and_operators(self):
        self.assertEqual(python_kinds("def f(x): return 'a' + 1  # c\n"),
                         [("keyword", "def"), ("identifier", "f"), ("operator", "("),
                          ("identifier", "x"), ("operator", ")"), ("operator", ":"),
                          ("keyword", "return"), ("string", "'a'"), ("operator", "+"),
                          ("number", "1"), ("comment", "# c")])

    def test_triple_quoted_strings_span_lines(self):
        self.assertIn(("string", '"""doc\nmore"""'), python_kinds('y = """doc\nmore"""\n'))

    def test_an_f_string_is_a_string_and_its_expression_is_code(self):
        kinds = python_kinds('x = f"a{b}c"\n')
        self.assertIn(("string", 'f"'), kinds)
        self.assertIn(("identifier", "b"), kinds)

    def test_incomplete_text_keeps_the_tokens_read_so_far(self):
        self.assertEqual(python_kinds("x = 1\ny = (2,")[:3],
                         [("identifier", "x"), ("operator", "="), ("number", "1")])

    def test_highlight_spans_for_python_and_pypy(self):
        source = "import os  # note"
        expected = [("keyword", 0, 6), ("comment", 11, 17)]
        self.assertEqual(H.spans("python", source), expected)
        self.assertEqual(H.spans("pypy", source), expected)


class SqlDialectTests(unittest.TestCase):
    def keywords(self, source, dialect):
        return [source[t.start:t.end] for t in S.tokenize(source, dialect) if t.kind == "keyword"]

    def test_top_is_a_keyword_only_in_transact_sql(self):
        self.assertIn("TOP", self.keywords("SELECT TOP 1 x FROM t", "mssql"))
        self.assertNotIn("TOP", self.keywords("SELECT TOP 1 x FROM t", "generic"))

    def test_returning_is_a_postgresql_keyword(self):
        sql = "INSERT INTO t VALUES (1) RETURNING id"
        self.assertIn("RETURNING", self.keywords(sql, "postgresql"))
        self.assertNotIn("RETURNING", self.keywords(sql, "mysql"))

    def test_mysql_keeps_howls_keyword_list(self):
        self.assertIn("SHOW", self.keywords("SHOW TABLES", "mysql"))
        self.assertIn("SHOW", self.keywords("SHOW TABLES", "mariadb"))
        self.assertNotIn("SHOW", self.keywords("SHOW TABLES", "generic"))

    def test_unknown_or_missing_dialect_uses_the_generic_set(self):
        self.assertIs(K.keywords_for("no-such-dialect"), K.ANSI_KEYWORDS)
        self.assertIs(K.keywords_for(None), K.ANSI_KEYWORDS)

    def test_every_dialect_of_the_language_has_a_set(self):
        for dialect in ("generic", "oracle", "apache-hive", "mysql", "mariadb", "mssql", "postgresql"):
            self.assertIn(dialect, K.KEYWORDS_BY_DIALECT)

    def test_highlight_passes_the_dialect_on(self):
        self.assertIn(("keyword", 7, 10), H.spans("sql", "SELECT TOP 1", "mssql"))
        self.assertNotIn(("keyword", 7, 10), H.spans("sql", "SELECT TOP 1", "generic"))


if __name__ == "__main__":
    unittest.main()
