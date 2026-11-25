import os
import tempfile
import unittest

from ogmkdev.document import Document


class DocumentTests(unittest.TestCase):
    def test_open_save_and_save_as_reload_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, ".editorconfig"), "w", encoding="utf-8") as h:
                h.write("root = true\n[*]\nindent_size = 2\n[*.sql]\nogmkdev_language = postgresql\n")
            path = os.path.join(tmp, "a.txt")
            with open(path, "w", encoding="utf-8") as h:
                h.write("x\n")
            doc = Document.open(path)
            self.assertEqual(doc.settings.indent_size, 2)
            doc.text = "CREATE TABLE t (i INT) ENGINE=InnoDB;\n"
            target = os.path.join(tmp, "schema.sql")
            doc.save(target)
            self.assertEqual(doc.path, target)
            self.assertEqual(doc.detection.dialect, "postgresql")
            self.assertEqual([d.code for d in doc.diagnostics], ["sql-not_supported"])
            with open(target, encoding="utf-8") as h:
                self.assertEqual(h.read(), "CREATE TABLE t (i INT) ENGINE=InnoDB;\n")

    def test_new_document_has_no_path_and_cannot_be_saved(self):
        doc = Document.new()
        self.assertEqual(doc.title, "untitled")
        with self.assertRaises(ValueError):
            doc.save()


if __name__ == "__main__":
    unittest.main()
