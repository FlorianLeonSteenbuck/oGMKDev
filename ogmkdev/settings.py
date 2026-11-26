"""Settings with two scopes that use the same keys: global (per user) and project.

Both scopes are EditorConfig files, so the whole program has one configuration format:

* global: ``$XDG_CONFIG_HOME/ogmkdev/.editorconfig`` (default ``~/.config/ogmkdev/.editorconfig``),
  its ``[*]`` section applies to every file;
* project: ``.editorconfig`` in the project root, applies to the files below it.

A file's effective settings are the global ones, overridden by the EditorConfig files of the file's
directories (the nearest wins, as in EditorConfig). Writing a value equal to the default removes the
key, so the value is inherited again.

The settings dialog edits a model of the OtherSettings library (ogmkdev.othersettings): one provider per
setting, with the type the setting has (a checkbox, a number, a choice, a text line). The categories of the
dialog are the ``group`` paths of the schema: "Diagnostics / PHP" is a category inside "Diagnostics", and a
path may be as deep as needed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from . import editorconfig
from .languages import LANGUAGES
from .outcome import Failure, failed
from .othersettings import (BooleanCheckboxProvider, ColorPickerProvider, NumberInputProvider, PairsProvider,
                            Pairs, PreStoredSettings, SettingProvider, SettingsTyp, StringLineProvider)

PHP_VERSIONS = tuple(LANGUAGES["php"].dialects)
SEVERITIES = ("error", "warning", "hint", "off")
KEYWORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
COLOUR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")
CATEGORY_SEPARATOR = "/"


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    group: str                      # the category path, parts separated by "/": "Diagnostics / PHP"
    kind: str                       # choice | int | bool | text | color | pairs
    default: str
    choices: Tuple[str, ...] = ()
    section: str = "*"              # the EditorConfig section the value is written to

    @property
    def category(self) -> Tuple[str, ...]:
        return tuple(part.strip() for part in self.group.split(CATEGORY_SEPARATOR) if part.strip())


SCHEMA: Tuple[Setting, ...] = (
    Setting("indent_style", "Indent style", "Editor / Indentation", "choice", "space", ("space", "tab")),
    Setting("indent_size", "Indent size", "Editor / Indentation", "int", "4"),
    Setting("tab_width", "Tab width", "Editor / Indentation", "int", "4"),
    Setting("end_of_line", "Line endings", "Editor / Files", "choice", "lf", ("lf", "crlf", "cr")),
    Setting("charset", "Charset", "Editor / Files", "choice", "utf-8", ("utf-8", "utf-8-bom", "latin1")),
    Setting("trim_trailing_whitespace", "Trim trailing whitespace", "Editor / Files", "bool", "false"),
    Setting("insert_final_newline", "Final newline", "Editor / Files", "bool", "true"),
    Setting("ogmkdev_autosave", "Autosave while typing (--autosave starts it on)", "Editor / Behaviour", "choice",
            "off", ("on", "off")),
    Setting("ogmkdev_appearance", "Light or dark colours (the --mode option of the start overrides it)",
            "Colors / Appearance", "choice", "light", ("light", "dark")),
    Setting("ogmkdev_syntax_highlight", "Syntax highlighting", "Colors / Syntax", "choice", "on", ("on", "off")),
    Setting("ogmkdev_current_line", "Highlight the current line", "Colors / Syntax", "bool", "true"),
    Setting("ogmkdev_change_marks", "Change marks in the gutter (since the last save)", "Colors / Changes", "choice",
            "on", ("on", "off")),
    Setting("ogmkdev_change_color_added", "Colour of added lines", "Colors / Changes", "color", "#3FB950"),
    Setting("ogmkdev_change_color_modified", "Colour of modified lines", "Colors / Changes", "color", "#58A6FF"),
    Setting("ogmkdev_change_color_deleted", "Colour of deleted lines", "Colors / Changes", "color", "#F85149"),
    Setting("ogmkdev_git_colors", "Git status colours in the tree and the Git panel", "Colors / Git", "choice", "on",
            ("on", "off")),
    Setting("ogmkdev_dialect", "PHP version", "Languages / PHP", "choice", "8.6", PHP_VERSIONS, section="*.php"),
    Setting("ogmkdev_markup_inspection", "XML and HTML inspection: structure, selectors, id and file references "
            "(never in PHP files)", "Languages / Markup", "choice", "on", ("on", "off")),
    Setting("ogmkdev_source_roots", "Source folders (comma separated; empty: src, source, app, lib, include)",
            "Workspace / Folders", "text", ""),
    Setting("ogmkdev_test_roots", "Test folders (comma separated)", "Workspace / Folders", "text", "tests,test,spec"),
    Setting("ogmkdev_build_roots", "Build folders (coloured as build)", "Workspace / Folders", "text",
            "build,dist,out,target,bin,obj"),
    Setting("ogmkdev_artifact_roots", "Artifact folders (coloured as artifacts)", "Workspace / Folders", "text",
            "artifacts,coverage,reports,logs"),
    Setting("ogmkdev_asset_roots", "Asset folders (coloured as assets)", "Workspace / Folders", "text",
            "assets,static,public,resources,images,fonts"),
    Setting("ogmkdev_exclude", "Ignored folders (not in the tree, not indexed, not searched)", "Workspace / Ignored",
            "text", ".git,node_modules,__pycache__,vendor,.idea,*.iml"),
    Setting("ogmkdev_diagnostics", "Error hinting", "Diagnostics / Problems", "choice", "on", ("on", "off")),
    Setting("ogmkdev_diagnostic_marks", "Underline problems in the editor (message as tooltip)",
            "Diagnostics / Problems", "choice", "on", ("on", "off")),
    Setting("ogmkdev_diagnostic_php_function", "PHP library functions newer than the version", "Diagnostics / PHP",
            "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_php_partial_application", "PHP 8.6 placeholders on older versions",
            "Diagnostics / PHP", "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_heredoc_unterminated", "Unterminated heredoc", "Diagnostics / Code",
            "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_js_syntax", "ECMAScript syntax errors", "Diagnostics / Code", "choice", "error",
            SEVERITIES),
    Setting("ogmkdev_diagnostic_baredown_fence", "Unclosed BareDown code block", "Diagnostics / Code",
            "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_sql_not_supported", "ENGINE on a dialect without it", "Diagnostics / Code",
            "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_json_syntax", "JSON syntax errors", "Diagnostics / Data and markup", "choice",
            "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_xml_syntax", "XML and SVG well-formedness", "Diagnostics / Data and markup",
            "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_duplicate_id", "Duplicate id values in XML, SVG and HTML",
            "Diagnostics / Data and markup", "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_css_braces", "Unbalanced braces in CSS, SCSS and LESS",
            "Diagnostics / Data and markup", "choice", "error", SEVERITIES),
    Setting("ogmkdev_diagnostic_trailing_whitespace", "Trailing spaces and tabs (trim_trailing_whitespace)",
            "Diagnostics / Style", "choice", "hint", SEVERITIES),
    Setting("ogmkdev_diagnostic_indent_style", "Indentation against indent_style, or tabs mixed with spaces",
            "Diagnostics / Style", "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_line_length", "Lines longer than max_line_length", "Diagnostics / Style",
            "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_line_endings", "Line endings against end_of_line, or mixed endings",
            "Diagnostics / Style", "choice", "warning", SEVERITIES),
    Setting("ogmkdev_diagnostic_final_newline", "No newline at the end of the file (insert_final_newline)",
            "Diagnostics / Style", "choice", "hint", SEVERITIES),
    Setting("ogmkdev_todo_keywords", "TODO keywords in comments with priorities (FIXME:1,TODO:3)", "TODO", "pairs",
            "FIXME:1,XXX:2,HACK:2,TODO:3,NOTE:5"),
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


def appearance_mode(store: SettingsStore) -> str:
    """The light or dark colours of the global setting; the default when the file holds another text."""
    setting = SETTINGS_BY_KEY["ogmkdev_appearance"]
    value = store.value(setting.key)
    return value if value in setting.choices else setting.default


def groups(schema: Sequence[Setting] = SCHEMA):
    """Settings grouped by their group path, in schema order."""
    result: Dict[str, list] = {}
    for setting in schema:
        result.setdefault(setting.group, []).append(setting)
    return list(result.items())


def in_category(setting: Setting, path: str) -> bool:
    """Whether the setting lies in the category ``path`` ("Diagnostics", or "Diagnostics / PHP") or below it."""
    wanted = tuple(part.strip() for part in path.split(CATEGORY_SEPARATOR) if part.strip())
    return setting.category[:len(wanted)] == wanted


def category_tree(schema: Sequence[Setting] = SCHEMA) -> List[Dict[str, Any]]:
    """The categories as a tree of nodes: each node has its name, its path, its child nodes and the settings that
    sit directly in it. The depth is not limited."""
    root: Dict[str, Any] = {"children": {}, "settings": []}
    for setting in schema:
        node = root
        path: List[str] = []
        for part in setting.category:
            path.append(part)
            node = node["children"].setdefault(part, {"name": part, "path": " / ".join(path), "children": {},
                                                      "settings": []})
        node["settings"].append(setting)

    def convert(children: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"name": node["name"], "path": node["path"], "settings": node["settings"],
                 "children": convert(node["children"])} for node in children.values()]

    return convert(root["children"])


def search(query: str, schema: Sequence[Setting] = SCHEMA) -> List[Setting]:
    """The settings whose label, key, category and choices contain every word of the query (ignoring case).
    An empty query finds every setting."""
    words = query.lower().split()
    if not words:
        return list(schema)
    found = []
    for setting in schema:
        text = " ".join([setting.label, setting.key, setting.group, " ".join(setting.choices)]).lower()
        if all(word in text for word in words):
            found.append(setting)
    return found


Value = Union[bool, int, str, Pairs]


def default_value(setting: Setting) -> Value:
    """The default of a setting as its typed value."""
    if setting.kind == "bool":
        return setting.default.strip().lower() == "true"
    if setting.kind == "int":
        return int(setting.default)
    if setting.kind == "pairs":
        parsed = parse_pairs(setting.key, setting.default)
        return parsed if not isinstance(parsed, Failure) else []
    return setting.default


def parse_pairs(key: str, text: str) -> Union[Pairs, Failure]:
    """The keyword and priority pairs of a text such as "FIXME:1,TODO:3", or the reason it is not one. An empty text
    holds no pairs."""
    pairs: Pairs = []
    for item in text.split(","):
        entry = item.strip()
        if not entry:
            continue
        keyword, separator, priority = entry.partition(":")
        keyword = keyword.strip()
        priority = priority.strip()
        if separator != ":" or KEYWORD_PATTERN.fullmatch(keyword) is None or not priority.isdigit():
            return failed(f"{key}: expected KEYWORD:PRIORITY pairs such as TODO:3, got {entry!r}")
        pairs.append((keyword, int(priority)))
    return pairs


def pairs_text(pairs: Pairs) -> str:
    """The pairs as the EditorConfig file keeps them: "FIXME:1,TODO:3"."""
    return ",".join(f"{keyword}:{priority}" for keyword, priority in pairs)


def parse_value(setting: Setting, text: str) -> Union[Value, Failure]:
    """The typed value of a text for the setting, or the reason it is not one. Nothing is raised for a bad text."""
    if setting.kind == "bool":
        lowered = text.strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        return failed(f"{setting.key}: expected true or false, got {text!r}")
    if setting.kind == "int":
        try:
            return int(text)
        except ValueError:
            return failed(f"{setting.key}: expected a whole number, got {text!r}")
    if setting.kind == "color":
        colour = text.strip().upper()
        if COLOUR_PATTERN.fullmatch(colour) is not None:
            return colour
        return failed(f"{setting.key}: expected a colour such as #3FB950, got {text!r}")
    if setting.kind == "pairs":
        return parse_pairs(setting.key, text)
    return text


def typed_value(setting: Setting, text: str) -> Value:
    """The typed value of a text; the default when the text is not a valid value (the lenient reading of a file)."""
    parsed = parse_value(setting, text)
    if isinstance(parsed, Failure):
        return default_value(setting)
    return parsed


def text_value(setting: Setting, value: Value) -> str:
    """The text the EditorConfig file keeps for a value of the setting (the inverse of parse_value)."""
    if setting.kind == "bool" and isinstance(value, bool):
        return "true" if value else "false"
    if setting.kind == "int" and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if setting.kind == "pairs" and isinstance(value, list):
        return pairs_text(value)
    if isinstance(value, str):
        return value
    return setting.default  # a value of another type than its setting: the default stands in for it


def provider_for(setting: Setting, text: str) -> SettingProvider:
    """The OtherSettings provider of a setting, holding the value the text has."""
    value = typed_value(setting, text)
    if setting.kind == "bool" and isinstance(value, bool):
        return BooleanCheckboxProvider(value)
    if setting.kind == "int" and isinstance(value, int) and not isinstance(value, bool):
        return NumberInputProvider(value)
    if setting.kind == "color" and isinstance(value, str):
        return ColorPickerProvider(value)
    if setting.kind == "pairs" and isinstance(value, list):
        return PairsProvider(value)
    if setting.kind == "choice" and isinstance(value, str):
        return SettingProvider(value, SettingsTyp.SELECT)
    if isinstance(value, str):
        return StringLineProvider(value)
    return StringLineProvider(setting.default)


def build_model(values: Dict[str, str], schema: Sequence[Setting] = SCHEMA) -> PreStoredSettings:
    """The settings dialog's model: a provider for every setting, holding the value in ``values`` or the default."""
    return PreStoredSettings({setting.key: provider_for(setting, values.get(setting.key, setting.default))
                              for setting in schema})


