import os
import unittest

from ogmkdev import languages as L


class DetectionTests(unittest.TestCase):
    def d(self, name, custom=None, first=None):
        return L.detect(os.path.join("/x", name), custom, first)

    def test_plain_extensions(self):
        self.assertEqual(self.d("a.php").language, "php")
        self.assertEqual(self.d("a.py").language, "python")
        self.assertEqual(self.d("a.py").dialect, "3")
        self.assertEqual(self.d("a.ts").language, "typescript")
        self.assertEqual(self.d("a.tsx").language, "tsx")
        self.assertEqual(self.d("a.jsx").language, "jsx")
        self.assertEqual(self.d("a.mjs").language, "ecmascript")
        self.assertEqual(self.d("README.md").language, "markdown")
        self.assertEqual(self.d("notes.bin").language, "text")

    def test_template_compound_extensions(self):
        d = self.d("page.mustache.html")
        self.assertEqual((d.language, d.template, d.source), ("html", "mustache", "compound"))
        self.assertEqual(d.name, "Mustache (HTML)")
        t = self.d("view.twig.html")
        self.assertEqual((t.language, t.template), ("html", "twig"))
        x = self.d("tpl.mustache.x")  # unknown base extension: plain text inside the template
        self.assertEqual((x.language, x.template), ("text", "mustache"))

    def test_sql_dialect_suffix(self):
        d = self.d("schema.mysql.sql")
        self.assertEqual((d.language, d.dialect, d.source), ("sql", "mysql", "compound"))
        self.assertEqual(self.d("q.oracle.sql").dialect, "oracle")
        self.assertEqual(self.d("q.sql").dialect, "generic")

    def test_shebang_detection(self):
        self.assertEqual(L.language_for_shebang("#!/usr/bin/env pypy3"), ("pypy", "3"))
        self.assertEqual(L.language_for_shebang("#!/usr/bin/pypy"), ("pypy", "3"))
        self.assertEqual(L.language_for_shebang("#!/usr/bin/python2.7"), ("python", "2"))
        self.assertEqual(L.language_for_shebang("#!/usr/bin/env python3"), ("python", "3"))
        self.assertEqual(L.language_for_shebang("#!/usr/bin/env node"), ("ecmascript", "es2022"))
        self.assertIsNone(L.language_for_shebang("not a shebang"))
        self.assertEqual(self.d("run", first="#!/usr/bin/env python2").dialect, "2")

    def test_editorconfig_scope_overrides_name_and_dialect(self):
        d = self.d("tool.py", {"ogmkdev_language": "python", "ogmkdev_dialect": "2"})
        self.assertEqual((d.language, d.dialect, d.source), ("python", "2", "editorconfig"))
        d = self.d("data.txt", {"ogmkdev_language": "mysql"})
        self.assertEqual((d.language, d.dialect), ("sql", "mysql"))
        d = self.d("a.js", {"ogmkdev_language": "wscript"})
        self.assertEqual((d.language, d.dialect), ("ecmascript", "jscript"))
        d = self.d("page.html", {"ogmkdev_language": "mustache"})
        self.assertEqual((d.language, d.template), ("html", "mustache"))

    def test_invalid_scope_is_ignored(self):
        d = self.d("a.py", {"ogmkdev_language": "java"})  # Java is excluded on purpose
        self.assertEqual(d.language, "python")
        self.assertEqual(d.source, "extension")

    def test_dialect_only_scope_applies_to_detected_language(self):
        d = self.d("q.sql", {"ogmkdev_dialect": "postgresql"})
        self.assertEqual(d.dialect, "postgresql")


if __name__ == "__main__":
    unittest.main()
