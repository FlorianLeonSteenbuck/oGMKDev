import unittest

from ogmkdev import sql as S


class EngineTests(unittest.TestCase):
    def test_innodb_mysql_canonical(self):
        [clause] = S.engine_clauses("CREATE TABLE t (id INT) ENGINE=InnoDB;", "mysql")
        self.assertEqual((clause.name, clause.canonical, clause.problem), ("InnoDB", "InnoDB", None))

    def test_engine_name_is_case_insensitive_with_canonical_spelling(self):
        [clause] = S.engine_clauses("CREATE TABLE t (id INT) engine = innodb;", "mysql")
        self.assertEqual((clause.canonical, clause.problem), ("InnoDB", None))

    def test_engine_without_equals_needs_a_known_name(self):
        [clause] = S.engine_clauses("CREATE TABLE t (id INT) ENGINE MyISAM;", "mysql")
        self.assertEqual(clause.canonical, "MyISAM")
        self.assertEqual(S.engine_clauses("CREATE TABLE t (engine VARCHAR(20));", "mysql"), [])

    def test_unknown_engine_is_flagged(self):
        [clause] = S.engine_clauses("CREATE TABLE t (id INT) ENGINE=Btrfs;", "mysql")
        self.assertEqual(clause.problem, "unknown_engine")

    def test_mariadb_extra_engines(self):
        [clause] = S.engine_clauses("CREATE TABLE t (id INT) ENGINE=Aria;", "mariadb")
        self.assertIsNone(clause.problem)
        [mysql_only] = S.engine_clauses("CREATE TABLE t (id INT) ENGINE=Aria;", "mysql")
        self.assertEqual(mysql_only.problem, "unknown_engine")

    def test_engine_outside_mysql_is_not_supported(self):
        [clause] = S.engine_clauses("CREATE TABLE t (id INT) ENGINE=InnoDB;", "postgresql")
        self.assertEqual(clause.problem, "not_supported")
        self.assertEqual(S.engine_clauses("UPDATE t SET engine = 'x';", "postgresql"), [])

    def test_strings_identifiers_and_comments_are_skipped(self):
        sql = ("INSERT INTO t VALUES ('ENGINE=InnoDB');\n"
               "-- ENGINE=MyISAM\n"
               "/* ENGINE=Aria */\n"
               "SELECT `ENGINE=CSV` FROM t;\n")
        self.assertEqual(S.engine_clauses(sql, "mysql"), [])

    def test_backslash_escaped_quote_in_mysql_string(self):
        sql = "SELECT 'it\\'s ENGINE=MEMORY' ; CREATE TABLE t (i INT) ENGINE=MEMORY;"
        clauses = S.engine_clauses(sql, "mysql")
        self.assertEqual([c.canonical for c in clauses], ["MEMORY"])

    def test_mysqldump_executable_comment_is_scanned(self):
        sql = "/*!40101 SET x=1 */;\n/*!50100 ... ENGINE=InnoDB */;"
        clauses = S.engine_clauses(sql, "mysql")
        self.assertEqual([c.canonical for c in clauses], ["InnoDB"])

    def test_default_engine(self):
        self.assertEqual(S.default_engine("mysql"), "InnoDB")
        self.assertIsNone(S.default_engine("mssql"))


if __name__ == "__main__":
    unittest.main()
