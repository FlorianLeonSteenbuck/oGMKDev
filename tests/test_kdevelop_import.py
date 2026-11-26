"""Importing the launch configurations of a KDevelop project file. A native application becomes a shell run configuration
that runs its executable with its arguments, in its working folder. Other types are reported as skipped. A run
configuration that has a file already is kept. The vendored KDevelop source has no launch configurations: it imports
without writing anything."""

import os
import subprocess
import tempfile
import unittest

from ogmkdev import runconfig
from ogmkdev.bridges import KDEVELOP_SOURCE
from ogmkdev.bridges import kdevelop as K
from ogmkdev.outcome import Failure

PROJECT = r"""[Project]
Name=sample
Manager=KDevCustomBuildSystem

[Launch Configurations]
Configurations=Launch Configuration 0,Launch Configuration 1

[Launch Configurations][Launch Configuration 0]
Name=Run app
Type=nativeAppConfigType

[Launch Configurations][Launch Configuration 0][Data]
Executable=file://FOLDER/app
Arguments=--verbose,--name=a\,b
Working Directory=file://FOLDER

[Launch Configurations][Launch Configuration 1]
Name=Test script
Type=scriptAppConfigType
"""

APP = '#!/bin/sh\nprintf "%s\\n" "$@"\n'


class LaunchImportTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self._directory.name, "sample")
        os.makedirs(self.folder)
        self.app = os.path.join(self.folder, "app")
        with open(self.app, "w", encoding="utf-8") as handle:
            handle.write(APP)
        os.chmod(self.app, 0o755)
        self.kdev4 = os.path.join(self.folder, "sample.kdev4")
        with open(self.kdev4, "w", encoding="utf-8") as handle:
            handle.write(PROJECT.replace("FOLDER", self.folder))

    def tearDown(self):
        self._directory.cleanup()

    def test_a_native_application_is_saved_and_runs_with_its_arguments(self):
        result = K.import_project(self.kdev4)
        self.assertNotIsInstance(result, Failure)
        self.assertEqual(result.written, ["Run app"])
        self.assertEqual(result.existing, [])
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("Test script", result.skipped[0])
        config = runconfig.load(runconfig.configuration_path(self.folder, "Run app"))
        spec = config.to_process(self.folder)
        self.assertEqual(spec.cwd, self.folder)
        completed = subprocess.run(spec.argv, cwd=spec.cwd, env=spec.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.stdout, "--verbose\n--name=a,b\n")

    def test_a_configuration_that_has_a_file_already_is_kept(self):
        K.import_project(self.kdev4)
        again = K.import_project(self.kdev4)
        self.assertEqual(again.written, [])
        self.assertEqual(again.existing, ["Run app"])

    def test_a_list_of_arguments_reads_commas_and_escaped_commas(self):
        self.assertEqual(K.kconfig_list(r"a,b\,c,,d"), ["a", "b,c", "d"])
        self.assertEqual(K.kconfig_list(""), [])

    def test_the_vendored_kdevelop_project_imports_without_writing_anything(self):
        path = os.path.join(KDEVELOP_SOURCE, "kdevelop.kdev4")
        if not os.path.isfile(path):
            self.skipTest("kdevelop/ source tree is missing")
        result = K.import_project(path)
        self.assertNotIsInstance(result, Failure)
        self.assertEqual((result.written, result.existing, result.skipped), ([], [], []))


if __name__ == "__main__":
    unittest.main()
