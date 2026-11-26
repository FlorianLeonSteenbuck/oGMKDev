"""The resources of the IDE and of a running program, read from /proc, and the size of the index. Without GTK."""

import os
import tempfile
import threading
import unittest

from ogmkdev import index as index_module
from ogmkdev import resources
from ogmkdev.outcome import Failure


class ResourceTests(unittest.TestCase):
    def test_the_own_process_has_memory_and_threads(self):
        own = resources.process_resources(os.getpid())
        self.assertNotIsInstance(own, Failure)
        self.assertGreater(own.resident_bytes, 0)
        self.assertGreaterEqual(own.virtual_bytes, own.resident_bytes)
        self.assertGreaterEqual(len(own.threads), 1)

    def test_a_started_thread_is_counted_among_the_threads(self):
        before = len(resources.process_resources(os.getpid()).threads)
        stop = threading.Event()
        thread = threading.Thread(target=stop.wait, daemon=True)
        thread.start()
        try:
            after = len(resources.process_resources(os.getpid()).threads)
            self.assertGreater(after, before)
            self.assertIn("MainThread", resources.python_threads())
        finally:
            stop.set()
            thread.join()

    def test_a_process_that_does_not_exist_is_a_failure(self):
        self.assertIsInstance(resources.process_resources(2 ** 22 + 7), Failure)

    def test_bytes_are_written_with_the_largest_unit_they_reach(self):
        self.assertEqual(resources.format_bytes(512), "512 B")
        self.assertEqual(resources.format_bytes(1536), "1.5 KiB")
        self.assertEqual(resources.format_bytes(12 * 1024 * 1024), "12.0 MiB")

    def test_the_index_size_counts_its_files_symbols_and_references_and_the_cache(self):
        with tempfile.TemporaryDirectory() as project:
            with open(os.path.join(project, "main.py"), "w", encoding="utf-8") as handle:
                handle.write("class Main:\n    def run(self):\n        return helper()\n\n\ndef helper():\n    return 1\n")
            index = index_module.ProjectIndex([project])
            size = resources.index_size(index, None)
            self.assertEqual(size.files, 1)
            self.assertGreater(size.symbols, 0)
            self.assertGreater(size.references, 0)
            self.assertEqual(size.cache_bytes, 0)
            cache = os.path.join(project, "cache.json")
            index.save_cache(cache)
            self.assertGreater(resources.index_size(index, cache).cache_bytes, 0)

    def test_the_lines_name_the_program_and_say_when_none_runs(self):
        own = resources.process_resources(os.getpid())
        size = resources.IndexSize(files=2, symbols=5, references=9, cache_bytes=2048)
        lines = resources.resource_lines(own, ["MainThread"], None, size)
        text = "\n".join(lines)
        self.assertIn(f"oGMKDev (process {os.getpid()}", text)
        self.assertIn("Running program: none", text)
        self.assertIn("Index: 2 files, 5 symbols, 9 references, cache 2.0 KiB", text)

    def test_a_running_program_is_named_with_its_pid(self):
        own = resources.process_resources(os.getpid())
        program = resources.process_resources(os.getpid())  # any live process will do for the line
        lines = resources.resource_lines(own, [], program, None)
        self.assertIn(f"Running program (process {os.getpid()}", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
