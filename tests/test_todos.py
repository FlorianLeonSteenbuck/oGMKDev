"""TODO words as editor hints (todos.todo_marks): the span of the keyword in its line, the message from the keyword on,
and only the words inside comments."""

import unittest

from ogmkdev import todos


class TodoMarksTest(unittest.TestCase):
    def keywords(self):
        return todos.parse_keywords(todos.DEFAULT_KEYWORDS)

    def test_a_keyword_in_a_comment_is_marked_with_its_columns_and_message(self):
        text = "x = 1\n# TODO: split this\ny = 2  # FIXME: later\n"
        marks = todos.todo_marks("sample.py", text, self.keywords())
        self.assertEqual([(2, 3, 7, "todo", "TODO: split this"), (3, 10, 15, "todo", "FIXME: later")], marks)

    def test_a_keyword_in_a_string_is_not_marked(self):
        text = "label = 'TODO: not a comment'\n"
        self.assertEqual([], todos.todo_marks("sample.py", text, self.keywords()))

    def test_a_file_of_an_unknown_language_has_no_marks(self):
        self.assertEqual([], todos.todo_marks("notes.zzz", "# TODO: x\n", self.keywords()))

    def test_no_keywords_mean_no_marks(self):
        self.assertEqual([], todos.todo_marks("sample.py", "# TODO: x\n", []))


if __name__ == "__main__":
    unittest.main()
