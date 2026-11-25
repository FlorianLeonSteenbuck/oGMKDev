"""GDB backend over the GDB/MI machine interface (``gdb --interpreter=mi3``).

Commands are sent with a numeric token and answered by a ``^`` result record with the same
token. Asynchronous records (``*stopped``, ``*running``), stream records (``~``, ``@``, ``&``)
and ``=`` notifications arrive on the same stream and are turned into debugger events.
"""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base import Breakpoint, Debugger, DebuggerError, Exited, Location, Output, Stopped

_RECORD = re.compile(r"^(\d*)([\^*+=~@&])(.*)$", re.DOTALL)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")
_OCTAL = frozenset("01234567")
_ESCAPES = {"n": 10, "t": 9, "r": 13, "a": 7, "b": 8, "f": 12, "v": 11, "\\": 92, '"': 34}
_REASONS = {
    "breakpoint-hit": "breakpoint",
    "end-stepping-range": "step",
    "function-finished": "step",
    "location-reached": "step",
    "signal-received": "signal",
}


class MiParseError(ValueError):
    pass


@dataclass
class MiRecord:
    kind: str                 # "result" | "exec" | "status" | "notify" | "stream" | "prompt"
    symbol: str = ""
    token: Optional[int] = None
    cls: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    text: str = ""


