"""Starts the frame: python -m ogmkdev.frame [--project DIR] [FILE ...]"""

import argparse
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

from .window import Frame  # noqa: E402


def main(argv):
    parser = argparse.ArgumentParser(prog="ogmkdev")
    parser.add_argument("--project", default=os.getcwd(), help="project folder (default: the current folder)")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    project = os.path.abspath(args.project)
    files = [os.path.abspath(path) for path in args.files]

    app = Gtk.Application(application_id="org.ogmkdev.frame", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda application: Frame(application, project, files).present())
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
