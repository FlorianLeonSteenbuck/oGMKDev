import os
import tempfile
import unittest

from ogmkdev import editorconfig as E
from ogmkdev import templates as T


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class ConfiguredTemplateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def registry_for_file(self, rel):
        path = os.path.join(self.root, rel)
        settings = E.settings_for(path)
        from ogmkdev import languages
        detection = languages.detect(path, settings.custom)
        return T.registry_for(detection.language, detection.dialect, settings.custom, detection.template)

    def test_config_template_keeps_case_and_escapes_and_replaces_builtin(self):
        write(self.root, ".editorconfig", "root = true\n[*.php]\n"
              "ogmkdev_template_foreach = Foreach (${xs:Items} as ${x:Item}) {\\n    $0\\n}\n")
        registry = self.registry_for_file("a.php")
        found = registry.complete("foreach")
        self.assertEqual(len(found), 1)
        self.assertEqual(T.expand(found[0]).text, "Foreach (Items as Item) {\n    \n}")

    def test_directory_scope_selects_files_and_their_language(self):
        write(self.root, ".editorconfig", "root = true\n"
              "[legacy/**]\nogmkdev_language = php\nogmkdev_template_Hello = echo \"Hello\";$0\n")
        inside = self.registry_for_file("legacy/old/a.txt")
        outside = self.registry_for_file("modern/a.txt")
        self.assertIn("hello", [t.trigger for t in inside.complete("hel")])
        self.assertEqual(outside.complete("hel"), [])
        # a directory scope can also use the language of its files
        self.assertTrue(any(t.trigger == "foreach" for t in inside.complete("fore")))

    def test_nested_config_overrides_the_parent_template(self):
        write(self.root, ".editorconfig", "root = true\n[*]\nogmkdev_template_todo = TODO: $0\n")
        write(self.root, "sub/.editorconfig", "[*]\nogmkdev_template_todo = FIXME: $0\n")
        parent = self.registry_for_file("a.txt").complete("todo")[0]
        child = self.registry_for_file("sub/b.txt").complete("todo")[0]
        self.assertEqual(T.expand(parent).text.strip(), "TODO:")
        self.assertEqual(T.expand(child).text.strip(), "FIXME:")

    def test_invalid_trigger_names_are_ignored(self):
        custom = {"ogmkdev_template_Bad": "x", "ogmkdev_template_ok-one": "y", "other": "z"}
        self.assertEqual([t.trigger for t in T.from_config(custom)], ["ok-one"])

    def test_config_templates_apply_to_any_language(self):
        write(self.root, ".editorconfig", "root = true\n[*]\nogmkdev_template_sig = -- $0\n")
        self.assertEqual([t.trigger for t in self.registry_for_file("q.sql").complete("sig")], ["sig"])
        self.assertEqual([t.trigger for t in self.registry_for_file("q.bd").complete("sig")], ["sig"])


if __name__ == "__main__":
    unittest.main()
