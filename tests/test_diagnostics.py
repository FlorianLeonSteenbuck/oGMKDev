import unittest

from ogmkdev import diagnostics as D
from ogmkdev.languages import Detection


class DiagnosticsTests(unittest.TestCase):
    def test_php_mismatched_heredoc_label_is_an_error_with_position(self):
        text = "<?php\n$s = <<<HEREDOC\nhello\nENDDOC;\n"
        found = D.analyze(text, Detection("php", "8.4", None, "extension"))
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].line, found[0].column, found[0].severity), (2, 6, "error"))
        self.assertEqual(found[0].code, "heredoc-unterminated")

    def test_valid_php_has_no_diagnostics(self):
        text = "<?php\n$s = <<<T\n  ok\n  T;\n"
        self.assertEqual(D.analyze(text, Detection("php", "8.4", None, "extension")), [])

    def test_mustache_php_layer_is_not_scanned_as_php(self):
        text = "<?php\n$s = <<<T\nx\nENDDOC;\n"
        self.assertEqual(D.analyze(text, Detection("html", None, "mustache", "compound")), [])

    def test_sql_engine_checks_follow_dialect(self):
        text = "CREATE TABLE t (id INT) ENGINE=Btrfs;\nCREATE TABLE u (id INT) ENGINE=InnoDB;\n"
        mysql = D.analyze(text, Detection("sql", "mysql", None, "compound"))
        self.assertEqual([d.code for d in mysql], ["unknown_engine"])
        pg = D.analyze(text, Detection("sql", "postgresql", None, "compound"))
        self.assertEqual([d.code for d in pg], ["not_supported"])
        self.assertIn("InnoDB", "".join(d.message for d in pg))

    def test_summary(self):
        self.assertEqual(D.summary([]), "no diagnostics")
        found = D.analyze("<?php <<<X\n", Detection("php", "8.4", None, "extension"))
        self.assertIn("1 error(s)", D.summary(found))


if __name__ == "__main__":
    unittest.main()
