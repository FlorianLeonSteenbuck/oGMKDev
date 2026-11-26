"""Starts the frame: python -m ogmkdev.frame [--folder DIR] [FILE ...]"""

import argparse
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

from .. import projects  # noqa: E402
from ..outcome import Failure  # noqa: E402
from .start import StartWindow  # noqa: E402
from .window import Frame  # noqa: E402


def main(argv):
    parser = argparse.ArgumentParser(prog="ogmkdev")
    parser.add_argument("--folder", default=None,
                        help="folder of the project (default: the start window with the projects opened last, or the "
                             "current folder when there are none)")
    parser.add_argument("--mode", choices=("light", "dark"), default=None,
                        help="light or dark colours (default: the Light or dark colours setting, which this overrides)")
    parser.add_argument("--scheme", choices=("blend", "jetbrains", "eclipse"), default="blend",
                        help="colour scheme (default: blend)")
    parser.add_argument("--autosave", action="store_true",
                        help="save modified files on their own (default: the ogmkdev_autosave setting)")
    parser.add_argument("--clear-index", action="store_true",
                        help="delete the index cache of the folder and read every file again")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    folder = os.path.abspath(args.folder) if args.folder else None  # None: the start window may choose
    files = [os.path.abspath(path) for path in args.files]

    # One running frame per session: starting again with files hands them to the running frame
    app = Gtk.Application(application_id="org.ogmkdev.frame", flags=Gio.ApplicationFlags.HANDLES_OPEN)
    frames = []
    starts = []  # the start window while it is open

    def open_project(application, chosen, paths):
        frames.append(Frame(application, chosen, paths, args.mode, args.scheme,
                            autosave=True if args.autosave else None, clear_index=args.clear_index))
        frames[0].present()
        for window in starts:  # the frame exists now, so the start window can close
            window.destroy()
        starts.clear()

    def show(application, paths):
        if frames:
            for path in paths:
                frames[0].open_file(path)
            frames[0].present()
            return
        if folder is None and not paths:
            if starts:
                starts[0].present()
                return
            recent = projects.recent_projects(limit=projects.START_LIMIT)
            if not isinstance(recent, Failure) and recent:
                choices = projects.start_choices([project.folder for project in recent], os.getcwd())
                opened = {project.folder: project.opened for project in recent}
                window = StartWindow(application, choices, opened,
                                     lambda chosen: open_project(application, chosen, []))
                starts.append(window)
                window.present()
                return
        open_project(application, folder or os.getcwd(), paths)

    app.connect("activate", lambda application: show(application, []))
    app.connect("open", lambda application, gfiles, _count, _hint: show(
        application, [gfile.get_path() for gfile in gfiles]))
    return app.run([sys.argv[0]] + files)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
