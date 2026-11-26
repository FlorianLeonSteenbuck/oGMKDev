"""The layout of the install tree (packaging/install-tree.sh): libhowl.so goes to usr/lib by default, and to the
library directory given for the RPM (usr/lib64 on 64-bit systems). Needs howl/src/libhowl.so, which
packaging/build-howl.sh builds; without it the tests are skipped."""

import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY = os.path.join(ROOT, "howl", "src", "libhowl.so")


@unittest.skipUnless(os.path.isfile(LIBRARY), "needs howl/src/libhowl.so (packaging/build-howl.sh)")
class InstallTreeTest(unittest.TestCase):
    def _install(self, *args):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        subprocess.run(["sh", "packaging/install-tree.sh", directory.name, *args], cwd=ROOT, check=True,
                       capture_output=True)
        return directory.name

    def test_the_library_goes_to_usr_lib_by_default(self):
        root = self._install()
        self.assertTrue(os.path.isfile(os.path.join(root, "usr", "lib", "ogmkdev", "libhowl.so")))

    def test_the_library_goes_to_the_given_library_directory(self):
        root = self._install("/usr/lib64")
        self.assertTrue(os.path.isfile(os.path.join(root, "usr", "lib64", "ogmkdev", "libhowl.so")))
        self.assertFalse(os.path.exists(os.path.join(root, "usr", "lib", "ogmkdev")))


if __name__ == "__main__":
    unittest.main()
