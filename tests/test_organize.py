import unittest

from ogmkdev import organize as O

SOURCE = """<?php
namespace App\\Service;

use Zeta\\Lib;
use App\\Model\\Shape;
use Countable;
use App\\Model\\Unused as Old;
use function strlen;

final class Pricing implements Countable
{
    use Loggable;

    public function total(Shape $s): int { return strlen('x') + count([]); }
    public function count(): int { return 0; }
}
"""


class OrganizeTests(unittest.TestCase):
    def test_unused_imports_are_found(self):
        unused = [s.fqn for s in O.unused_imports(SOURCE)]
        self.assertEqual(unused, ["Zeta\\Lib", "App\\Model\\Unused"])

    def test_organize_sorts_removes_unused_and_keeps_functions(self):
        result = O.organize(SOURCE)
        self.assertIn("use App\\Model\\Shape;\nuse Countable;\nuse function strlen;\n", result)
        self.assertNotIn("Zeta", result)
        self.assertNotIn("Unused", result)
        self.assertIn("final class Pricing implements Countable", result)
        self.assertIn("    use Loggable;", result)  # trait use inside the class is not an import

    def test_organize_is_idempotent(self):
        once = O.organize(SOURCE)
        self.assertEqual(O.organize(once), once)

    def test_group_imports_leave_the_file_alone(self):
        source = "<?php\nuse App\\{A, B};\nclass C {}\n"
        self.assertIsNone(O.top_level_uses(source))
        self.assertEqual(O.organize(source), source)

    def test_code_between_two_groups_of_imports_stays(self):
        source = "<?php\nuse Zeta\\Lib;\nuse App\\Shape;\nclass Between {}\nuse Countable;\n" \
                 "function f(Shape $s, Countable $c) {}\n"
        self.assertEqual(O.organize(source), "<?php\nuse App\\Shape;\nclass Between {}\nuse Countable;\n"
                                             "function f(Shape $s, Countable $c) {}\n")

    def test_a_string_or_a_method_with_the_name_is_no_use_of_an_import(self):
        source = "<?php\nuse App\\Lib;\nclass C { public function Lib() {} public $x = 'Lib'; }\n"
        self.assertEqual([s.fqn for s in O.unused_imports(source)], ["App\\Lib"])

    def test_a_file_with_a_syntax_error_is_left_alone(self):
        source = "<?php\nuse App\\Shape;\nclass C { function f( {} }\n"
        self.assertEqual(O.unused_imports(source), [])
        self.assertEqual(O.organize(source), source)

    def test_no_imports_no_change(self):
        source = "<?php\nclass C {}\n"
        self.assertEqual(O.organize(source), source)


if __name__ == "__main__":
    unittest.main()
