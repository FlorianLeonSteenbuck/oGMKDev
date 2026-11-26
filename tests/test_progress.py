"""The progress of the background index: the files it reads are counted, and the builder runs the task as 'Index' and
ends it before it delivers the index."""

import os
import tempfile
import threading
import unittest

from ogmkdev import index as index_module
from ogmkdev.indexbuild import IndexBuilder
from ogmkdev.progress import Progress


def _write_python(root, name):
    with open(os.path.join(root, name), "w", encoding="utf-8") as handle:
        handle.write("def f():\n    return 1\n")


class ProgressTests(unittest.TestCase):
    def test_a_task_counts_its_steps_and_finishes(self):
        progress = Progress()
        progress.start("Index")
        progress.expect(3)
        progress.step()
        progress.step()
        self.assertTrue(progress.running)
        self.assertEqual((progress.label, progress.done, progress.total), ("Index", 2, 3))
        progress.finish()
        self.assertFalse(progress.running)


class IndexProgressTests(unittest.TestCase):
    def test_the_index_counts_the_files_it_reads(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("a.py", "b.py", "c.py"):
                _write_python(root, name)
            progress = Progress()
            index_module.ProjectIndex([root], progress=progress)
            self.assertEqual((progress.done, progress.total), (3, 3))


class BuilderProgressTests(unittest.TestCase):
    def test_the_builder_runs_the_index_task_and_ends_it_before_it_delivers(self):
        with tempfile.TemporaryDirectory() as root:
            _write_python(root, "a.py")
            delivered = threading.Event()
            running_at_delivery = []

            def deliver(index, folders, error):
                running_at_delivery.append(builder.progress.running)
                delivered.set()

            builder = IndexBuilder(deliver)
            builder.request([root])
            self.assertTrue(delivered.wait(60))
            self.assertEqual(running_at_delivery, [False])
            self.assertEqual(builder.progress.label, "Index")


if __name__ == "__main__":
    unittest.main()