class _MiReader:
    """Recursive-descent reader for MI values (c-strings, tuples, lists)."""

    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0

    def eof(self) -> bool:
        return self.i >= len(self.s)

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            raise MiParseError(f"expected {ch!r} at {self.i} in {self.s!r}")
        self.i += 1

    def cstring(self) -> str:
        self.expect('"')
        out = bytearray()
        while True:
            if self.eof():
                raise MiParseError("unterminated c-string")
            c = self.s[self.i]
            self.i += 1
            if c == '"':
                return out.decode("utf-8", errors="replace")
            if c != "\\":
                out.extend(c.encode("utf-8"))
                continue
            if self.eof():
                raise MiParseError("dangling escape")
            e = self.s[self.i]
            self.i += 1
            if e in _OCTAL:
                digits = e
                while len(digits) < 3 and self.peek() in _OCTAL and self.peek() != "":
                    digits += self.peek()
                    self.i += 1
                out.append(int(digits, 8) & 0xFF)
            elif e in _ESCAPES:
                out.append(_ESCAPES[e])
            else:
                out.extend(e.encode("utf-8"))

    def value(self) -> Any:
        c = self.peek()
        if c == '"':
            return self.cstring()
        if c == "{":
            self.i += 1
            return self._results("}")
        if c == "[":
            self.i += 1
            return self._list()
        raise MiParseError(f"unexpected {c!r} at {self.i} in {self.s!r}")

    def _name(self) -> str:
        match = _NAME.match(self.s, self.i)
        if not match:
            raise MiParseError(f"expected a name at {self.i} in {self.s!r}")
        self.i = match.end()
        return match.group(0)

    def _results(self, closer: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        while not self.eof() and self.peek() != closer:
            name = self._name()
            self.expect("=")
            _add(out, name, self.value())
            if self.peek() == ",":
                self.i += 1
            elif self.peek() == closer or self.eof():
                break
            else:
                raise MiParseError(f"unexpected {self.peek()!r} at {self.i}")
        if closer and self.peek() == closer:
            self.i += 1
        return out

    def _list(self) -> List[Any]:
        items: List[Any] = []
        while self.peek() != "]":
            named = _NAME.match(self.s, self.i)
            if named and self.s[named.end():named.end() + 1] == "=":
                self.i = named.end() + 1       # `frame={...}` inside a list: keep the value
            items.append(self.value())
            if self.peek() == ",":
                self.i += 1
            elif self.peek() != "]":
                raise MiParseError(f"unexpected {self.peek()!r} in list")
        self.i += 1
        return items


def _add(target: Dict[str, Any], key: str, value: Any) -> None:
    if key not in target:
        target[key] = value
    elif isinstance(target[key], _Repeated):
        target[key].append(value)
    else:
        target[key] = _Repeated([target[key], value])


class _Repeated(list):
    """A key that appears more than once in a tuple; kept as a list."""


def parse_record(line: str) -> Optional[MiRecord]:
    if line.rstrip() == "(gdb)":
        return MiRecord(kind="prompt")
    match = _RECORD.match(line)
    if not match:
        return None
    token_text, symbol, rest = match.groups()
    token = int(token_text) if token_text else None
    if symbol in "~@&":
        return MiRecord(kind="stream", symbol=symbol, token=token,
                        text=_MiReader(rest).cstring() if rest.startswith('"') else rest)
    cls, _, tail = rest.partition(",")
    payload = _MiReader(tail)._results("") if tail else {}
    kind = {"^": "result", "*": "exec", "+": "status", "=": "notify"}[symbol]
    return MiRecord(kind=kind, symbol=symbol, token=token, cls=cls, payload=payload)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


class _Pending:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.cls = ""
        self.payload: Dict[str, Any] = {}


class GdbMiDebugger(Debugger):
    def __init__(self, program: str, args: Optional[List[str]] = None,
                 cwd: Optional[str] = None, gdb: str = "gdb", timeout: float = 20.0) -> None:
        super().__init__()
        self.program = os.path.abspath(program)
        self.args = list(args or [])
        self.cwd = cwd
        self.gdb = gdb
        self.timeout = timeout
        self._process: Optional[subprocess.Popen] = None
        self._tokens = itertools.count(1)
        self._send_lock = threading.Lock()
        self._pending: Dict[int, _Pending] = {}
        self._prompt_seen = threading.Event()
        self._gdb_number_for_bp: Dict[int, int] = {}
        self._bp_for_gdb_number: Dict[int, int] = {}
        self._started = False
        self._exited = False

    # ---------------------------------------------------------- lifecycle

    def start(self) -> None:
        argv = [self.gdb, "--interpreter=mi3", "--quiet", "--nx", "--args", self.program, *self.args]
        self._process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=self.cwd, text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        if not self._prompt_seen.wait(self.timeout):
            self.stop()
            raise DebuggerError("gdb did not reach its MI prompt")

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            try:
                self._command("-gdb-exit", timeout=5)
            except DebuggerError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()
        self._process = None

    # ------------------------------------------------------- run control

    def _resume(self, operation: str) -> None:
        if self._exited:
            raise DebuggerError("the program has exited")
        self._command(operation)

    def run(self) -> None:
        if not self._started:
            self._started = True
            self._resume("-exec-run")
        else:
            self._resume("-exec-continue")

    def step_over(self) -> None:
        self._resume("-exec-next")

    def step_into(self) -> None:
        self._resume("-exec-step")

    def step_out(self) -> None:
        self._resume("-exec-finish")

    def evaluate(self, expression: str) -> str:
        _, payload = self._command(f"-data-evaluate-expression {_quote(expression)}")
        return str(payload.get("value", ""))

    def variables(self) -> List[Tuple[str, str]]:
        _, payload = self._command("-stack-list-locals --simple-values")
        return [(str(item.get("name", "")), str(item.get("value", "")))
                for item in payload.get("locals", [])]

    # ------------------------------------------------------- breakpoints

    def _add_breakpoint(self, bp: Breakpoint) -> None:
        condition = f"-c {_quote(bp.condition)} " if bp.condition else ""
        location = _quote(f"{bp.file}:{bp.line}")
        _, payload = self._command(f"-break-insert -f {condition}{location}")
        number = int(payload["bkpt"]["number"])
        self._gdb_number_for_bp[bp.id] = number
        self._bp_for_gdb_number[number] = bp.id

    def _remove_breakpoint(self, bp: Breakpoint) -> None:
        number = self._gdb_number_for_bp.pop(bp.id, None)
        self._bp_for_gdb_number.pop(number, None)
        if number is not None:
            self._command(f"-break-delete {number}")

    # ---------------------------------------------------------- plumbing

    def _command(self, operation: str, timeout: Optional[float] = None) -> Tuple[str, Dict[str, Any]]:
        if self._process is None or self._process.poll() is not None:
            raise DebuggerError("gdb is not running")
        with self._send_lock:
            token = next(self._tokens)
            pending = _Pending()
            self._pending[token] = pending
            self._process.stdin.write(f"{token}{operation}\n")
            self._process.stdin.flush()
        if not pending.done.wait(timeout or self.timeout):
            self._pending.pop(token, None)
            raise DebuggerError(f"gdb did not answer {operation.split()[0]}")
        if pending.cls == "error":
            raise DebuggerError(str(pending.payload.get("msg", "gdb error")))
        return pending.cls, pending.payload

    def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for raw in self._process.stdout:
            line = raw.rstrip("\r\n")
            if line.rstrip() == "(gdb)":
                self._prompt_seen.set()
                continue
            try:
                record = parse_record(line)
            except (MiParseError, IndexError, ValueError):
                record = None
            if record is not None:
                self._handle(record)
            elif line:
                # Raw line: the debuggee writes straight to gdb's stdout, outside MI records.
                self.emit(Output(line, stream="target"))
        self._exited_by_process_end()

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for raw in self._process.stderr:
            self.emit(Output(raw.rstrip("\n"), stream="error"))

    def _handle(self, record: MiRecord) -> None:
        if record.kind == "result" and record.token is not None:
            pending = self._pending.pop(record.token, None)
            if pending is not None:
                pending.cls = record.cls
                pending.payload = record.payload
                pending.done.set()
        elif record.kind == "stream":
            stream = {"~": "console", "@": "target", "&": "error"}[record.symbol]
            if record.text:
                self.emit(Output(record.text, stream=stream))
        elif record.kind == "exec" and record.cls == "stopped":
            self._on_stopped(record.payload)
        elif record.kind == "notify" and record.cls == "thread-group-exited":
            code = record.payload.get("exit-code")
            self._mark_exited(int(code, 8) if code else None)

    def _on_stopped(self, payload: Dict[str, Any]) -> None:
        reason = str(payload.get("reason", ""))
        if reason.startswith("exited"):
            code = payload.get("exit-code")
            self._mark_exited(int(code, 8) if code else 0)
            return
        frame = payload.get("frame") or {}
        line = frame.get("line")
        location = Location(
            file=frame.get("fullname") or frame.get("file"),
            line=int(line) if line and line.isdigit() else None,
            function=frame.get("func"),
        )
        bp_id = None
        if "bkptno" in payload:
            bp_id = self._bp_for_gdb_number.get(int(payload["bkptno"]))
        self.emit(Stopped(_REASONS.get(reason, "unknown"), location, bp_id))

    def _mark_exited(self, code: Optional[int]) -> None:
        if self._exited:
            return
        self._exited = True
        self.emit(Exited(code))

    def _exited_by_process_end(self) -> None:
        for pending in list(self._pending.values()):
            pending.cls = "error"
            pending.payload = {"msg": "gdb terminated"}
            pending.done.set()
        self._pending.clear()
        self._mark_exited(None)
