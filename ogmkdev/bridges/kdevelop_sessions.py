"""KDevelop's sessions: the projects that were open in each session, read from the sessionrc files of the KDevelop data
folder. Only the projects are imported; they become recent projects.

The format follows KDevelop's own source (kdevelop/kdevplatform/shell/session.cpp and sessioncontroller.cpp): each session
is a folder with a sessionrc file. The session name is written in the root group, which has no header, and the open
projects in the group "General Options" as a list of file URLs, the .kdev4 file of each project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from .kdevelop import kconfig_list, local_path, parse_kconfig


@dataclass(frozen=True)
class KdevSession:
    id: str
    name: str
    folders: Tuple[str, ...]  # the folder of each project that was open in the session, once each


def session_base(environ: Optional[Mapping[str, str]] = None) -> str:
    """KDevelop keeps its sessions in $XDG_DATA_HOME/kdevelop/sessions; ~/.local/share when the variable is not set."""
    env = os.environ if environ is None else environ
    data_home = env.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(data_home, "kdevelop", "sessions")


def read_sessions(base: str) -> List[KdevSession]:
    """The sessions in the folder: every sub-folder with a sessionrc. A session that cannot be read is skipped."""
    if not os.path.isdir(base):
        return []
    sessions: List[KdevSession] = []
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry, "sessionrc")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        groups = parse_kconfig("[root]\n" + text)  # the keys before the first header belong to the root group
        name = groups.get("root", {}).get("SessionName") or entry
        folders: List[str] = []
        for location in kconfig_list(groups.get("General Options", {}).get("Open Projects", "")):
            project = local_path(location)
            folder = os.path.dirname(project) if project.endswith(".kdev4") else project
            if folder and folder not in folders:
                folders.append(folder)
        sessions.append(KdevSession(entry, name, tuple(folders)))
    return sessions
