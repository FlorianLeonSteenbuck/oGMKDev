"""Starts the frame: python -m ogmkdev.frame [--folder DIR] [FILE ...]"""

import argparse
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

from .window import Frame  # noqa: E402


def main(argv):
    parser = argparse.ArgumentParser(prog="ogmkdev")
    parser.add_argument("--folder", default=os.getcwd(), help="folder (default: the current folder)")
    parser.add_argument("--mode", choices=("light", "dark"), default="light", help="colours (default: light)")
    parser.add_argument("--scheme", choices=("blend", "jetbrains", "eclipse"), default="blend",
                        help="colour scheme (default: blend)")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    folder = os.path.abspath(args.folder)
    files = [os.path.abspath(path) for path in args.files]

    app = Gtk.Application(application_id="org.ogmkdev.frame", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda application: Frame(application, folder, files, args.mode,
                                                       args.scheme).present())
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
