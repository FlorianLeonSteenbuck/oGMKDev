"""The base of the background services (ogmkdev/service.py), without GTK: a job runs in a thread of its own, the latest
request waits for the running job, cancel and shutdown end the work, and a cancelled job publishes nothing."""

import threading
import time
import unittest

from ogmkdev.service import Cancelled, Service


def wait_for(condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.005)
    return condition()


class GatedService(Service):
    """A service whose job waits at ``gate``, so the test decides when it ends. The job returns its argument."""

    label = "Test"

    def __init__(self, deliver=None):
        self.gate = threading.Event()
        self.runs = []
        self.threads = []
        self.published = []
        super().__init__(deliver or (lambda result, error: self.published.append((result, error))))

    def run(self, cancel, value):
        self.runs.append(value)
        self.threads.append(threading.current_thread())
        while not self.gate.wait(0.005):
            if cancel.is_set():
                raise Cancelled("cancelled")
        if value == "fail":
            raise ValueError("boom")
        return value


class ServiceTest(unittest.TestCase):
    def test_a_job_runs_in_a_thread_of_its_own_and_is_published_when_the_service_is_free(self):
        seen = []
        service = GatedService(lambda result, error: seen.append((service.busy, result, error)))
        service.gate.set()
        service.request("a")
        self.assertTrue(wait_for(lambda: seen))
        self.assertEqual([(False, "a", None)], seen)
        self.assertIsNot(threading.current_thread(), service.threads[0])
        service.shutdown()

    def test_a_request_made_while_a_job_runs_waits_and_only_the_latest_one_is_kept(self):
        service = GatedService()
        service.request(1)
        self.assertTrue(wait_for(lambda: service.runs))
        service.request(2)
        service.request(3)
        service.gate.set()
        self.assertTrue(wait_for(lambda: len(service.published) == 2))
        self.assertEqual([(1, None), (3, None)], service.published)
        service.shutdown()

    def test_a_request_made_while_a_result_is_published_starts_a_job_and_the_older_waiting_one_is_dropped(self):
        published = []
        service = None

        def deliver(result, error):
            published.append(result)
            if result == 1:
                service.request(3)  # the service is free now, so this request starts a job of its own

        service = GatedService(deliver)
        service.request(1)
        self.assertTrue(wait_for(lambda: service.runs))
        service.request(2)  # waits behind job 1; request 3 is newer and replaces it
        service.gate.set()
        self.assertTrue(wait_for(lambda: len(published) == 2))
        self.assertEqual([1, 3], published)
        service.shutdown()

    def test_an_error_of_the_job_is_published_with_its_message(self):
        service = GatedService()
        service.gate.set()
        service.request("fail")
        self.assertTrue(wait_for(lambda: service.published))
        self.assertEqual([(None, "boom")], service.published)
        service.shutdown()

    def test_cancel_ends_the_running_job_publishes_nothing_and_drops_the_waiting_request(self):
        service = GatedService()
        service.request(1)
        self.assertTrue(wait_for(lambda: service.runs))
        service.request(2)
        service.cancel()
        self.assertTrue(wait_for(lambda: not service.busy))
        service.shutdown()
        self.assertEqual([1], service.runs)
        self.assertEqual([], service.published)

    def test_a_request_made_after_a_cancel_runs(self):
        service = GatedService()
        service.request(1)
        self.assertTrue(wait_for(lambda: service.runs))
        service.cancel()
        self.assertTrue(wait_for(lambda: not service.busy))
        service.gate.set()
        service.request(2)
        self.assertTrue(wait_for(lambda: service.published))
        self.assertEqual([(2, None)], service.published)
        service.shutdown()

    def test_shutdown_ends_the_running_job_and_no_job_starts_afterwards(self):
        service = GatedService()
        service.request(1)
        self.assertTrue(wait_for(lambda: service.runs))
        service.shutdown(timeout=5)
        self.assertFalse(service.busy)
        self.assertTrue(service.closed)
        service.gate.set()
        service.request(2)
        self.assertFalse(service.busy)
        self.assertEqual([1], service.runs)
        self.assertEqual([], service.published)


if __name__ == "__main__":
    unittest.main()
