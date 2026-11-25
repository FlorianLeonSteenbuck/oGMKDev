import unittest

from ogmkdev import templates as T
from ogmkdev import languages


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

    def test_php_dollar_variables_are_literal(self):
        tpl = T.Template("t", "php", "$${name:x} = 1;")
        self.assertEqual(T.expand(tpl).text, "$x = 1;")

    def test_completion_filters_by_language_prefix_and_dialect(self):
        reg = T.builtin_registry()
        self.assertEqual([t.trigger for t in reg.complete("fo", "php")], ["foreach"])
        self.assertIn("for", [t.trigger for t in reg.complete("", "python")])
        self.assertNotIn("foreach", [t.trigger for t in reg.complete("", "python")])
        self.assertEqual([t.dialect for t in reg.complete("createtable", "sql", "mysql")
                          if t.dialect], ["mysql"])

    def test_create_table_template_carries_engine_variable(self):
        reg = T.builtin_registry()
        tpl = [t for t in reg.complete("createtable", "sql", "mysql") if t.dialect == "mysql"][0]
        self.assertIn("ENGINE=InnoDB", T.expand(tpl).text)
        self.assertIn("ENGINE=MyISAM", T.expand(tpl, {"engine": "MyISAM"}).text)

    def test_every_language_has_templates(self):
        for language in languages.LANGUAGES:
            if language == "text":
                continue
            dialect = languages.LANGUAGES[language].default_dialect
            self.assertTrue(T.registry_for(language, dialect, {}).complete(""), language)

    def test_dialect_specific_template_replaces_generic_one(self):
        generic = T.registry_for("sql", None, {}).complete("createtable")
        mysql = T.registry_for("sql", "mysql", {}).complete("createtable")
        self.assertEqual(len(generic), 1)
        self.assertEqual(mysql[0].dialect, "mysql")


if __name__ == "__main__":
    unittest.main()
