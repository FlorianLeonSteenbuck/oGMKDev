"""The progress of a background task, as the frame shows it in the status bar.

The worker thread writes the progress, the GTK thread reads it on its poll. Each value is written in one assignment, so
the reader sees a complete value. A task that does not know its size yet has a total of 0; the bar then pulses.
"""

from __future__ import annotations


class Progress:
    """The label of the task, its steps done and its steps in all, and whether the task runs."""

    def __init__(self) -> None:
        self.label = ""
        self.done = 0
        self.total = 0
        self.running = False

    def start(self, label: str) -> None:
        self.label = label
        self.done = 0
        self.total = 0
        self.running = True

    def expect(self, total: int) -> None:
        """The task knows how many steps it has now; no step is done yet."""
        self.total = total
        self.done = 0

    def step(self) -> None:
        self.done += 1

    def finish(self) -> None:
        self.running = False
