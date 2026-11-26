"""Importing a JetBrains project as far as the program knows it: the run configurations of .run and .idea/runConfigurations
are read where they are (nothing is copied), the ones of a type this program can run are told apart from those only
listed, and a folder without a JetBrains project is refused. The frame test opens the folder as the project."""

import os
import tempfile
import unittest

from ogmkdev import jetbrains
from ogmkdev.outcome import Failure
from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase

SHELL = ('<component name="RunManager"><configuration name="build" type="ShConfigurationType" '
         'factoryName="Shell Script"><option name="SCRIPT_TEXT" value="make" /></configuration></component>')
PYTHON = ('<configuration name="app" type="PythonConfigurationType" factoryName="Python">'
          '<option name="SCRIPT_NAME" value="$PROJECT_DIR$/main.py" /></configuration>')
APPLICATION = ('<component name="RunManager"><configuration name="gui" type="ApplicationConfigurationType" '
               'factoryName="Application"><option name="MAIN_CLASS_NAME" value="Main" /></configuration></component>')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


class JetBrainsImportTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self._directory.name, "jb")
        write(os.path.join(self.folder, ".idea", "runConfigurations", "build.xml"), SHELL)
        write(os.path.join(self.folder, ".idea", "runConfigurations", "gui.xml"), APPLICATION)
        write(os.path.join(self.folder, ".run", "app.run.xml"), PYTHON)

    def tearDown(self):
        self._directory.cleanup()

    def test_the_configurations_are_told_apart_and_nothing_is_copied(self):
        before = sorted(os.listdir(os.path.join(self.folder, ".run")))
        result = jetbrains.import_project(self.folder)
        self.assertNotIsInstance(result, Failure)
        self.assertEqual(result.runnable, ["app", "build"])
        self.assertEqual(result.listed, ["gui"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.folder, ".run"))), before)

    def test_a_folder_without_a_jetbrains_project_is_refused(self):
        plain = os.path.join(self._directory.name, "plain")
        os.makedirs(plain)
        self.assertIsInstance(jetbrains.import_project(plain), Failure)


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class JetBrainsFrameTests(FrameTestCase):
    def test_the_folder_opens_as_the_project_and_its_configurations_are_listed(self):
        class Chooser:
            def __init__(self, path):
                self.path = path

            def get_file(self):
                from gi.repository import Gio

                return Gio.File.new_for_path(self.path)

        from gi.repository import Gtk

        folder = os.path.join(self._directory.name, "jb")
        write(os.path.join(folder, ".run", "app.run.xml"), PYTHON)
        frame = self.frame()
        frame._on_jetbrains_chosen(Chooser(folder), Gtk.ResponseType.ACCEPT)
        self.assertEqual(frame.folder, os.path.abspath(folder))
        self.assertEqual([row[0] for row in frame.run_store], ["app"])
        self.assertIn("1 run configuration(s) can run here", frame.status.get_text())


if __name__ == "__main__":
    unittest.main()
