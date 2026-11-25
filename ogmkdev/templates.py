"""Variable-based templates: the only source of auto-completion proposals.

A template has a trigger word, a body and named variables::

    ${name}            variable with no default (required; left as-is when not supplied)
    ${name:default}    variable with a default
    $0                 final cursor position

Completion filters templates by their trigger prefix and language. Nothing is inferred
from the code, which keeps the completion engine small and predictable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}|\$0")


@dataclass(frozen=True)
class Template:
    trigger: str
    language: str
    body: str
    description: str = ""
    dialect: Optional[str] = None      # restricts the template to one dialect when set
    variables: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Expansion:
    text: str
    cursor: int                        # offset of $0 (or the end of the text)


def variable_names(body: str) -> List[str]:
    names: List[str] = []
    for match in _VARIABLE.finditer(body):
        if match.group(1) and match.group(1) not in names:
            names.append(match.group(1))
    return names


def expand(template: Template, values: Optional[Mapping[str, str]] = None) -> Expansion:
    """Replace variables; ``values`` override template defaults; ``$0`` marks the cursor."""
    values = dict(values or {})
    defaults = dict(template.variables)
    cursor: Optional[int] = None
    pieces: List[str] = []
    last = 0
    for match in _VARIABLE.finditer(template.body):
        pieces.append(template.body[last:match.start()])
        last = match.end()
        if match.group(0) == "$0":
            cursor = sum(len(p) for p in pieces)
            continue
        name, inline_default = match.group(1), match.group(2)
        if name in values:
            text = values[name]
        elif name in defaults:
            text = defaults[name]
        elif inline_default is not None:
            text = inline_default
        else:
            text = match.group(0)
        pieces.append(text)
    pieces.append(template.body[last:])
    text = "".join(pieces)
    if cursor is None:
        cursor = len(text)
    return Expansion(text, cursor)


@dataclass
class TemplateRegistry:
    templates: List[Template] = field(default_factory=list)

    def add(self, template: Template) -> None:
        self.templates.append(template)

    def complete(self, prefix: str, language: str, dialect: Optional[str] = None) -> List[Template]:
        matches = []
        for template in self.templates:
            if template.language != language:
                continue
            if template.dialect and template.dialect != dialect:
                continue
            if template.trigger.startswith(prefix):
                matches.append(template)
        return sorted(matches, key=lambda t: (len(t.trigger), t.trigger))


BUILTIN_TEMPLATES: Tuple[Template, ...] = (
    Template("foreach", "php",
             "foreach (${collection:items} as ${key:key} => ${value:value}) {\n    $0\n}",
             "foreach over an array with key"),
    Template("fn", "php",
             "fn(${args:x}) => $0;", "arrow function (PHP 7.4+)"),
    Template("for", "python",
             "for ${item:item} in ${collection:items}:\n    $0", "for loop"),
    Template("def", "python",
             "def ${name:function}(${args:self}):\n    $0", "function definition"),
    Template("forof", "typescript",
             "for (const ${item:item} of ${collection:items}) {\n    $0\n}", "for...of loop"),
    Template("fc", "tsx",
             "const ${name:Component}: React.FC = () => {\n    return (\n        <div>$0</div>\n    );\n};",
             "function component"),
    Template("select", "sql",
             "SELECT ${columns:*}\nFROM ${table:table_name}\nWHERE $0;", "select statement"),
    Template("createtable", "sql",
             "CREATE TABLE ${table:table_name} (\n    id INT NOT NULL,\n    $0\n) ENGINE=${engine:InnoDB};",
             "create table with storage engine", "mysql"),
    Template("createtable", "sql",
             "CREATE TABLE ${table:table_name} (\n    id INT NOT NULL,\n    $0\n) ENGINE=${engine:InnoDB};",
             "create table with storage engine", "mariadb"),
    Template("section", "mustache",
             "{{#${name:items}}}\n    {{${field:name}}}$0\n{{/${name:items}}}", "Mustache section"),
    Template("for", "twig",
             "{% for ${item:item} in ${collection:items} %}\n    $0\n{% endfor %}", "Twig for loop"),
)


def builtin_registry() -> TemplateRegistry:
    return TemplateRegistry(list(BUILTIN_TEMPLATES))
