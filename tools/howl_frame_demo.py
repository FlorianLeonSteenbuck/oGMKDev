"""A GTK 4 Python window with Howl's editor as a widget inside its layout (same process).

Howl is built as libhowl.so (howl/src, make libhowl.so); the library puts the editor's content
into a GtkBox that this program owns.
"""

import ctypes
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOWL_ROOT = os.path.join(ROOT, "howl")

_api = ctypes.pythonapi
_api.PyCapsule_GetPointer.restype = ctypes.c_void_p
_api.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]


def raw_pointer(gobject):
    """The C pointer of a PyGObject object (its __gpointer__ capsule)."""
    return _api.PyCapsule_GetPointer(gobject.__gpointer__, None)


howl = ctypes.CDLL(os.path.join(HOWL_ROOT, "src", "libhowl.so"))
howl.howl_embed.restype = ctypes.c_int
howl.howl_embed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]


def on_activate(application):
    window = Gtk.ApplicationWindow(application=application, title="oGMKDev")
    window.set_default_size(1100, 700)
    layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    window.set_child(layout)
    file = sys.argv[1].encode() if len(sys.argv) > 1 else None
    status = howl.howl_embed(raw_pointer(layout), HOWL_ROOT.encode(), file)
    print("howl_embed status:", status, flush=True)
    window.present()


app = Gtk.Application(application_id="org.ogmkdev.howlframe")
app.connect("activate", on_activate)
app.run(None)
