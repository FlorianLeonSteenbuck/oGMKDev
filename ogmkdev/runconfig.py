"""JetBrains-compatible run and debug configurations (XML).

Files follow the layout JetBrains IDEs write for shared configurations::

    .run/<name>.run.xml
    .idea/runConfigurations/<name>.xml

    <component name="ProjectRunConfigurationManager">
      <configuration default="false" name="..." type="PythonConfigurationType"
                     factoryName="Python" nameIsGenerated="false">
        <option name="SCRIPT_NAME" value="..." />
        <envs><env name="K" value="V" /></envs>
        <method v="2" />
      </configuration>
    </component>

Known children (``option``, ``envs``, ``module``, ``method``, ``EXTENSION``) are
modelled; any other child element is kept verbatim and written back unchanged.
"""

from __future__ import annotations

import glob
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

COMPONENT_NAMES = ("ProjectRunConfigurationManager", "RunManager")
RUN_DIR = ".run"
IDEA_RUN_DIR = os.path.join(".idea", "runConfigurations")
KNOWN_CHILDREN = frozenset({"option", "envs", "module", "method", "EXTENSION"})

# Configuration types this IDE can execute. Types are JetBrains ids where they exist and
# ogmkdev ids otherwise; the values are what the run/debug code dispatches on.
PYTHON_TYPE = "PythonConfigurationType"
SHELL_TYPE = "ShConfigurationType"
GDB_TYPE = "OgmkdevGdbConfigurationType"
XDEBUG_TYPE = "OgmkdevXdebugConfigurationType"


class RunConfigError(ValueError):
    pass


@dataclass
class RunConfiguration:
    name: str
    type: str
    factory: str
    default: bool = False
    name_is_generated: bool = False
    options: Dict[str, str] = field(default_factory=dict)
    envs: Dict[str, str] = field(default_factory=dict)
    module: Optional[str] = None
    before_launch: List[Dict[str, str]] = field(default_factory=list)  # <method> options
    extensions: List[Dict[str, str]] = field(default_factory=list)     # <EXTENSION> attrs
    unknown: List[ET.Element] = field(default_factory=list)           # preserved verbatim
    source_path: Optional[str] = None

    def option(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.options.get(key, default)

    def set_option(self, key: str, value: str) -> None:
        self.options[key] = value

    def to_process(self, project_dir: str) -> "ProcessSpec":
        """Translate the configuration into an argv/cwd/env triple for supported types."""
        cwd = _expand(self.option("WORKING_DIRECTORY") or "$PROJECT_DIR$", project_dir)
        env = dict(os.environ)
        env.update({k: _expand(v, project_dir) for k, v in self.envs.items()})
        params = _split_args(self.option("PARAMETERS", "") or "")
        if self.type == PYTHON_TYPE:
            script = _expand(self.option("SCRIPT_NAME", "") or "", project_dir)
            if not script:
                raise RunConfigError(f"{self.name}: SCRIPT_NAME is empty")
            interpreter = _expand(self.option("SDK_HOME", "") or "python3", project_dir)
            interp_opts = _split_args(self.option("INTERPRETER_OPTIONS", "") or "")
            return ProcessSpec([interpreter, *interp_opts, script, *params], cwd, env)
        if self.type == SHELL_TYPE:
            script = _expand(self.option("SCRIPT_PATH", "") or "", project_dir)
            if script:
                return ProcessSpec(["/bin/sh", script, *params], cwd, env)
            text = self.option("SCRIPT_TEXT", "") or ""
            if not text.strip():
                raise RunConfigError(f"{self.name}: no script")
            return ProcessSpec(["/bin/sh", "-c", text, "sh", *params], cwd, env)
        raise RunConfigError(f"{self.name}: type {self.type} is not executable here")


@dataclass(frozen=True)
class ProcessSpec:
    argv: List[str]
    cwd: str
    env: Dict[str, str]


def _expand(value: str, project_dir: str) -> str:
    return value.replace("$PROJECT_DIR$", project_dir)


def _split_args(text: str) -> List[str]:
    import shlex
    return shlex.split(text) if text.strip() else []


def parse(xml_text: str, source_path: Optional[str] = None) -> RunConfiguration:
    root = ET.fromstring(xml_text)
    if root.tag == "component":
        if root.get("name") not in COMPONENT_NAMES:
            raise RunConfigError(f"unexpected component {root.get('name')!r}")
        configuration = root.find("configuration")
    elif root.tag == "configuration":
        configuration = root
    else:
        raise RunConfigError(f"unexpected root element {root.tag!r}")
    if configuration is None:
        raise RunConfigError("no <configuration> element")
    config = RunConfiguration(
        name=configuration.get("name", ""),
        type=configuration.get("type", ""),
        factory=configuration.get("factoryName", ""),
        default=configuration.get("default", "false") == "true",
        name_is_generated=configuration.get("nameIsGenerated", "false") == "true",
        source_path=source_path,
    )
    if not config.type:
        raise RunConfigError("configuration has no type")
    module = configuration.find("module")
    if module is not None:
        config.module = module.get("name")
    for child in configuration:
        if child.tag == "option":
            config.options[child.get("name", "")] = child.get("value", "")
        elif child.tag == "envs":
            for env in child.findall("env"):
                config.envs[env.get("name", "")] = env.get("value", "")
        elif child.tag == "method":
            for option in child.findall("option"):
                config.before_launch.append(dict(option.attrib))
        elif child.tag == "EXTENSION":
            config.extensions.append(dict(child.attrib))
        elif child.tag not in KNOWN_CHILDREN:
            config.unknown.append(child)
    return config


def dumps(config: RunConfiguration) -> str:
    component = ET.Element("component", {"name": "ProjectRunConfigurationManager"})
    attrs = {
        "default": "true" if config.default else "false",
        "name": config.name,
        "type": config.type,
        "factoryName": config.factory,
    }
    if config.name_is_generated:
        attrs["nameIsGenerated"] = "true"
    else:
        attrs["nameIsGenerated"] = "false"
    node = ET.SubElement(component, "configuration", attrs)
    if config.module:
        ET.SubElement(node, "module", {"name": config.module})
    for key, value in config.options.items():
        ET.SubElement(node, "option", {"name": key, "value": value})
    if config.envs:
        envs = ET.SubElement(node, "envs")
        for key, value in config.envs.items():
            ET.SubElement(envs, "env", {"name": key, "value": value})
    for extension in config.extensions:
        ET.SubElement(node, "EXTENSION", dict(extension))
    if config.before_launch:
        method = ET.SubElement(node, "method", {"v": "2"})
        for option in config.before_launch:
            ET.SubElement(method, "option", dict(option))
    for child in config.unknown:
        node.append(child)
    ET.indent(component, space="  ")
    return ET.tostring(component, encoding="unicode", xml_declaration=False) + "\n"


def save(config: RunConfiguration, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(dumps(config))
    config.source_path = path


def load(path: str) -> RunConfiguration:
    with open(path, encoding="utf-8") as handle:
        return parse(handle.read(), source_path=path)


def discover(project_dir: str) -> List[RunConfiguration]:
    """Read every shared run configuration of a project, skipping unreadable files."""
    configs: List[RunConfiguration] = []
    for directory, pattern in ((RUN_DIR, "*.run.xml"), (IDEA_RUN_DIR, "*.xml")):
        for path in sorted(glob.glob(os.path.join(project_dir, directory, pattern))):
            try:
                configs.append(load(path))
            except (RunConfigError, ET.ParseError, OSError):
                continue
    return configs
