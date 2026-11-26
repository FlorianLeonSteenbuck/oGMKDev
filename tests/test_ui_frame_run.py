"""The Run Configurations dialog: a new shell configuration is saved to the .run folder and runs its command; a saved one
is edited with its name kept; a name that exists is not overwritten; a configuration of another type is shown only.

Needs PyGObject with GTK 4, a display (run under xvfb-run) and libhowl.so; otherwise it is skipped.
"""

import os
import tempfile
import unittest

from ogmkdev import runconfig
from tests.frame_support import GTK_AVAILABLE, SKIP_REASON, FrameTestCase

if GTK_AVAILABLE:
    from gi.repository import Gtk


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class RunConfigurationDialogTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.project = os.path.join(self._directory.name, "project")
        os.makedirs(self.project)
        self.parent = Gtk.Window()
        self.addCleanup(self.parent.destroy)
        self.saved = []

    def tearDown(self):
        self._directory.cleanup()

    def open_dialog(self):
        from ogmkdev.frame.runconfig_dialog import RunConfigurationDialog

        dialog = RunConfigurationDialog(self.parent, self.project, self.saved.append)
        self.addCleanup(dialog.destroy)
        return dialog

    def saved_file(self, name):
        return runconfig.load(runconfig.configuration_path(self.project, name))

    def test_a_new_configuration_is_saved_to_the_run_folder_and_runs_its_command(self):
        dialog = self.open_dialog()
        dialog.name.set_text("tests")
        dialog.command.set_text('python3 -m unittest "$@"')
        dialog.arguments.set_text("-v")
        dialog.folder.set_text("$PROJECT_DIR$/src")
        dialog.environment.get_buffer().set_text("MODE=dev")
        dialog.save()
        self.assertTrue(os.path.isfile(runconfig.configuration_path(self.project, "tests")))
        self.assertEqual(self.saved, ["tests"])
        spec = self.saved_file("tests").to_process(self.project)
        self.assertEqual(spec.argv, ["/bin/sh", "-c", 'python3 -m unittest "$@"', "sh", "-v"])
        self.assertEqual(spec.cwd, os.path.join(self.project, "src"))
        self.assertEqual(spec.env["MODE"], "dev")

    def test_a_saved_configuration_is_edited_and_keeps_its_name(self):
        dialog = self.open_dialog()
        dialog.name.set_text("tests")
        dialog.command.set_text("make test")
        dialog.save()
        self.assertFalse(dialog.name.get_editable())  # the name is the file name: it does not change when edited
        dialog.command.set_text("make check")
        dialog.save()
        self.assertEqual(self.saved_file("tests").option("SCRIPT_TEXT"), "make check")
        self.assertEqual(self.saved, ["tests", "tests"])

    def test_a_name_that_exists_is_not_overwritten(self):
        first = self.open_dialog()
        first.name.set_text("tests")
        first.command.set_text("make test")
        first.save()
        second = self.open_dialog()
        second.name.set_text("tests")
        second.command.set_text("make clean")
        second.save()
        self.assertIn("exists", second.message.get_text())
        self.assertEqual(self.saved_file("tests").option("SCRIPT_TEXT"), "make test")

    def test_an_empty_command_or_a_wrong_environment_line_is_refused_and_nothing_is_written(self):
        dialog = self.open_dialog()
        dialog.name.set_text("empty")
        dialog.save()
        self.assertIn("empty", dialog.message.get_text())
        dialog.command.set_text("make")
        dialog.environment.get_buffer().set_text("broken line")
        dialog.save()
        self.assertIn("KEY=VALUE", dialog.message.get_text())
        self.assertFalse(os.path.exists(runconfig.configuration_path(self.project, "empty")))

    def test_a_configuration_of_another_type_is_shown_but_not_edited_here(self):
        app = runconfig.parse('<configuration name="app" type="PythonConfigurationType" factoryName="Python">'
                              '<option name="SCRIPT_NAME" value="$PROJECT_DIR$/main.py" /></configuration>')
        runconfig.save(app, runconfig.configuration_path(self.project, "app"))
        dialog = self.open_dialog()
        dialog.list.select_row(dialog.list.get_row_at_index(0))
        self.assertFalse(dialog._save_button.get_sensitive())
        self.assertIn("the type PythonConfigurationType", dialog.message.get_text())


@unittest.skipUnless(GTK_AVAILABLE, SKIP_REASON)
class RunMenuTests(FrameTestCase):
    def test_the_run_menu_creates_a_configuration_and_the_run_tab_selects_it(self):
        frame = self.frame()
        dialog = frame.edit_run_configurations()
        self.addCleanup(dialog.destroy)
        dialog.name.set_text("serve")
        dialog.command.set_text("php -S localhost:8000")
        dialog.save()
        model, iterator = frame.run_view.get_selection().get_selected()
        self.assertIsNotNone(iterator)
        self.assertEqual(model[iterator][0], "serve")
        self.assertEqual(len(frame.run_store), 1)

    def test_importing_a_kdevelop_project_opens_its_folder_with_the_run_configurations(self):
        from gi.repository import Gio

        class Chooser:  # what the file chooser answers: the chosen file
            def __init__(self, path):
                self.path = path

            def get_file(self):
                return Gio.File.new_for_path(self.path)

        frame = self.frame()
        kdevelop = os.path.join(self._directory.name, "imported")
        os.makedirs(kdevelop)
        app = os.path.join(kdevelop, "app")
        with open(app, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        project = os.path.join(kdevelop, "imported.kdev4")
        with open(project, "w", encoding="utf-8") as handle:
            handle.write("[Project]\nName=imported\nManager=KDevCustomBuildSystem\n\n"
                         "[Launch Configurations]\nConfigurations=Launch Configuration 0\n\n"
                         "[Launch Configurations][Launch Configuration 0]\nName=Run app\n"
                         "Type=nativeAppConfigType\n\n"
                         f"[Launch Configurations][Launch Configuration 0][Data]\nExecutable=file://{app}\n")
        frame._on_kdevelop_chosen(Chooser(project), Gtk.ResponseType.ACCEPT)
        self.assertEqual(frame.folder, os.path.abspath(kdevelop))
        self.assertEqual([row[0] for row in frame.run_store], ["Run app"])
        self.assertIn("1 run configuration(s)", frame.status.get_text())


if __name__ == "__main__":
    unittest.main()
