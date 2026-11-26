import unittest

from ogmkdev import diagnostics
from ogmkdev.languages import Detection
from ogmkdev.parsers import php as P

VALID = [
    "<?php echo 1;",
    "<?php namespace App\\Models; use Foo\\Bar as Baz, Qux; use function Foo\\bar; use const Foo\\BAZ; use Foo\\{A, B as C};",
    "<?php enum Suit: string implements HasLabel { case Hearts = 'H'; const X = 1; public function label(): string { return $this->name; } }",
    "<?php readonly class P {}",
    "<?php abstract class A { abstract protected function f(int $x): static; final public const X = 1; }",
    "<?php interface I extends J, K { const C = 1; public function m(): void; }",
    "<?php trait T { use U, V { U::f insteadof V; V::f as protected g; h as private; } }",
    "<?php $f = fn($x) => $x * 2; $g = static fn() => 1; $h = function(&$a) use (&$b, $c): ?int { return 1; };",
    "<?php $r = match(true) { $a > 1, $a < 0 => 'x', default => 'y', };",
    "<?php $o?->m()?->p; $x = $o::CONST; $y = Foo::class; $z = $o::{$name}(); $w = Foo::$bar;",
    "<?php $a = strlen(...); $b = $o->m(...); $c = Foo::bar(...);",
    "<?php f(a: 1, b: 2); f(...$args); $x = [...$a, ...$b];",
    "<?php [$p, [$q, $r]] = $nested; foreach ($arr as ['x' => $x]) {}",
    "<?php while (true): break; endwhile; for ($i=0;$i<2;$i++): endfor; foreach ($a as $v): endforeach; switch ($x): case 1: break; endswitch;",
    "<?php if ($a): echo 1; elseif ($b): echo 2; else: echo 3; endif;",
    "<?php switch ($x) { case 1: case 2; break; default: }",
    "<?php try { throw new Exception('x'); } catch (A | B $e) { } catch (C) { } finally { }",
    "<?php function &gen(): iterable { yield 1; yield 'k' => 2; } function g() { $x = yield from other(); }",
    "<?php $s = <<<EOT\nHello $name\nEOT;\n$n = <<<'X'\nraw\nX;",
    "<?php global $a, $b; static $c = 1, $d; unset($a, $b[0]); isset($x, $y); empty($z);",
    "<?php declare(strict_types=1); exit(0);",
    "<?php #[Attr(1), Other] final class A { #[Id] public int $x = 0; public function __construct(private readonly int $y = 2, public ?string $z = null) {} }",
    "<?php $x = new class(1) extends A implements I { }; $k = new (get())(); $l = new static; new self();",
    "<?php echo $a instanceof B ? 'y' : 'n';",
    "<?php goto end; echo 1; end: echo 2;",
    "<?php const A = 1, B = [1, 2]; define('X', 3);",
    "<?php echo \"Hello {$user->name} ${var} $arr[0]\";",
    "<?php $v = 0o17 + 0b101 + 0x1F + 1_000_000 + 1.5e3;",
    "<?php function f(int|string $a, A&B $b, ?C $c = null, mixed ...$rest): never {}",
    "<?php namespace { echo 1; } namespace A { }",
    "<?php $a = $b <=> $c; $d = $e ** -1; $f = -$g ** 2; $h = $i . $j . 'k';",
    "<?php echo 1 ?>\n<p>html</p>\n<?= $x ?>\n<?php echo 2;",
    "<?php class A { public static function f() { return static::class; } }",
    "<?php if ($a) echo 1; else if ($b) echo 2; else echo 3;",
    "<?php return 5;",
    "<?php $x = new class { public function __construct(public int $v = 0) {} };",
    "<?php ${'x'} = 1; $$name = 2; ${$a . 'b'}[0] = 3;",
    "<?php class A { const B = self::C; public $p = [1]; public static $s; var $old; }",
    "<?php $x = 1 <=> 2 ?: 3; echo 1 and 0 or 2 xor 3; $q = $x ? : 2;",
    "<?php function f(): ?array { return null; } function g(): (A&B)|null {}",
    "<?php enum E { case A; case B; }",
    "<?php $c = clone $o; $d = clone $o->p; print 1 + 2; $z = include 'a.php';",
    "<?php $x = match($y) { 1 => fn() => 2, };",
]

INVALID = [
    "<?php echo 1",
    "<?php $t = ;",
    "<?php if ($a) { echo 1;",
    "<?php function f( { }",
    "<?php class { }",
    "<?php $a = [1, 2;",
    "<?php foreach ($a $v) {}",
    "<?php echo \"x\" \"y\";",
    "<?php $x == ;",
    "<?php new;",
    "<?php case 1: ;",
    "<?php return return;",
    "<?php $a->;",
    "<?php $a = 1 +;",
    "<?php if $a { }",
    "<?php while () {}",
    "<?php class A { public function }",
    "<?php echo 'unterminated",
    "<?php $x = if;",
    "<?php $a = class;",
]


