"""KDevelop bridge: project files and C++ test data from the original KDevelop sources.

* ``.kdev4`` project files use KConfig syntax (``[Group]`` headers, ``Key=Value`` lines,
  ``\\s``/``\\n``/``\\t``/``\\\\`` escapes). :func:`load_project` reads them.
* The GDB/MI parser tests of KDevelop (``plugins/debuggercommon/tests/test_miparser.cpp``,
  ``plugins/gdb/unittests/test_gdb.cpp``) contain MI transcripts as C++ string literals.
  :func:`mi_corpus` extracts them so :mod:`ogmkdev.debug.gdb_mi` can be checked against the
  same data KDevelop uses for its own parser.

The C++ analysis itself lives in ``plugins/clang`` and needs KDevelop built against Qt and
KDE Frameworks; this module does not build or link it.
"""

from __future__ import annotations

import os
import re
import shlex
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from . import KDEVELOP_SOURCE
from .. import runconfig
from ..outcome import Failure, failed

MI_TEST_FILES = (
    os.path.join("plugins", "debuggercommon", "tests", "test_miparser.cpp"),
    os.path.join("plugins", "gdb", "unittests", "test_gdb.cpp"),
)
_C_STRING = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
_MI_SHAPE = re.compile(r'^\d*(?:[~@&]"|[\^*+=][A-Za-z][A-Za-z-]*(?:,|$)|\(gdb\)$)')
_KCONFIG_ESCAPE = re.compile(r"\\([snrt\\])")
_KCONFIG_MAP = {"s": " ", "n": "\n", "r": "\r", "t": "\t", "\\": "\\"}
_C_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\", "?": "?", "0": "\0"}


@dataclass
class KdevProject:
    name: str
    manager: str
    groups: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def get(self, group: str, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.groups.get(group, {}).get(key, default)


def parse_kconfig(text: str) -> Dict[str, Dict[str, str]]:
    groups: Dict[str, Dict[str, str]] = {}
    current: Optional[Dict[str, str]] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            # Nested KConfig groups are written as [A][B] and stored as "A][B".
            current = groups.setdefault(line[1:-1], {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = _KCONFIG_ESCAPE.sub(lambda m: _KCONFIG_MAP[m.group(1)], value)
    return groups


def load_project(path: str) -> KdevProject:
    with open(path, encoding="utf-8") as handle:
        groups = parse_kconfig(handle.read())
    project = groups.get("Project", {})
    return KdevProject(name=project.get("Name", ""), manager=project.get("Manager", ""), groups=groups)


def _c_unescape(text: str) -> str:
    out: List[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            out.append(_C_ESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


NATIVE_APP_TYPE = "nativeAppConfigType"  # KDevelop's native application; the other types are reported as skipped


def kconfig_list(text: str) -> List[str]:
    """A KConfig list (a QStringList): items separated by commas, a comma inside an item written as a backslash and a
    comma. Empty items are left out."""
    items: List[str] = []
    current: List[str] = []
    index = 0
    while index < len(text):
        if text.startswith("\\,", index):
            current.append(",")
            index += 2
        elif text[index] == ",":
            items.append("".join(current))
            current = []
            index += 1
        else:
            current.append(text[index])
            index += 1
    items.append("".join(current))
    return [item for item in items if item]


def local_path(location: str) -> str:
    """The local path of a KDevelop location: a file:// URL, or the text itself when it is a path already."""
    parsed = urllib.parse.urlsplit(location)
    if parsed.scheme == "file":
        return urllib.parse.unquote(parsed.path)
    return location


def launch_configurations(project: KdevProject) -> Tuple[List[runconfig.RunConfiguration], List[str]]:
    """The launch configurations of a project file as shell run configurations. A native application runs its executable
    with its arguments in its working folder; the arguments are the positional parameters of the command, passed on by
    "$@". The other types, and the entries without an executable, are returned as skipped, with the reason."""
    configs: List[runconfig.RunConfiguration] = []
    skipped: List[str] = []
    for group in kconfig_list(project.get("Launch Configurations", "Configurations", "") or ""):
        base = f"Launch Configurations][{group}"
        name = project.groups.get(base, {}).get("Name", group)
        kind = project.groups.get(base, {}).get("Type", "")
        if kind != NATIVE_APP_TYPE:
            skipped.append(f"{name}: the type {kind or 'missing'} is not imported")
            continue
        data = project.groups.get(base + "][Data", {})
        executable = local_path(data.get("Executable", ""))
        if not executable:
            skipped.append(f"{name}: no executable")
            continue
        arguments = " ".join(shlex.quote(argument) for argument in kconfig_list(data.get("Arguments", "")))
        working = local_path(data.get("Working Directory", "")) or runconfig.DEFAULT_WORKING_DIRECTORY
        configs.append(runconfig.shell_configuration(name, f'{shlex.quote(executable)} "$@"', arguments, working))
    return configs, skipped


@dataclass
class ImportResult:
    written: List[str]    # the run configurations saved in the project's .run folder
    existing: List[str]   # the names that have a file already: that file is kept
    skipped: List[str]    # the entries that cannot be imported, with the reason


def import_project(kdev4_path: str) -> Union[ImportResult, Failure]:
    """Saves the launch configurations of a KDevelop project as run configurations in the project's folder, the folder of
    its .kdev4 file. The files of the folder stay as they are: the project's tree is the same tree."""
    try:
        project = load_project(kdev4_path)
    except OSError as problem:
        return failed(f"{kdev4_path}: {problem}")
    configs, skipped = launch_configurations(project)
    folder = os.path.dirname(os.path.abspath(kdev4_path))
    result = ImportResult(written=[], existing=[], skipped=list(skipped))
    for config in configs:
        name = runconfig.valid_name(config.name)
        if isinstance(name, Failure):
            result.skipped.append(f"{config.name}: {name}")
            continue
        config.name = name
        path = runconfig.configuration_path(folder, name)
        if os.path.exists(path):
            result.existing.append(name)
            continue
        try:
            runconfig.save(config, path)
        except OSError as problem:
            return failed(f"{path}: {problem}")
        result.written.append(name)
    return result


def mi_corpus(kdevelop_root: str = KDEVELOP_SOURCE) -> List[str]:
    """MI transcript lines found as C string literals in KDevelop's GDB/MI tests."""
    lines: List[str] = []
    for relative in MI_TEST_FILES:
        path = os.path.join(kdevelop_root, relative)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            source = handle.read()
        for match in _C_STRING.finditer(source):
            text = _c_unescape(match.group(1))
            if _MI_SHAPE.match(text):
                lines.append(text)
    return lines
