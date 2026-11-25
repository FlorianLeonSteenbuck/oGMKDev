"""Adapters to the original KDevelop sources vendored under ``vendor/kdevelop``.

* :mod:`ogmkdev.bridges.kdevelop` reads KDevelop's ``.kdev4`` project files and takes the
  GDB/MI test corpus from KDevelop's C++ sources, so the MI parser is checked against the
  data KDevelop uses for its own parser.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VENDOR_KDEVELOP = os.path.join(REPO_ROOT, "vendor", "kdevelop")
