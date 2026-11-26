import os
import tempfile
import threading
import time
import unittest

from ogmkdev import indexbuild as B
from ogmkdev.progress import Progress


class WatchedDirectoriesTest(unittest.TestCase):
    def test_the_roots_and_their_subfolders_without_the_excluded_ones(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "src", "deep"))
            os.makedirs(os.path.join(root, ".idea"))
            found = B.watched_directories([root], excluded=lambda path: os.path.basename(path) == ".idea")
            self.assertIn(root, found)
            self.assertIn(os.path.join(root, "src"), found)
            self.assertIn(os.path.join(root, "src", "deep"), found)
            self.assertNotIn(os.path.join(root, ".idea"), found)


class IndexBuilderTest(unittest.TestCase):
    def test_a_build_is_delivered_with_its_symbols_and_the_cache_is_saved(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as cache_dir:
            with open(os.path.join(root, "shop.py"), "w", encoding="utf-8") as handle:
                handle.write("class Shop:\n    pass\n")
            cache = os.path.join(cache_dir, "index.json")
            done = threading.Event()
            seen = {}

            def deliver(index, folders, error):
                seen.update(index=index, folders=folders, error=error)
                done.set()

            builder = B.IndexBuilder(deliver)
            builder.request([root], cache_path=cache)
            self.assertTrue(done.wait(20))
            self.assertIsNone(seen["error"])
            self.assertEqual(["Shop"], [symbol.name for symbol in seen["index"].symbols])
            self.assertIn(root, seen["folders"])
            self.assertTrue(os.path.isfile(cache))
            self.assertFalse(builder.busy)

    def test_a_failed_build_is_delivered_as_an_error(self):
        done = threading.Event()
        seen = {}

        def deliver(index, folders, error):
            seen.update(index=index, error=error)
            done.set()

        builder = B.IndexBuilder(deliver)
        builder.request([12345])
        self.assertTrue(done.wait(20))
        self.assertIsNone(seen["index"])
        self.assertTrue(seen["error"])
        self.assertFalse(builder.busy)

    def test_a_request_made_during_a_build_runs_after_it(self):
        with tempfile.TemporaryDirectory() as root:
            deliveries = []
            done = threading.Event()

            def deliver(index, folders, error):
                deliveries.append(index)
                if len(deliveries) == 2:
                    done.set()

            builder = B.IndexBuilder(deliver)
            builder.request([root])
            builder.request([root])
            self.assertTrue(done.wait(20))
            self.assertEqual(2, len(deliveries))


def wait_until_idle(builder, timeout=20.0):
    deadline = time.monotonic() + timeout
    while builder.busy and time.monotonic() < deadline:
        time.sleep(0.005)
    return not builder.busy


class IndexBuildCancelTest(unittest.TestCase):
    def test_a_cancelled_build_stops_between_two_files_and_delivers_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            for number in range(40):
                with open(os.path.join(root, f"module{number}.py"), "w", encoding="utf-8") as handle:
                    handle.write(f"class Module{number}:\n    pass\n")
            deliveries = []

            class CancelAfterThree(Progress):
                def step(self) -> None:
                    super().step()
                    if self.done == 3:
                        builder.cancel()  # from the build's own thread, as the Tools menu's request arrives later

            progress = CancelAfterThree()
            builder = B.IndexBuilder(lambda index, folders, error: deliveries.append(index), progress)
            builder.request([root])
            self.assertTrue(wait_until_idle(builder))  # the build cancels itself at its third file
            builder.shutdown()  # the build's thread has ended, so the delivery could not come later
            self.assertEqual(3, progress.done)
            self.assertEqual([], deliveries)
            self.assertFalse(builder.busy)

    def test_nothing_starts_after_shutdown(self):
        with tempfile.TemporaryDirectory() as root:
            deliveries = []
            builder = B.IndexBuilder(lambda index, folders, error: deliveries.append(index))
            builder.shutdown()
            builder.request([root])
            self.assertTrue(builder.closed)
            self.assertFalse(builder.busy)
            self.assertEqual([], deliveries)


if __name__ == "__main__":
    unittest.main()
