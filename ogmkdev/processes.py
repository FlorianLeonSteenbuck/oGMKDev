"""The processes of a process group, read from /proc (Linux): the members that still run, and their end.

A background service started from the Run tab runs in a process group of its own: its shell, and everything the shell
started, also what goes on after the shell has ended. Stopping the service means ending the group. A zombie has ended
and waits only to be reaped, so it does not count as running. Without /proc nothing can be told apart, and no member
is reported.
"""

from __future__ import annotations

import os
import signal
import time
from typing import List


def group_members(pgid: int) -> List[int]:
    """The processes of the group ``pgid`` that still run (zombies left out)."""
    members: List[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return members
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue  # the process has ended while the list was read
        # the command name sits in parentheses and may hold spaces: the fields come after the last closing parenthesis
        fields = text[text.rfind(")") + 2:].split()
        if len(fields) > 2 and int(fields[2]) == pgid and fields[0] != "Z":
            members.append(int(entry))
    return members


def terminate_group(pgid: int, wait: float = 2.0) -> bool:
    """Ends the processes of the group: SIGTERM to the group, then SIGKILL to those still running after ``wait`` seconds.
    Returns True when no process of the group runs any more."""
    if not group_members(pgid):
        return True
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + wait
    while group_members(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)
    for pid in group_members(pgid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 0.5
    while group_members(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)
    return not group_members(pgid)
