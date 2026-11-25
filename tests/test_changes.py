"""The changes of an open file since its last save: the marks per line and the unified diff (no GUI)."""

import unittest

from ogmkdev import changes


class LineChangeTests(unittest.TestCase):
    def test_the_same_text_has_no_marks(self):
        self.assertEqual(changes.line_changes("a\nb\n", "a\nb\n"), [])
        self.assertEqual(changes.diff_text("a\nb\n", "a\nb\n"), "")

    def test_an_inserted_line_is_added(self):
        self.assertEqual(changes.line_changes("a\nc\n", "a\nb\nc\n"), [(2, changes.ADDED)])

    def test_a_replaced_line_is_changed(self):
        self.assertEqual(changes.line_changes("a\nb\nc\n", "a\nX\nc\n"), [(2, changes.CHANGED)])

    def test_a_removed_block_is_marked_on_the_line_that_follows_it(self):
        self.assertEqual(changes.line_changes("a\nb\nc\n", "a\nc\n"), [(2, changes.DELETED)])

    def test_a_removed_block_at_the_end_is_marked_on_the_last_line(self):
        self.assertEqual(changes.line_changes("a\nb\n", "a\n"), [(2, changes.DELETED)])

    def test_the_count_of_changed_lines_counts_each_line_once(self):
        self.assertEqual(changes.changed_lines("a\nb\nc\n", "a\nX\nY\nc\n"), 2)

    def test_the_diff_shows_the_removed_and_the_added_line(self):
        diff = changes.diff_text("one\ntwo\n", "one\nTWO\n", "saved", "buffer")
        self.assertIn("--- saved", diff)
        self.assertIn("+++ buffer", diff)
        self.assertIn("-two", diff)
        self.assertIn("+TWO", diff)


if __name__ == "__main__":
    unittest.main()
