"""Adapters to the KDevelop source tree that is imported into this repository under ``kdevelop/``.

* :mod:`ogmkdev.bridges.kdevelop` reads KDevelop's ``.kdev4`` project files and takes the
  GDB/MI test corpus from KDevelop's C++ sources, so the MI parser is checked against the data
  KDevelop uses for its own parser.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KDEVELOP_SOURCE = os.path.join(REPO_ROOT, "kdevelop")
