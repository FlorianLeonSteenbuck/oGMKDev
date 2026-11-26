"""Importing a JetBrains project, as far as this program knows JetBrains projects: the run configurations they share, in the
.run folder and in .idea/runConfigurations (see runconfig.py). Those are used where they are, so nothing is copied. The
import opens the folder as the project and says which configurations can run here. The other files of a JetBrains
project (module files, code styles, the workspace) are not read: this program does not model them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Union

from . import runconfig
from .outcome import Failure, failed

RUNNABLE_TYPES = (runconfig.PYTHON_TYPE, runconfig.SHELL_TYPE, runconfig.GDB_TYPE, runconfig.XDEBUG_TYPE)


@dataclass(frozen=True)
class JetBrainsImport:
    folder: str
    runnable: List[str]   # the configurations of a type this program can run
    listed: List[str]     # the configurations of other types: listed, not run


def import_project(folder: str) -> Union[JetBrainsImport, Failure]:
    """Reads the run configurations of a JetBrains project folder (one with a .idea or a .run folder)."""
    folder = os.path.abspath(folder)
    if not (os.path.isdir(os.path.join(folder, ".idea")) or os.path.isdir(os.path.join(folder, runconfig.RUN_DIR))):
        return failed(f"{folder} has neither a .idea nor a .run folder: not a JetBrains project")
    runnable, listed = [], []
    for config in runconfig.discover(folder):
        (runnable if config.type in RUNNABLE_TYPES else listed).append(config.name)
    return JetBrainsImport(folder, sorted(runnable), sorted(listed))
