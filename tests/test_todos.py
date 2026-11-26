"""TODO words as editor hints (todos.todo_marks): the span of the keyword in its line, the message from the keyword on,
and only the words inside comments."""

import os
import tempfile
import unittest
from unittest import mock

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


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class TodoCacheTest(unittest.TestCase):
    def test_only_the_changed_files_are_read_again(self):
        keywords = todos.parse_keywords(todos.DEFAULT_KEYWORDS)
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "a.py")
            second = os.path.join(folder, "b.py")
            write(first, "# TODO: one\n")
            write(second, "# FIXME: two\n")
            cache = todos.TodoCache()
            with mock.patch.object(todos, "todos_in_file", wraps=todos.todos_in_file) as reads:
                self.assertEqual(2, len(cache.collect([first, second], keywords)))
                self.assertEqual(2, reads.call_count)
                self.assertEqual(2, len(cache.collect([first, second], keywords)))
                self.assertEqual(2, reads.call_count, "nothing changed: nothing is read again")
                write(first, "# TODO: one and more\n# TODO: three\n")
                found = cache.collect([first, second], keywords)
                self.assertEqual(3, len(found))
                self.assertEqual(3, reads.call_count, "only the changed file is read again")

    def test_a_file_that_left_the_workspace_leaves_the_list(self):
        keywords = todos.parse_keywords(todos.DEFAULT_KEYWORDS)
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "a.py")
            second = os.path.join(folder, "b.py")
            write(first, "# TODO: one\n")
            write(second, "# TODO: two\n")
            cache = todos.TodoCache()
            self.assertEqual(2, len(cache.collect([first, second], keywords)))
            self.assertEqual(1, len(cache.collect([second], keywords)))


if __name__ == "__main__":
    unittest.main()
