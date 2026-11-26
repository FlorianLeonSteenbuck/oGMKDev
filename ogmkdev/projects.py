"""The projects the frame has opened, with the folders attached to each one (File > Add Folder).

The projects are kept in ``projects.json`` in the global configuration folder, next to the global EditorConfig file.
Opening a project again restores the folders that were attached to it. Each record keeps the time the project was
opened last; the most recent project comes first.

The file is read and written as a whole. A file that cannot be read is never overwritten: saving then answers with the
reason, so a file with a mistake can be repaired by hand instead of being replaced.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from dataclasses import dataclass
from typing import List, Sequence, Tuple, Union

from .outcome import Failure, failed
from .settings import default_global_path

FILE_NAME = "projects.json"
KEEP = 50  # the projects kept; the ones opened longest ago are dropped


@dataclass(frozen=True)
class Project:
    """A project as the file holds it: its folder, the folders attached to it, and when it was opened last."""

    folder: str
    attached: Tuple[str, ...]
    opened: str


def projects_path() -> str:
    """The projects file, in the global configuration folder."""
    return os.path.join(os.path.dirname(default_global_path()), FILE_NAME)


def read_projects(path: str) -> Union[List[Project], Failure]:
    """The projects the file holds; none when there is no file. A file that cannot be read gives the reason. An entry
    of another shape is skipped, the others still count."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as problem:
        return failed(f"{path}: {problem}")
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        return failed(f"{path}: expected an object with a list of projects")
    projects: List[Project] = []
    for entry in data["projects"]:
        if not isinstance(entry, dict):
            continue
        folder, attached, opened = entry.get("folder"), entry.get("attached", []), entry.get("opened", "")
        if isinstance(folder, str) and isinstance(attached, list) and isinstance(opened, str):
            projects.append(Project(folder, tuple(item for item in attached if isinstance(item, str)), opened))
    return projects


def write_projects(path: str, projects: Sequence[Project]) -> Union[str, Failure]:
    """Writes the projects through a temporary file, so that a failure leaves the old file whole. Returns the path."""
    data = {"projects": [{"folder": project.folder, "attached": list(project.attached), "opened": project.opened}
                         for project in projects]}
    folder = os.path.dirname(path)
    temporary = ""
    try:
        os.makedirs(folder, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=folder, prefix=".projects-", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
        os.replace(temporary, path)
    except OSError as problem:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
        return failed(f"{path}: {problem}")
    return path


def remember(folder: str, attached: Sequence[str]) -> Union[str, Failure]:
    """Saves the project with the folders attached to it, opened now. The projects saved before stay behind it. Returns
    the path of the file, or the reason the file could not be read or written."""
    path = projects_path()
    existing = read_projects(path)
    if isinstance(existing, Failure):
        return existing
    opened = datetime.datetime.now().isoformat(timespec="seconds")
    record = Project(folder, tuple(dict.fromkeys(attached)), opened)
    others = [project for project in existing if project.folder != folder]
    return write_projects(path, [record] + others[:KEEP - 1])


def attached_folders(folder: str) -> Union[List[str], Failure]:
    """The folders attached to the project the last time it was open, without those that no longer exist."""
    projects = read_projects(projects_path())
    if isinstance(projects, Failure):
        return projects
    for project in projects:
        if project.folder == folder:
            return [path for path in project.attached if path != folder and os.path.isdir(path)]
    return []
