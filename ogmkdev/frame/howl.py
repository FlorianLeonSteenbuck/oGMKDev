"""Howl's editor as GTK 4 widgets: loads libhowl.so and hands it containers of the frame."""

from __future__ import annotations

import ctypes
import os
from typing import List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# A package installs the library and Howl's Lua files elsewhere: the starter sets these variables
HOWL_ROOT = os.environ.get("OGMKDEV_HOWL_ROOT") or os.path.join(ROOT, "howl")
LIBRARY = os.environ.get("OGMKDEV_HOWL_LIBRARY") or os.path.join(HOWL_ROOT, "src", "libhowl.so")

_pythonapi = ctypes.pythonapi
_pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
_pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]


def raw_pointer(gobject) -> int:
    """The C address of a PyGObject object (the __gpointer__ capsule)."""
    return _pythonapi.PyCapsule_GetPointer(gobject.__gpointer__, None)


class Editors:
    """The Howl library of this process. One Lua state: every editor belongs to it."""

    def __init__(self, library: str = LIBRARY, root: str = HOWL_ROOT) -> None:
        # RTLD_GLOBAL: the symbols of libhowl.so must be visible to LuaJIT's ffi.C lookups
        self._lib = ctypes.CDLL(library, mode=ctypes.RTLD_GLOBAL)
        self._lib.howl_embed.restype = ctypes.c_int
        self._lib.howl_embed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        self._lib.howl_open.restype = ctypes.c_int
        self._lib.howl_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        self._lib.howl_command.restype = ctypes.c_int
        self._lib.howl_command.argtypes = [ctypes.c_char_p]
        self._lib.howl_theme.restype = ctypes.c_int
        self._lib.howl_theme.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.howl_status.restype = ctypes.c_int
        self._lib.howl_status.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self._lib.howl_files.restype = ctypes.c_int
        self._lib.howl_files.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self._lib.howl_insert.restype = ctypes.c_int
        self._lib.howl_insert.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p]
        self._lib.howl_inspect.restype = ctypes.c_int
        self._lib.howl_inspect.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.howl_take_click.restype = ctypes.c_int
        self._lib.howl_take_click.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self._lib.howl_edge.restype = ctypes.c_int
        self._lib.howl_edge.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self._lib.howl_templates.restype = ctypes.c_int
        self._lib.howl_templates.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.howl_changes.restype = ctypes.c_int
        self._lib.howl_changes.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.howl_options.restype = ctypes.c_int
        self._lib.howl_options.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        self._lib.howl_text.restype = ctypes.c_int
        self._lib.howl_text.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        self._lib.howl_breakpoints.restype = ctypes.c_int
        self._lib.howl_breakpoints.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self._lib.howl_close.restype = ctypes.c_int
        self._lib.howl_close.argtypes = [ctypes.c_void_p]
        self._lib.howl_focus.restype = ctypes.c_int
        self._lib.howl_focus.argtypes = [ctypes.c_void_p]
        self._root = root.encode()
        self.count = 0

    def add(self, container, path: Optional[str] = None) -> bool:
        """Puts a new Howl editor (with ``path`` if given) into ``container`` (a Gtk.Box)."""
        file = os.path.abspath(path).encode() if path else None
        status = self._lib.howl_embed(raw_pointer(container), self._root, file)
        if status == 0:
            self.count += 1
        return status == 0

    def open(self, path: str, line: int = 0, column: int = 0) -> bool:
        """Opens ``path`` in the Howl editor that has the focus (line and column 1-based, 0 for none)."""
        return self._lib.howl_open(os.path.abspath(path).encode(), line, column) == 0

    def command(self, name: str) -> bool:
        """Runs a Howl command ("save", "editor-undo", ...) in the editor that has the focus."""
        return self._lib.howl_command(name.encode()) == 0

    def status(self) -> Optional[dict]:
        """The focused Howl editor: path, line, column, mode and whether it is modified (None if none)."""
        buffer = ctypes.create_string_buffer(4096)
        if self._lib.howl_status(buffer, len(buffer)) != 0:
            return None
        fields = buffer.value.decode("utf-8", "replace").split("\t")
        if len(fields) != 4 or not fields[0]:
            return None
        line, _, column = fields[1].partition(":")
        return {
            "path": fields[0],
            "line": int(line) if line.isdigit() else 1,
            "column": int(column) if column.isdigit() else 1,
            "mode": fields[2],
            "modified": fields[3] == "modified",
        }

    def changes(self, path: str, rows) -> bool:
        """The change marks of ``path`` in its Howl buffers: rows of (line, kind), kind added, changed or
        deleted. An empty list removes them."""
        lines = [f"{line}\t{kind}" for line, kind in rows]
        return self._lib.howl_changes(os.path.abspath(path).encode(), "\n".join(lines).encode("utf-8")) == 0

    def options(self, path: str, syntax: Optional[bool] = None,
                current_line: Optional[bool] = None) -> Optional[Tuple[bool, bool]]:
        """Sets the display options of the editors that show ``path``: the syntax colours and the highlight of the
        current line; an option that is None stays as it is. Returns the state of the first editor that shows the
        file as (syntax colours shown, current line highlighted), or None when no editor shows it."""
        state = self._lib.howl_options(os.path.abspath(path).encode(),
                                       -1 if syntax is None else int(syntax),
                                       -1 if current_line is None else int(current_line))
        return None if state < 0 else (bool(state & 1), bool(state & 2))

    TEXT_LIMIT = 4 * 1024 * 1024

    def text(self, path: str) -> Optional[str]:
        """The text of the Howl buffer of ``path``; None when no editor shows it or the text is too large."""
        buffer = ctypes.create_string_buffer(self.TEXT_LIMIT)
        if self._lib.howl_text(os.path.abspath(path).encode(), buffer, self.TEXT_LIMIT) != 0:
            return None
        if len(buffer.value) >= self.TEXT_LIMIT - 1:
            return None  # truncated by the buffer
        return buffer.value.decode("utf-8", "replace")

    def hints(self, path: str, rows) -> bool:
        """Error hints of ``path`` in its Howl buffer: rows of (line, start, end, kind, message), columns
        1-based and end exclusive, kind error, warning or hint. An empty list removes them."""
        lines = [f"{line}\t{start}\t{end}\t{kind}\t{' '.join(message.split())}"
                 for line, start, end, kind, message in rows]
        return self._lib.howl_inspect(os.path.abspath(path).encode(), "\n".join(lines).encode("utf-8")) == 0

    def templates(self, path: str, rows: str) -> bool:
        """The code templates of ``path`` for Ctrl+Space in its Howl editors: one row per template,
        "trigger<TAB>body" with the body escaped (see templates.howl_rows)."""
        return self._lib.howl_templates(os.path.abspath(path).encode(), rows.encode("utf-8")) == 0

    def breakpoints(self) -> List[Tuple[str, int]]:
        """The breakpoints the Howl editors show: (path, line) pairs, lines 1-based, each once."""
        buffer = ctypes.create_string_buffer(65536)
        if self._lib.howl_breakpoints(buffer, len(buffer)) != 0:
            return []
        found: List[Tuple[str, int]] = []
        for row in buffer.value.decode("utf-8", "replace").split("\n"):
            path, _, line = row.partition("\t")
            if path and line.isdigit() and (path, int(line)) not in found:
                found.append((path, int(line)))
        return found

    def close(self, container) -> bool:
        """Releases the Howl editor shown in ``container`` (a Gtk.Box); call it before the container is removed."""
        return self._lib.howl_close(raw_pointer(container)) == 0

    def focus(self, container) -> bool:
        """Gives the keyboard focus to the Howl editor shown in ``container``; Howl then follows that editor."""
        return self._lib.howl_focus(raw_pointer(container)) == 0

    def take_click(self):
        """The last Ctrl+click in a Howl editor, taken once: (word, column, line text), or None."""
        buffer = ctypes.create_string_buffer(8192)
        if self._lib.howl_take_click(buffer, len(buffer)) != 0:
            return None
        text = buffer.value.decode("utf-8", "replace")
        word, _, rest = text.partition("\t")
        column, _, line = rest.partition("\t")
        if not word:
            return None
        return word, int(column) if column.isdigit() else 0, line

    def set_edge(self, path: str, column: int) -> bool:
        """The edge line at ``column`` in the editors that show ``path`` (0 for none)."""
        return self._lib.howl_edge(os.path.abspath(path).encode(), column) == 0

    def insert_before(self, path: str, line: int, text: str) -> bool:
        """Inserts whole lines in front of a 1-based line of the editor showing ``path``."""
        return self._lib.howl_insert(os.path.abspath(path).encode(), line, text.encode("utf-8")) == 0

    def files(self) -> list:
        """The paths of the files shown in the Howl editors."""
        buffer = ctypes.create_string_buffer(65536)
        if self._lib.howl_files(buffer, len(buffer)) != 0:
            return []
        return [path for path in buffer.value.decode("utf-8", "replace").split("\n") if path]

    def theme(self, name: str, path: str) -> bool:
        """Registers the Howl theme file ``path`` under ``name`` and selects it."""
        return self._lib.howl_theme(name.encode(), os.path.abspath(path).encode()) == 0
