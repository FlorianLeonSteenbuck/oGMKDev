"""The paths a PHP file builds from its own folder (__DIR__ . "/x" and dirname(__FILE__) . '/x'): a click inside a string
of the chain gives the path, a click elsewhere gives nothing. Without GTK."""

import unittest

from ogmkdev.php_paths import path_at

LINE = '<?php echo file_get_contents(__DIR__ . "/style.css"); ?>'


class PhpPathTests(unittest.TestCase):
    def test_a_click_on_the_string_gives_the_file_next_to_the_php_file(self):
        column = LINE.index('"/style.css"') + 3  # inside the literal
        self.assertEqual(path_at(LINE, column, "/work/site"), "/work/site/style.css")

    def test_a_click_outside_the_string_gives_nothing(self):
        self.assertIsNone(path_at(LINE, LINE.index("__DIR__") + 1, "/work/site"))
        self.assertIsNone(path_at(LINE, 1, "/work/site"))

    def test_dirname_of_the_file_and_relative_parts_are_normalized(self):
        line = "require dirname(__FILE__) . '/../shared/x.css';"
        self.assertEqual(path_at(line, line.index("'/../") + 3, "/work/site"), "/work/shared/x.css")

    def test_a_chain_of_strings_is_one_path_and_a_click_in_any_part_finds_it(self):
        line = 'echo __DIR__ . "/css" . "/main.css";'
        self.assertEqual(path_at(line, line.index('"/main') + 2, "/work/site"), "/work/site/css/main.css")
        self.assertEqual(path_at(line, line.index('"/css') + 2, "/work/site"), "/work/site/css/main.css")

    def test_a_plain_string_without_the_folder_is_not_a_path_of_the_file(self):
        line = 'echo "/style.css";'
        self.assertIsNone(path_at(line, 8, "/work/site"))


if __name__ == "__main__":
    unittest.main()
