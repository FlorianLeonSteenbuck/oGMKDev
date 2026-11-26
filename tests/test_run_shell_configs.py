"""The shell run configurations of the Run Configurations dialog, without GTK: the name that is a file name, the environment
text, the arguments that a command reads, the saved file, and editing a configuration that keeps what the form does not
show."""

import tempfile
import unittest

from ogmkdev import runconfig as RC
from ogmkdev.outcome import Failure


class ShellConfigurationTests(unittest.TestCase):
    def test_a_name_is_a_file_name(self):
        self.assertEqual(RC.valid_name("  build tests "), "build tests")
        self.assertIsInstance(RC.valid_name(""), Failure)
        self.assertIsInstance(RC.valid_name("ci/build"), Failure)
        self.assertIsInstance(RC.valid_name(".hidden"), Failure)

    def test_the_environment_text_reads_back_and_refuses_a_line_without_equals(self):
        envs = RC.environment_from_text("# comment\nAPP_MODE=dev\n\nEMPTY=\nPATH_EXTRA=a=b\n")
        self.assertEqual(envs, {"APP_MODE": "dev", "EMPTY": "", "PATH_EXTRA": "a=b"})
        self.assertEqual(RC.environment_from_text(RC.environment_text(envs)), envs)
        refused = RC.environment_from_text("GOOD=1\nnot a variable\n")
        self.assertIsInstance(refused, Failure)
        self.assertIn("line 2", str(refused))

    def test_a_command_reads_its_arguments_through_the_positional_parameters(self):
        self.assertTrue(RC.reads_arguments('pytest "$@"'))
        self.assertTrue(RC.reads_arguments("echo $1"))
        self.assertTrue(RC.reads_arguments("echo ${2:-x}"))
        self.assertFalse(RC.reads_arguments("make test"))

    def test_a_saved_shell_configuration_runs_its_command_with_the_arguments(self):
        with tempfile.TemporaryDirectory() as project:
            config = RC.shell_configuration("tests", 'python3 -m unittest "$@"', "-v test_x", envs={"MODE": "dev"})
            path = RC.configuration_path(project, "tests")
            RC.save(config, path)
            loaded = RC.load(path)
            self.assertEqual(loaded.name, "tests")
            self.assertEqual(loaded.type, RC.SHELL_TYPE)
            spec = loaded.to_process(project)
            self.assertEqual(spec.argv, ["/bin/sh", "-c", 'python3 -m unittest "$@"', "sh", "-v", "test_x"])
            self.assertEqual(spec.cwd, project)
            self.assertEqual(spec.env["MODE"], "dev")

    def test_editing_keeps_the_options_the_form_does_not_show(self):
        xml = ('<component name="ProjectRunConfigurationManager"><configuration name="b" type="ShConfigurationType" '
               'factoryName="Shell Script"><option name="SCRIPT_TEXT" value="old" />'
               '<custom_tool name="kept" /></configuration></component>')
        edited = RC.shell_configuration("b", "new", "", base=RC.parse(xml))
        self.assertEqual(edited.option("SCRIPT_TEXT"), "new")
        self.assertIn('<custom_tool name="kept" />', RC.dumps(edited))


if __name__ == "__main__":
    unittest.main()