def set_model_text(model: PreStoredSettings, setting: Setting, text: str) -> Union[Value, Failure]:
    """Puts a text into the model under the setting's type. A text that is not a valid value leaves the model as it
    is, and the reason is returned."""
    parsed = parse_value(setting, text)
    if isinstance(parsed, Failure):
        return parsed
    if setting.kind == "bool" and isinstance(parsed, bool):
        model.set_boolean(setting.key, parsed)
        return parsed
    if setting.kind == "int" and isinstance(parsed, int) and not isinstance(parsed, bool):
        model.set_number(setting.key, parsed)
        return parsed
    if setting.kind == "color" and isinstance(parsed, str):
        stored = model.set_color(setting.key, parsed)
        return stored if isinstance(stored, Failure) else parsed
    if setting.kind == "pairs" and isinstance(parsed, list):
        stored_pairs = model.set_pairs(setting.key, parsed)
        return stored_pairs if isinstance(stored_pairs, Failure) else parsed
    if setting.kind in ("choice", "text") and isinstance(parsed, str):
        model.set_string(setting.key, parsed)
        return parsed
    return failed(f"{setting.key}: the value does not fit the setting")


def model_text(model: PreStoredSettings, setting: Setting) -> str:
    """The text of a setting as the model holds it; the default text when the model holds no value for it."""
    value = model.get(setting.key)
    if isinstance(value, Failure):
        return setting.default
    return text_value(setting, value)


def model_values(model: PreStoredSettings, schema: Sequence[Setting] = SCHEMA) -> Dict[str, str]:
    """The text of every setting of the model, keyed by setting key (what the store writes)."""
    return {setting.key: model_text(model, setting) for setting in schema}
