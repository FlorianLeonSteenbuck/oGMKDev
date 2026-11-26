"""The declarations and names of a PHP file, read from its parse tree (ogmkdev/php_analysis.py): the namespaces and
imports of the file and the names they resolve to, the members, and the classes the code refers to. Pure Python, no
display needed."""

import unittest

from ogmkdev import php_analysis as A
from ogmkdev.parsers import php as P

SOURCE = r"""<?php
namespace App\Shop {
    use App\Geometry\Base as Parent_;
    use App\Util\{Helper, Money};
    use function strlen;

    abstract class Cart extends Parent_ implements \Countable, Shape
    {
        use Loggable, Audit { Loggable::log insteadof Audit; }
        public const int LIMIT = 10;
        private ?Helper $helper = null;
        public function add(Money $price, Item $item): static
        {
            $x = new Line($price);
            if ($x instanceof Square) { }
            try { } catch (\RuntimeException | Oops $e) { }
            return self::make(Config::VERSION);
        }
        abstract protected function total(): int;
    }
}
namespace Other {
    interface Shape extends \Stringable { public function area(): float; }
    enum Suit: string { case Hearts = 'H'; const X = 1; }
    function helper(int $x): int { return strlen($x); }
    if (true) { class Hidden {} function nested() {} }
    $anon = new class extends Base { public function run() {} };
}
"""


def _analyse(source):
    tree, errors = P.parse_partial(source)
    return A.declarations(tree, source), A.occurrences(tree, source), errors


class DeclarationsTest(unittest.TestCase):
    def setUp(self):
        self.declarations, _occurrences, self.errors = _analyse(SOURCE)
        self.by_name = {declaration.name: declaration for declaration in self.declarations}

    def test_the_declarations_come_in_source_order_with_their_namespaces(self):
        self.assertEqual([d.name for d in self.declarations],
                         ["App\\Shop\\Cart", "Other\\Shape", "Other\\Suit", "Other\\helper", "Other\\Hidden"])
        self.assertEqual([d.kind for d in self.declarations], ["class", "interface", "enum", "function", "class"])
        self.assertEqual(self.errors, [])

    def test_a_class_resolves_its_supertypes_and_traits_through_imports_and_namespace(self):
        cart = self.by_name["App\\Shop\\Cart"]
        self.assertTrue(cart.abstract)
        self.assertEqual(cart.supertypes, ("App\\Geometry\\Base", "Countable", "App\\Shop\\Shape"))
        self.assertEqual(cart.traits, ("App\\Shop\\Loggable", "App\\Shop\\Audit"))

    def test_the_members_are_named_as_the_index_names_them(self):
        cart = self.by_name["App\\Shop\\Cart"]
        self.assertEqual([(m.kind, m.name) for m in cart.members], [
            ("constant", "LIMIT"), ("property", "$helper"), ("method", "add"), ("method", "total")])

    def test_members_have_the_line_and_column_of_their_names(self):
        add = next(m for m in self.by_name["App\\Shop\\Cart"].members if m.name == "add")
        self.assertEqual((add.line, add.column), (12, 25))

    def test_interfaces_are_abstract_and_enum_cases_are_constants(self):
        shape = self.by_name["Other\\Shape"]
        self.assertTrue(shape.abstract)
        self.assertEqual(shape.supertypes, ("Stringable",))
        suit = self.by_name["Other\\Suit"]
        self.assertEqual([(m.kind, m.name) for m in suit.members], [("constant", "Hearts"), ("constant", "X")])

    def test_a_class_in_a_block_counts_a_function_in_a_block_does_not(self):
        self.assertIn("Other\\Hidden", self.by_name)
        self.assertNotIn("Other\\nested", self.by_name)

    def test_the_references_of_a_class_are_the_classes_its_body_refers_to(self):
        self.assertEqual(self.by_name["App\\Shop\\Cart"].references, (
            "App\\Util\\Helper", "App\\Util\\Money", "App\\Shop\\Item", "App\\Shop\\Line", "App\\Shop\\Square",
            "RuntimeException", "App\\Shop\\Oops", "App\\Shop\\Config"))

    def test_a_broken_statement_keeps_the_declarations_around_it(self):
        declarations, _occurrences, errors = _analyse("<?php\nclass A {}\n$x = ;\nclass B {}\n")
        self.assertEqual([d.name for d in declarations], ["A", "B"])
        self.assertEqual(len(errors), 1)


class NamespaceFormsTest(unittest.TestCase):
    def test_the_statement_form_of_a_namespace_applies_to_the_statements_after_it(self):
        declarations, _occurrences, _errors = _analyse(
            "<?php\nnamespace A\\B;\nclass C extends \\D\\E {}\nuse F\\G as H;\nclass I extends H {}\n")
        self.assertEqual([(d.name, d.supertypes) for d in declarations],
                         [("A\\B\\C", ("D\\E",)), ("A\\B\\I", ("F\\G",))])


class OccurrencesTest(unittest.TestCase):
    def test_names_of_the_code_are_occurrences_while_comments_strings_and_keywords_are_not(self):
        source = ("<?php\n// Circle\n$s = 'Circle';\necho \\App\\Circle::class;\n"
                  "class_exists(Circle::class);\n$x = self::VALUE;\nfunction f(int $n): void {}\n")
        _declarations, occurrences, _errors = _analyse(source)
        names = [name for name, _line, _column in occurrences]
        self.assertEqual(names.count("Circle"), 2)
        for word in ("class", "self", "int", "void"):
            self.assertNotIn(word, names)
        self.assertEqual([(line, column) for name, line, column in occurrences if name == "Circle"],
                         [(4, 11), (5, 14)])


if __name__ == "__main__":
    unittest.main()
