"""The resources of the IDE and of a running program: their memory and threads, read from /proc (Linux), and the size of the
index. The Resources tab of the frame shows the lines :func:`resource_lines` makes. Failures are return values (see
ogmkdev.outcome); nothing here raises for a process that has ended."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

from .outcome import Failure, failed

KIB = 1024
UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


@dataclass(frozen=True)
class ProcessResources:
    pid: int
    name: str                   # the name of the program
    resident_bytes: int         # the memory the process holds in RAM (VmRSS)
    virtual_bytes: int          # the address space the process has reserved (VmSize)
    threads: Tuple[str, ...]    # one name per thread, as the operating system names it


@dataclass(frozen=True)
class IndexSize:
    files: int
    symbols: int
    references: int
    cache_bytes: int            # the index cache on disk; 0 when there is none


def format_bytes(count: int) -> str:
    """A byte count with the largest unit it reaches, one decimal place from KiB on: "12.4 MiB"."""
    value = float(count)
    for unit in UNITS:
        if value < KIB or unit == UNITS[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= KIB
    return f"{count} B"  # not reached: the last unit takes every count


def _status(pid: int) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    with open(f"/proc/{pid}/status", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            key, _separator, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def _kib(value: Optional[str]) -> int:
    """The bytes of a /proc value such as "12345 kB"; 0 when the value is missing."""
    return int(value.split()[0]) * KIB if value else 0


def process_resources(pid: int) -> Union[ProcessResources, Failure]:
    """The memory and the threads of a process. A process that has ended, or a system without /proc, gives the reason."""
    try:
        fields = _status(pid)
        names: List[str] = []
        for task in sorted(os.listdir(f"/proc/{pid}/task"), key=int):
            try:
                with open(f"/proc/{pid}/task/{task}/comm", encoding="utf-8", errors="replace") as handle:
                    names.append(handle.read().strip())
            except OSError:
                continue  # the thread has ended since the list was read
    except (OSError, ValueError) as problem:
        return failed(f"process {pid}: {problem}")
    return ProcessResources(pid, fields.get("Name", ""), _kib(fields.get("VmRSS")), _kib(fields.get("VmSize")),
                            tuple(names))


def python_threads() -> List[str]:
    """The names of the Python threads of this process, the main thread included: the work the IDE runs in the background
    (the index builder) is among them."""
    return [thread.name for thread in threading.enumerate()]


def index_size(index, cache_path: Optional[str]) -> IndexSize:
    """How much the index holds: its files, symbols and references, and the size of its cache file on disk."""
    files = index.files
    cache = os.path.getsize(cache_path) if cache_path and os.path.isfile(cache_path) else 0
    return IndexSize(files=len(files),
                     symbols=sum(len(entry.symbols) for entry in files.values()),
                     references=sum(len(entry.references) for entry in files.values()),
                     cache_bytes=cache)


def resource_lines(own: Union[ProcessResources, Failure], python: List[str], program: Optional[ProcessResources],
                   index: Optional[IndexSize]) -> List[str]:
    """The text of the Resources tab: the IDE, the running program (or that none runs), and the index."""
    lines: List[str] = []
    if isinstance(own, Failure):
        lines.append(f"oGMKDev: {own}")
    else:
        lines.append(f"oGMKDev (process {own.pid}, {own.name})")
        lines.append(f"  memory in RAM {format_bytes(own.resident_bytes)}, reserved {format_bytes(own.virtual_bytes)}")
        lines.append(f"  threads: {len(own.threads)} from the operating system, {len(python)} of them Python threads")
        lines.append("  thread names: " + ", ".join(sorted(set(own.threads))))
        lines.append("  Python threads: " + ", ".join(python))
    lines.append("")
    if program is None:
        lines.append("Running program: none")
    else:
        lines.append(f"Running program (process {program.pid}, {program.name})")
        lines.append(f"  memory in RAM {format_bytes(program.resident_bytes)}, reserved {format_bytes(program.virtual_bytes)}")
        lines.append(f"  threads: {len(program.threads)}: " + ", ".join(program.threads))
    lines.append("")
    if index is None:
        lines.append("Index: not built yet")
    else:
        lines.append(f"Index: {index.files} files, {index.symbols} symbols, {index.references} references, "
                     f"cache {format_bytes(index.cache_bytes)}")
    return lines
