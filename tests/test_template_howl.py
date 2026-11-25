import unittest

from ogmkdev import templates


class HowlRowsTest(unittest.TestCase):
    def test_one_row_per_template_with_the_body_escaped(self):
        registry = templates.TemplateRegistry([
            templates.Template("if", "php", "if (${condition:true}) {\n    $0\n}", "if block"),
            templates.Template("tab", "*", "a\tb\\c", "escapes"),
        ])
        self.assertEqual("if\tif (${condition:true}) {\\n    $0\\n}\ntab\ta\\tb\\\\c",
                         templates.howl_rows(registry))

    def test_every_built_in_template_decodes_to_its_body(self):
        for template in templates.builtin_registry().templates:
            trigger, body = templates.howl_rows(templates.TemplateRegistry([template])).split("\t", 1)
            self.assertEqual(template.trigger, trigger)
            self.assertEqual(template.body, templates.unescape(body))

    def test_no_templates_give_no_rows(self):
        self.assertEqual("", templates.howl_rows(templates.TemplateRegistry([])))

    def test_a_template_with_variables_is_refused(self):
        registry = templates.TemplateRegistry([templates.Template("x", "php", "$0", "", None, {"a": "b"})])
        with self.assertRaises(ValueError):
            templates.howl_rows(registry)


if __name__ == "__main__":
    unittest.main()
