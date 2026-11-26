"""The warnings of the program itself. Python warns about the invalid escape sequences of the sources it parses (the
index reads the user's Python files with ast); importing the package turns that warning off."""

import ast
import unittest
import warnings

import ogmkdev  # noqa: F401 - importing the package sets the filter


class InvalidEscapeTests(unittest.TestCase):
    def test_an_invalid_escape_in_a_parsed_source_is_no_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            ast.parse("pattern = '\\d+'\n")
        self.assertEqual([str(warning.message) for warning in caught], [])


if __name__ == "__main__":
    unittest.main()