class PhpParserTests(unittest.TestCase):
    def test_valid_programs_parse(self):
        for source in VALID:
            with self.subTest(source=source[:60]):
                P.parse(source)

    def test_invalid_programs_are_rejected(self):
        for source in INVALID:
            with self.subTest(source=source):
                with self.assertRaises(P.ParseError):
                    P.parse(source)

    def test_error_position_and_message(self):
        with self.assertRaises(P.ParseError) as caught:
            P.parse("<?php\n$t = ;\n")
        self.assertEqual((caught.exception.line, caught.exception.column), (2, 6))
        self.assertIn("unexpected ';'", caught.exception.message)

    def test_missing_terminator_names_the_next_token(self):
        with self.assertRaises(P.ParseError) as caught:
            P.parse("<?php echo 1 echo 2;")
        self.assertIn("missing ';' before keyword 'echo'", caught.exception.message)

    def test_unclosed_brace_names_the_opener(self):
        with self.assertRaises(P.ParseError) as caught:
            P.parse("<?php\nif ($a) {\n echo 1;\n")
        self.assertIn("to match '{' on line 2", caught.exception.message)

    def test_tree_has_the_statement_kinds(self):
        tree = P.parse("<?php function f($x) { return $x; } class A {}")
        self.assertEqual([child.kind for child in tree.children],
                         ["FunctionDeclaration", "ClassDeclaration"])

    def test_declare_directives_are_name_value_pairs(self):
        tree = P.parse("<?php declare(strict_types=1);")
        self.assertEqual(tree.children[0].children[0].kind, "Directive")


class PhpDiagnosticsTests(unittest.TestCase):
    DETECTION = Detection("php", "8.3", None, "extension")

    def test_a_syntax_error_is_reported(self):
        found = diagnostics.analyze("<?php\n$total = ;\n", self.DETECTION)
        self.assertEqual([(d.line, d.column, d.code) for d in found], [(2, 10, "php-syntax")])

    def test_valid_php_has_no_syntax_diagnostics(self):
        self.assertEqual(diagnostics.analyze("<?php echo 'ok';\n", self.DETECTION), [])

    def test_a_broken_heredoc_is_left_to_the_heredoc_check(self):
        found = diagnostics.analyze("<?php\n$x = <<<EOT\nabc\n", self.DETECTION)
        self.assertTrue(all(d.code != "php-syntax" for d in found))


def _class_names(tree):
    """The names of the class declarations of a tree, in source order."""
    return [next(c.text for c in node.children if c.kind == "Name")
            for node in tree.walk() if node.kind == "ClassDeclaration"]


def _method_names(node):
    return [next(c.text for c in member.children if c.kind == "Name")
            for member in node.walk() if member.kind == "MethodDeclaration"]


class PartialParseTest(unittest.TestCase):
    """parse_partial: the tree keeps what parses around a syntax error, and the errors say what did not."""

    def test_a_broken_statement_keeps_the_declarations_around_it(self):
        tree, errors = P.parse_partial("<?php\nclass A {}\n$x = ;\nclass B {}\n")
        self.assertEqual(_class_names(tree), ["A", "B"])
        self.assertEqual([(error.line, error.column) for error in errors], [(3, 6)])

    def test_a_broken_method_keeps_the_class_and_its_other_methods(self):
        source = "<?php\nclass C { public function ok() {} public function broken( {} public function after() {} }\n"
        tree, errors = P.parse_partial(source)
        self.assertEqual(_class_names(tree), ["C"])
        self.assertEqual(_method_names(tree), ["ok", "after"])
        self.assertEqual((errors[0].line, errors[0].column), (2, 59))

    def test_a_stray_brace_is_skipped_and_the_parser_moves_on(self):
        tree, errors = P.parse_partial("<?php } class D {}\n")
        self.assertEqual(_class_names(tree), ["D"])
        self.assertEqual([error.message for error in errors], ["unexpected '}'"])

    def test_an_unterminated_string_gives_an_error_and_keeps_what_came_before(self):
        tree, errors = P.parse_partial("<?php\nclass E {}\n$s = \"abc;\n")
        self.assertEqual(_class_names(tree), ["E"])
        self.assertTrue(errors)

    def test_parse_still_raises_the_first_error(self):
        with self.assertRaises(P.ParseError) as caught:
            P.parse("<?php\nclass A {}\n$x = ;\n")
        self.assertEqual((caught.exception.line, caught.exception.column), (3, 6))

    def test_a_group_use_gives_each_item_the_prefix_of_its_group(self):
        tree, _errors = P.parse_partial("<?php\nuse App\\Util\\{Helper, Money as M};\n")
        items = [node for node in tree.walk() if node.kind == "UseItem"]
        self.assertEqual([item.text for item in items], ["App\\Util", "App\\Util"])


class AsymmetricVisibilityTest(unittest.TestCase):
    """PHP 8.4 asymmetric visibility: a property can be read more widely than it is written, as in private(set)."""

    def test_the_properties_with_asymmetric_visibility_parse(self):
        tree = P.parse("<?php class A { public private(set) int $x; protected(set) ?string $y = null; }")
        properties = [node for node in tree.walk() if node.kind == "PropertyDeclaration"]
        self.assertEqual(len(properties), 2)
        self.assertEqual([node.children[-1].children[0].text for node in properties], ["$x", "$y"])


class CatchVariableTest(unittest.TestCase):
    """A catch clause keeps its variable as a node; a clause without one has no Variable child."""

    def test_the_catch_variable_is_a_node_of_its_clause(self):
        tree = P.parse("<?php try {} catch (E $e) {} catch (F) {}")
        clauses = [node for node in tree.walk() if node.kind == "CatchClause"]
        self.assertEqual(len(clauses), 2)
        self.assertEqual([child.text for child in clauses[0].children if child.kind == "Variable"], ["$e"])
        self.assertNotIn("Variable", [child.kind for child in clauses[1].children])


if __name__ == "__main__":
    unittest.main()
