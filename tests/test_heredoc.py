import os
import shutil
import subprocess
import tempfile
import unittest

from ogmkdev import heredoc as H


def php_lint(source: str):
    """Return None if PHP accepts the source, else the PHP error text."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.php")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        result = subprocess.run(["php", "-l", path], capture_output=True, text=True)
        return None if result.returncode == 0 else result.stdout + result.stderr


@unittest.skipUnless(shutil.which("php"), "php not installed")
class PhpAgreementTests(unittest.TestCase):
    def check(self, source, expect_ok):
        scan = H.scan(source)
        php_error = php_lint(source)
        self.assertEqual(php_error is None, expect_ok, php_error)
        self.assertEqual(not scan.errors, expect_ok, scan.errors)

    def test_matching_labels_are_valid_in_php_and_here(self):
        src = "<?php\n$s = <<<HEREDOC\n    line one\n    HEREDOC;\necho $s;\n"
        self.check(src, True)

    def test_nowdoc_and_flexible_closing_indent(self):
        src = "<?php\n$n = <<<'RAW'\n  a $b\n  RAW;\n"
        self.check(src, True)

    def test_mismatched_closing_label_is_unterminated_in_php_and_here(self):
        src = "<?php\n$s = <<<HEREDOC\nhello\nENDDOC;\n"
        self.check(src, False)
        self.assertEqual(H.scan(src).errors[0].code, "unterminated")


class HeredocScannerTests(unittest.TestCase):
    def test_value_has_closing_indent_removed_and_final_newline_dropped(self):
        src = "<?php\n    $s = <<<EOT\n        one\n          two\n        EOT;\n"
        span = H.scan(src).spans[0]
        self.assertEqual(span.kind, "heredoc")
        self.assertEqual(span.label, "EOT")
        self.assertEqual(span.indent, "        ")
        self.assertEqual(span.value, "one\n  two")

    def test_nowdoc_kind(self):
        span = H.scan("<?php $x = <<<'N'\nraw\nN;\n").spans[0]
        self.assertEqual((span.kind, span.value), ("nowdoc", "raw"))

    def test_label_prefix_inside_body_is_not_a_closing_label(self):
        src = "<?php\n$s = <<<T\nTHEN is body\nTx\nT;\n"
        span = H.scan(src).spans[0]
        self.assertEqual(span.value, "THEN is body\nTx")

    def test_opener_inside_string_or_comment_is_ignored(self):
        src = "<?php\n$a = '<<<X';\n// <<<Y\n# <<<Z\n/* <<<W */\n$b = \"<<<Q\";\n"
        self.assertEqual(H.scan(src).spans, ())
        self.assertEqual(H.scan(src).errors, ())

    def test_attribute_is_not_a_comment(self):
        src = "<?php\n#[Attr]\n$s = <<<A\nx\nA;\n"
        self.assertEqual(len(H.scan(src).spans), 1)

    def test_html_before_php_is_not_scanned(self):
        src = "<p><<<X</p>\n<?php $s = <<<X\nok\nX;\n"
        self.assertEqual([s.value for s in H.scan(src).spans], ["ok"])

    def test_bad_indent_is_reported(self):
        src = "<?php\n$s = <<<A\n  ok\nbad\n    A;\n"
        errors = H.scan(src).errors
        self.assertEqual(errors[0].code, "bad_indent")


if __name__ == "__main__":
    unittest.main()
