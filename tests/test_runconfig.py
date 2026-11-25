import os
import tempfile
import unittest

from ogmkdev import runconfig as RC

SAMPLE = """<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="Run main" type="PythonConfigurationType" factoryName="Python" nameIsGenerated="false">
    <module name="proj" />
    <option name="SCRIPT_NAME" value="$PROJECT_DIR$/main.py" />
    <option name="PARAMETERS" value="--verbose 'two words'" />
    <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$/src" />
    <envs>
      <env name="APP_MODE" value="dev" />
    </envs>
    <EXTENSION ID="PythonCoverageRunConfigurationExtension" runner="coverage" />
    <method v="2">
      <option name="Make" enabled="true" />
    </method>
    <custom_tool name="kept" />
  </configuration>
</component>
"""


class RunConfigTests(unittest.TestCase):
    def test_parse_model(self):
        config = RC.parse(SAMPLE)
        self.assertEqual(config.name, "Run main")
        self.assertEqual(config.type, RC.PYTHON_TYPE)
        self.assertEqual(config.factory, "Python")
        self.assertEqual(config.module, "proj")
        self.assertEqual(config.envs, {"APP_MODE": "dev"})
        self.assertEqual(config.before_launch, [{"name": "Make", "enabled": "true"}])
        self.assertEqual(config.extensions[0]["runner"], "coverage")
        self.assertEqual([c.tag for c in config.unknown], ["custom_tool"])

    def test_round_trip_keeps_unknown_elements(self):
        once = RC.dumps(RC.parse(SAMPLE))
        twice = RC.dumps(RC.parse(once))
        self.assertEqual(once, twice)
        self.assertIn('<custom_tool name="kept" />', once)
        self.assertIn('<env name="APP_MODE" value="dev" />', once)

    def test_python_process_spec(self):
        config = RC.parse(SAMPLE)
        spec = config.to_process("/work/proj")
        self.assertEqual(spec.argv[-3:], ["/work/proj/main.py", "--verbose", "two words"])
        self.assertEqual(spec.cwd, "/work/proj/src")
        self.assertEqual(spec.env["APP_MODE"], "dev")

    def test_shell_script_text_and_missing_script(self):
        shell = RC.parse('<configuration name="s" type="ShConfigurationType" factoryName="Shell Script">'
                         '<option name="SCRIPT_TEXT" value="echo hi" /></configuration>')
        self.assertEqual(shell.to_process("/p").argv[:3], ["/bin/sh", "-c", "echo hi"])
        empty = RC.RunConfiguration(name="x", type=RC.PYTHON_TYPE, factory="Python")
        with self.assertRaises(RC.RunConfigError):
            empty.to_process("/p")

    def test_unsupported_type_is_an_error(self):
        config = RC.RunConfiguration(name="x", type="ApplicationConfigurationType", factory="Application")
        with self.assertRaises(RC.RunConfigError):
            config.to_process("/p")

    def test_discover_reads_both_jetbrains_locations(self):
        with tempfile.TemporaryDirectory() as project:
            os.makedirs(os.path.join(project, ".run"))
            os.makedirs(os.path.join(project, ".idea", "runConfigurations"))
            with open(os.path.join(project, ".run", "a.run.xml"), "w", encoding="utf-8") as h:
                h.write(SAMPLE)
            with open(os.path.join(project, ".idea", "runConfigurations", "b.xml"), "w", encoding="utf-8") as h:
                h.write('<component name="RunManager"><configuration name="b" type="ShConfigurationType" factoryName="Shell Script"/></component>')
            with open(os.path.join(project, ".run", "broken.run.xml"), "w", encoding="utf-8") as h:
                h.write("<component")
            names = sorted(c.name for c in RC.discover(project))
            self.assertEqual(names, ["Run main", "b"])

    def test_save_then_load(self):
        with tempfile.TemporaryDirectory() as project:
            config = RC.parse(SAMPLE)
            path = os.path.join(project, ".run", "Run main.run.xml")
            RC.save(config, path)
            again = RC.load(path)
            self.assertEqual(again.options, config.options)
            self.assertEqual(again.source_path, path)


if __name__ == "__main__":
    unittest.main()
