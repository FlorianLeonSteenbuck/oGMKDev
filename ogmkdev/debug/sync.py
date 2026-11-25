"""The breakpoints of a debug session follow the breakpoints the editors show (see ogmkdev.frame.debugging).

``BreakpointSync`` keeps the engine's breakpoints equal to a set of (path, line) locations: a location that is
new is added, one that is gone is removed, and one that is there already is left alone, so syncing before every
resume costs nothing when nothing changed.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .base import Debugger, DebuggerError

Location = Tuple[str, int]


class BreakpointSync:
    def __init__(self, debugger: Debugger) -> None:
        self.debugger = debugger
        self.ids: Dict[Location, int] = {}

    def sync(self, wanted: Iterable[Location]) -> List[str]:
        """Makes the engine's breakpoints the wanted locations. Returns the problems the engine reported (one
        location it cannot take does not stop the others)."""
        wanted_set = set(wanted)
        problems: List[str] = []
        for location in [known for known in self.ids if known not in wanted_set]:
            try:
                self.debugger.remove_breakpoint(self.ids.pop(location))
            except DebuggerError as error:
                problems.append(f"{location[0]}:{location[1]}: {error}")
        for location in sorted(wanted_set - set(self.ids)):
            try:
                self.ids[location] = self.debugger.add_breakpoint(location[0], location[1]).id
            except DebuggerError as error:
                problems.append(f"{location[0]}:{location[1]}: {error}")
        return problems
