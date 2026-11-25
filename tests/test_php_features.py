import unittest

from ogmkdev import php_features as F
from ogmkdev.diagnostics import analyze, severity_setting
from ogmkdev.editorconfig import EditorSettings
from ogmkdev.languages import Detection

SAMPLES = {
    "attribute": "<?php #[Attr] class A {}",
    "nullsafe": "<?php $a?->b;",
    "match": "<?php match($x) { 1 => 2 };",
    "throw-expression": "<?php $a = $b ?? throw new E();",
    "named-arguments": "<?php f(name: 1);",
    "constructor-promotion": "<?php class A { function __construct(public int $x) {} }",
    "class-on-object": "<?php $o::class;",
    "non-capturing-catch": "<?php try {} catch (E) {}",
    "enum": "<?php enum S: string { case A = 'a'; }",
    "readonly-property": "<?php class A { public readonly int $x; }",
    "first-class-callable": "<?php $f = strlen(...);",
    "never-type": "<?php function f(): never {}",
    "pure-intersection-types": "<?php function f(A&B $x) {}",
    "octal-prefix": "<?php echo 0o17;",
    "readonly-class": "<?php readonly class A {}",
    "dnf-types": "<?php function f((A&B)|null $x) {}",
    "true-type": "<?php function f(): true {}",
    "typed-class-constants": "<?php class A { const int X = 1; }",
    "override-attribute": "<?php class A { #[\\Override] function f() {} }",
    "dynamic-class-constant": "<?php $c::{$n};",
    "property-hooks": "<?php class A { public int $x { get => 1; } }",
    "asymmetric-visibility": "<?php class A { public private(set) int $x; }",
    "new-without-parentheses": "<?php new A()->b();",
    "deprecated-attribute": "<?php #[\\Deprecated] function f() {}",
    "pipe-operator": "<?php $a |> strlen(?);",
    "clone-with": "<?php clone($a, ['x' => 1]);",
    "nodiscard-attribute": "<?php #[\\NoDiscard] function f() {}",
    "closure-in-constant": "<?php #[Attr(static fn() => 1)] class A {}",
    "partial-application": "<?php f(1, ...);",
    "readonly-defaults": "<?php class A { public readonly int $x = 1; }",
}


class FeatureDetectionTests(unittest.TestCase):
    def test_every_feature_is_detected_in_its_sample(self):
        for feature, source in SAMPLES.items():
            found = {f.feature for f in F.analyze(source)}
            self.assertIn(feature, found, source)

    def test_library_functions_and_classes(self):
        self.assertIn("function:clamp", {f.feature for f in F.analyze("<?php clamp(1, 2, 3);")})
        self.assertIn("function:array_first", {f.feature for f in F.analyze("<?php array_first($a);")})
        self.assertIn("class:SortDirection", {f.feature for f in F.analyze("<?php SortDirection::Asc;")})
        self.assertEqual(F.findings_above("<?php str_contains($a, 'b');", "7.4")[0].kind, "function")

    def test_versions_gate_findings(self):
        self.assertEqual(F.findings_above("<?php f(1, ...);", "8.6"), [])
        above = F.findings_above("<?php f(1, ...);", "8.5")
        self.assertEqual([f.feature for f in above], ["partial-application"])
        self.assertEqual(above[0].message, "partial function application (? and ... placeholders) needs PHP 8.6")

    def test_placeholder_and_first_class_callable_are_different(self):
        self.assertIn("first-class-callable", {f.feature for f in F.analyze("<?php f(...);")})
        self.assertNotIn("partial-application", {f.feature for f in F.analyze("<?php f(...);")})

    def test_diagnostics_use_per_feature_severity_settings(self):
        detection = Detection("php", "7.4", None, "extension")
        found = analyze("<?php match($x) { 1 => 2 };", detection, EditorSettings())
        self.assertEqual([(d.code, d.severity) for d in found], [("php-match", "error")])
        off = EditorSettings(custom={"ogmkdev_diagnostic_php_match": "off"})
        self.assertEqual(analyze("<?php match($x) { 1 => 2 };", detection, off), [])
        warn = EditorSettings(custom={"ogmkdev_diagnostic_php_match": "warning"})
        self.assertEqual(analyze("<?php match($x) { 1 => 2 };", detection, warn)[0].severity, "warning")
        everything_off = EditorSettings(custom={"ogmkdev_diagnostics": "off"})
        self.assertEqual(analyze("<?php match($x) { 1 => 2 };", detection, everything_off), [])

    def test_severity_setting_validates_values(self):
        self.assertEqual(severity_setting({"ogmkdev_diagnostic_php_match": "bogus"}, "php-match", "error"), "error")
        self.assertEqual(severity_setting({}, "php-match", "warning"), "warning")


if __name__ == "__main__":
    unittest.main()
