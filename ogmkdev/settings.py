"""Settings with two scopes that use the same keys: global (per user) and project.

Both scopes are EditorConfig files, so the whole program has one configuration format:

* global: ``$XDG_CONFIG_HOME/ogmkdev/.editorconfig`` (default ``~/.config/ogmkdev/.editorconfig``),
  its ``[*]`` section applies to every file;
* project: ``.editorconfig`` in the project root, applies to the files below it.

A file's effective settings are the global ones, overridden by the EditorConfig files of the file's
directories (the nearest wins, as in EditorConfig). Writing a value equal to the default removes the
key, so the value is inherited again.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

from . import editorconfig
from .languages import LANGUAGES

PHP_VERSIONS = tuple(LANGUAGES["php"].dialects)
SEVERITIES = ("error", "warning", "hint", "off")


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str
    kind: str                       # choice | int | bool | text
    default: str
    choices: Tuple[str, ...] = ()
    section: str = "*"              # the EditorConfig section the value is written to


SCHEMA: Tuple[Setting, ...] = (
    Setting("indent_style", "Indent style", "Editor", "choice", "space", ("space", "tab")),
    Setting("indent_size", "Indent size", "Editor", "int", "4"),
    Setting("tab_width", "Tab width", "Editor", "int", "4"),
    Setting("end_of_line", "Line endings", "Editor", "choice", "lf", ("lf", "crlf", "cr")),
    Setting("charset", "Charset", "Editor", "choice", "utf-8", ("utf-8", "utf-8-bom", "latin1")),
    Setting("trim_trailing_whitespace", "Trim trailing whitespace", "Editor", "bool", "false"),
    Setting("insert_final_newline", "Final newline", "Editor", "bool", "true"),
    Setting("ogmkdev_current_line", "Highlight the current line", "Editor", "bool", "true"),
    Setting("ogmkdev_autosave", "Autosave while typing (--autosave starts it on)", "Editor", "choice", "off",
            ("on", "off")),
    Setting("ogmkdev_dialect", "PHP version", "Languages", "choice", "8.6", PHP_VERSIONS, section="*.php"),
    Setting("ogmkdev_source_roots", "Source folders (comma separated)", "Workspace", "text", ""),
    Setting("ogmkdev_test_roots", "Test folders (comma separated)", "Workspace", "text", "tests,test,spec"),
    Setting("ogmkdev_exclude", "Ignored folders (not in the tree, not indexed)", "Workspace", "text",
            ".git,node_modules,__pycache__,vendor"),
    Setting("ogmkdev_diagnostics", "Error hinting", "Diagnostics", "choice", "on", ("on", "off")),
    Setting("ogmkdev_diagnostic_php_function", "PHP library functions newer than the version", "Diagnostics",
            "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_php_partial_application", "PHP 8.6 placeholders on older versions", "Diagnostics",
            "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_heredoc_unterminated", "Unterminated heredoc", "Diagnostics",
            "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_js_syntax", "ECMAScript syntax errors", "Diagnostics", "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_baredown_fence", "Unclosed BareDown code block", "Diagnostics",
            "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_sql_not_supported", "ENGINE on a dialect without it", "Diagnostics",
            "choice", "warning", SEVERITIES),
)
SETTINGS_BY_KEY: Dict[str, Setting] = {s.key: s for s in SCHEMA}


def default_global_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ogmkdev", ".editorconfig")


class SettingsStore:
    def __init__(self, project_dir: str, global_path: Optional[str] = None) -> None:
        self.project_dir = os.path.abspath(project_dir)
        self.global_path = global_path or default_global_path()

    def path_for(self, scope: str) -> str:
        if scope == "global":
            return self.global_path
        if scope == "project":
            return os.path.join(self.project_dir, ".editorconfig")
        raise ValueError(f"unknown scope {scope!r}")

    def read(self, scope: str) -> Dict[str, str]:
        """Values written in one scope (all sections), keyed by setting key."""
        path = self.path_for(scope)
        if not os.path.isfile(path):
            return {}
        values: Dict[str, str] = {}
        with open(path, encoding="utf-8") as handle:
            config = editorconfig.parse(handle.read(), path)
        for section in config.sections:
            values.update({k: v for k, v in section.properties.items() if k in SETTINGS_BY_KEY})
        return values

    def write(self, scope: str, setting: Setting, value: str) -> None:
        """Store ``value`` in the scope; the default value removes the key so it is inherited."""
        stored = None if value == setting.default else value
        editorconfig.write_property(self.path_for(scope), setting.section, setting.key, stored)

    def apply(self, scope: str, values: Dict[str, str]) -> None:
        for key, value in values.items():
            self.write(scope, SETTINGS_BY_KEY[key], value)

    def global_properties(self) -> Dict[str, str]:
        if not os.path.isfile(self.global_path):
            return {}
        with open(self.global_path, encoding="utf-8") as handle:
            config = editorconfig.parse(handle.read(), self.global_path)
        props: Dict[str, str] = {}
        for section in config.sections:
            if section.glob == "*":
                props.update(section.properties)
        return props

    def effective_for(self, file_path: str) -> Dict[str, str]:
        props = self.global_properties()
        props.update(editorconfig.effective_properties(file_path))
        return props

    def value(self, key: str, file_path: Optional[str] = None) -> str:
        props = self.effective_for(file_path) if file_path else self.global_properties()
        return props.get(key, SETTINGS_BY_KEY[key].default)


def groups(schema: Sequence[Setting] = SCHEMA):
    """Settings grouped by their group name, in schema order."""
    result: Dict[str, list] = {}
    for setting in schema:
        result.setdefault(setting.group, []).append(setting)
    return list(result.items())
