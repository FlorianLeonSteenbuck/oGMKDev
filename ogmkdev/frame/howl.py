"""Howl's editor as GTK 4 widgets: loads libhowl.so and hands it containers of the frame."""

from __future__ import annotations

import ctypes
import os
from typing import Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOWL_ROOT = os.path.join(ROOT, "howl")
LIBRARY = os.path.join(HOWL_ROOT, "src", "libhowl.so")

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

    def theme(self, name: str, path: str) -> bool:
        """Registers the Howl theme file ``path`` under ``name`` and selects it."""
        return self._lib.howl_theme(name.encode(), os.path.abspath(path).encode()) == 0
