import unittest

from ogmkdev import templates as T


class TemplateTests(unittest.TestCase):
    def test_expand_defaults_overrides_and_cursor(self):
        tpl = T.Template("for", "python", "for ${item:item} in ${collection:items}:\n    $0")
        out = T.expand(tpl, {"item": "row"})
        self.assertEqual(out.text, "for row in items:\n    ")
        self.assertEqual(out.cursor, len("for row in items:\n    "))

    def test_required_variable_without_value_is_left_visible(self):
        tpl = T.Template("t", "sql", "SELECT ${columns} FROM ${table:t}")
        self.assertEqual(T.expand(tpl).text, "SELECT ${columns} FROM t")
        self.assertEqual(T.variable_names(tpl.body), ["columns", "table"])

    def test_completion_filters_by_language_prefix_and_dialect(self):
        reg = T.builtin_registry()
        self.assertEqual([t.trigger for t in reg.complete("fo", "php")], ["foreach"])
        self.assertEqual([t.trigger for t in reg.complete("", "python")], ["def", "for"])
        mysql = [t.trigger for t in reg.complete("create", "sql", "mysql")]
        generic = [t.trigger for t in reg.complete("create", "sql", "oracle")]
        self.assertEqual(mysql, ["createtable"])
        self.assertEqual(generic, [])

    def test_create_table_template_carries_engine_variable(self):
        reg = T.builtin_registry()
        tpl = reg.complete("createtable", "sql", "mysql")[0]
        self.assertIn("ENGINE=InnoDB", T.expand(tpl).text)
        self.assertIn("ENGINE=MyISAM", T.expand(tpl, {"engine": "MyISAM"}).text)


if __name__ == "__main__":
    unittest.main()
