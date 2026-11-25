"""Tests run with their own XDG directories, so history, index cache and settings never touch the user's home."""

import atexit
import os
import shutil
import tempfile

_TEST_HOME = tempfile.mkdtemp(prefix="ogmkdev-tests-")
os.environ["XDG_DATA_HOME"] = os.path.join(_TEST_HOME, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_TEST_HOME, "cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TEST_HOME, "config")
atexit.register(shutil.rmtree, _TEST_HOME, True)
