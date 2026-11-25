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
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import KDEVELOP_SOURCE

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
