"""XDebug backend: the DBGp protocol (https://xdebug.org/docs/dbgp).

The IDE listens on a TCP port; the PHP engine (XDebug) connects to it. Packets are framed
as ``<length>\\0<xml>\\0``. Commands are ``name -i <transaction> [args] [-- base64-data]\\0``
and every command gets exactly one ``<response>`` with the same transaction id.

Because DBGp is request/response, ``run`` and the step commands block until the engine
reports a break or the end of the script. Call them from a worker thread in a GUI.
"""

from __future__ import annotations

import base64
import itertools
import socket
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from .base import Breakpoint, Debugger, DebuggerError, Exited, Location, Output, Stopped

DEFAULT_PORT = 9003


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(root: ET.Element, name: str) -> Optional[ET.Element]:
    for element in root.iter():
        if _local(element.tag) == name:
            return element
    return None


def _decode_text(element: ET.Element) -> str:
    text = element.text or ""
    if element.get("encoding") == "base64":
        return base64.b64decode(text).decode("utf-8", errors="replace")
    return text


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class XdebugDebugger(Debugger):
    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 30.0) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.timeout = timeout
        self._server: Optional[socket.socket] = None
        self._conn: Optional[socket.socket] = None
        self._reader = None
        self._transactions = itertools.count(1)
        self._io_lock = threading.Lock()
        self._xdebug_ids: Dict[int, str] = {}
        self._last_action = "run"
        self._ended = False
        self.init_info: Dict[str, str] = {}

    # ---------------------------------------------------------- connection

    def listen(self) -> int:
        """Bind the listening socket; port 0 picks a free port. Returns the bound port."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen(1)
        self._server = server
        self.port = server.getsockname()[1]
        return self.port

    def start(self) -> None:
        """Wait for the engine to connect and read its ``<init>`` packet."""
        if self._server is None:
            self.listen()
        assert self._server is not None
        self._server.settimeout(self.timeout)
        try:
            conn, _ = self._server.accept()
        except socket.timeout as error:
            raise DebuggerError("no PHP/XDebug connection arrived") from error
        conn.settimeout(self.timeout)
        self._conn = conn
        self._reader = conn.makefile("rb")
        init = ET.fromstring(self._read_packet())
        self.init_info = {k: v for k, v in init.attrib.items()}

    def stop(self) -> None:
        if self._conn is None:
            self._close()
            return
        try:
            if not self._ended:
                self._call("stop")
        except (DebuggerError, OSError):
            pass
        self._close()

    def _close(self) -> None:
        for resource in (self._reader, self._conn, self._server):
            if resource is not None:
                try:
                    resource.close()
                except OSError:
                    pass
        self._reader = self._conn = self._server = None

    # ------------------------------------------------------------- protocol

    def _read_packet(self) -> bytes:
        assert self._reader is not None
        length_digits = bytearray()
        while True:
            ch = self._reader.read(1)
            if not ch:
                raise DebuggerError("the engine closed the connection")
            if ch == b"\0":
                break
            length_digits += ch
        length = int(length_digits.decode("ascii"))
        data = self._reader.read(length)
        if len(data) != length or self._reader.read(1) != b"\0":
            raise DebuggerError("malformed DBGp packet")
        return data

    def _call(self, command: str, args: str = "", data: Optional[str] = None) -> ET.Element:
        if self._conn is None:
            raise DebuggerError("no engine connected")
        with self._io_lock:
            transaction = next(self._transactions)
            line = f"{command} -i {transaction}"
            if args:
                line += f" {args}"
            if data is not None:
                line += f" -- {_b64(data)}"
            self._conn.sendall(line.encode("utf-8") + b"\0")
            while True:
                root = ET.fromstring(self._read_packet())
                tag = _local(root.tag)
                if tag == "stream":
                    self.emit(Output(_decode_text(root), stream="target"))
                    continue
                if tag == "response" and root.get("transaction_id") == str(transaction):
                    break
        error = _find(root, "error")
        if error is not None:
            message = _find(error, "message")
            raise DebuggerError(message.text if message is not None and message.text
                                else f"DBGp error {error.get('code')}")
        if root.get("status") in ("stopping", "stopped"):
            self._ended = True
        return root

    # --------------------------------------------------------- run control

    def _location(self, root: ET.Element) -> Optional[Location]:
        message = _find(root, "message")
        if message is None:
            return None
        uri = message.get("filename", "")
        path = unquote(urlparse(uri).path) if uri.startswith("file:") else uri
        line = message.get("lineno")
        return Location(file=path or None, line=int(line) if line else None)

    def _report(self, root: ET.Element) -> None:
        status = root.get("status")
        if status == "break":
            location = self._location(root)
            bp_id = None
            if location and location.file and location.line:
                for bp in self.breakpoints:
                    if Path(bp.file) == Path(location.file) and bp.line == location.line:
                        bp_id = bp.id
                        break
            if bp_id is not None:
                reason = "breakpoint"
            elif self._last_action != "run":
                reason = "step"
            else:
                reason = "pause"  # engine stopped without a breakpoint (debugger statement, start)
            self.emit(Stopped(reason, location, bp_id))
        elif status in ("stopping", "stopped"):
            self.emit(Exited(None))
            self._close()  # the engine is done; closing lets the PHP process exit

    def _resume(self, command: str) -> None:
        if self._ended:
            raise DebuggerError("the script has ended")
        self._last_action = command
        self._report(self._call(command))

    def run(self) -> None:
        self._resume("run")

    def step_over(self) -> None:
        self._resume("step_over")

    def step_into(self) -> None:
        self._resume("step_into")

    def step_out(self) -> None:
        self._resume("step_out")

    def evaluate(self, expression: str) -> str:
        root = self._call("eval", data=expression)
        prop = _find(root, "property")
        if prop is None:
            return ""
        return _decode_text(prop)

    def variables(self) -> List[Tuple[str, str]]:
        # context 0 is the local context of the current stack frame
        root = self._call("context_get", "-c 0")
        return [(child.get("name", ""), _decode_text(child))
                for child in root if _local(child.tag) == "property"]

    # ---------------------------------------------------------- breakpoints

    def _add_breakpoint(self, bp: Breakpoint) -> None:
        uri = Path(bp.file).resolve().as_uri()
        if bp.condition:
            root = self._call("breakpoint_set", f"-t conditional -f {uri} -n {bp.line}", data=bp.condition)
        else:
            root = self._call("breakpoint_set", f"-t line -f {uri} -n {bp.line}")
        xdebug_id = root.get("id")
        if not xdebug_id:
            raise DebuggerError("engine did not return a breakpoint id")
        self._xdebug_ids[bp.id] = xdebug_id

    def _remove_breakpoint(self, bp: Breakpoint) -> None:
        xdebug_id = self._xdebug_ids.pop(bp.id, None)
        if xdebug_id is not None:
            self._call("breakpoint_remove", f"-d {xdebug_id}")
