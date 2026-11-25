import unittest

from ogmkdev.debug.base import Breakpoint, Debugger, DebuggerError
from ogmkdev.debug.sync import BreakpointSync


class FakeDebugger(Debugger):
    """Records the breakpoints it is given; a file named 'bad' cannot take breakpoints."""

    def __init__(self):
        super().__init__()
        self.added = []
        self.removed = []

    def start(self):
        pass

    def run(self):
        pass

    def step_over(self):
        pass

    def step_into(self):
        pass

    def step_out(self):
        pass

    def stop(self):
        pass

    def evaluate(self, expression):
        return expression

    def _add_breakpoint(self, bp: Breakpoint) -> None:
        if bp.file == "bad":
            raise DebuggerError("no code at this line")
        self.added.append((bp.file, bp.line))

    def _remove_breakpoint(self, bp: Breakpoint) -> None:
        self.removed.append((bp.file, bp.line))


class BreakpointSyncTest(unittest.TestCase):
    def test_new_locations_are_added_once(self):
        debugger = FakeDebugger()
        sync = BreakpointSync(debugger)
        self.assertEqual([], sync.sync([("a.py", 3), ("a.py", 9)]))
        self.assertEqual([("a.py", 3), ("a.py", 9)], debugger.added)
        sync.sync([("a.py", 3), ("a.py", 9)])
        self.assertEqual([("a.py", 3), ("a.py", 9)], debugger.added)
        self.assertEqual([], debugger.removed)

    def test_locations_that_are_gone_are_removed(self):
        debugger = FakeDebugger()
        sync = BreakpointSync(debugger)
        sync.sync([("a.py", 3), ("a.py", 9)])
        sync.sync([("a.py", 9), ("b.py", 1)])
        self.assertEqual([("a.py", 3)], debugger.removed)
        self.assertEqual([("a.py", 3), ("a.py", 9), ("b.py", 1)], debugger.added)
        self.assertEqual(set(sync.ids), {("a.py", 9), ("b.py", 1)})

    def test_a_location_the_engine_refuses_is_reported_and_the_others_are_set(self):
        debugger = FakeDebugger()
        sync = BreakpointSync(debugger)
        problems = sync.sync([("bad", 2), ("a.py", 4)])
        self.assertEqual(["bad:2: no code at this line"], problems)
        self.assertEqual([("a.py", 4)], debugger.added)
        self.assertNotIn(("bad", 2), sync.ids)


if __name__ == "__main__":
    unittest.main()
