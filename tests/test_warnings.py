"""The warnings of the program itself. Python warns about the invalid escape sequences of the sources it parses (the
index reads the user's Python files with ast); importing the package turns that warning off."""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class InvalidEscapeTests(unittest.TestCase):
    def test_an_invalid_escape_in_a_parsed_source_is_no_warning(self):
        # A separate process: the unittest runner sets its own 'default' warnings filter in front of the package's
        # filter, which would show the warning whatever the package does. The program runs without that runner.
        code = "import ogmkdev, ast\nast.parse(\"pattern = '\\\\d+'\\n\")\n"
        completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")


if __name__ == "__main__":
    unittest.main()
