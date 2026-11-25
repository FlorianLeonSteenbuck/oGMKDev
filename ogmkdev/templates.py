"""Variable-based templates for completion: built in for every language, or configured in EditorConfig.

Body syntax:

    ${name}            variable without a default (stays visible when no value is given)
    ${name:default}    variable with a default
    $0                 cursor position after the expansion
    anything else      literal text (so PHP's $variable needs no escaping)

Configuration: a template is an EditorConfig property ``ogmkdev_template_<trigger>``. Its value
may use the escapes ``\\n``, ``\\t`` and ``\\\\``. Sections select the files: ``[*.php]``,
``[legacy/**]`` or ``[**/templates/**]`` scope templates to a language or a directory. A
configured template applies to every file its section matches and replaces a built-in template
with the same trigger, so a project can change any template without a second configuration format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .editorconfig import TEMPLATE_KEY_PREFIX

ANY_LANGUAGE = "*"
TRIGGER = re.compile(r"^[a-z0-9_-]+$")
_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}|\$0")
_ESCAPE = re.compile(r"\\(.)")
_UNESCAPE = {"n": "\n", "t": "\t", "\\": "\\"}

# Languages whose templates also serve another language (family members and template layers).
FAMILY: Dict[str, Tuple[str, ...]] = {
    "pypy": ("pypy", "python"),
    "tsx": ("tsx", "typescript"),
    "jsx": ("jsx", "ecmascript"),
    "mustache": ("mustache", "html"),
    "twig": ("twig", "html"),
}


@dataclass(frozen=True)
class Template:
    trigger: str
    language: str
    body: str
    description: str = ""
    dialect: Optional[str] = None
    variables: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Expansion:
    text: str
    cursor: int


def unescape(value: str) -> str:
    return _ESCAPE.sub(lambda m: _UNESCAPE.get(m.group(1), "\\" + m.group(1)), value)


def variable_names(body: str) -> List[str]:
    names: List[str] = []
    for match in _VARIABLE.finditer(body):
        if match.group(1) and match.group(1) not in names:
            names.append(match.group(1))
    return names


def expand(template: Template, values: Optional[Mapping[str, str]] = None) -> Expansion:
    """Replace variables (``values`` override defaults) and locate ``$0``."""
    values = dict(values or {})
    defaults = dict(template.variables)
    cursor: Optional[int] = None
    pieces: List[str] = []
    last = 0
    for match in _VARIABLE.finditer(template.body):
        pieces.append(template.body[last:match.start()])
        last = match.end()
        if match.group(0) == "$0":
            cursor = sum(len(piece) for piece in pieces)
            continue
        name, inline_default = match.group(1), match.group(2)
        if name in values:
            pieces.append(values[name])
        elif name in defaults:
            pieces.append(defaults[name])
        elif inline_default is not None:
            pieces.append(inline_default)
        else:
            pieces.append(match.group(0))
    pieces.append(template.body[last:])
    text = "".join(pieces)
    return Expansion(text, len(text) if cursor is None else cursor)


def from_config(custom: Mapping[str, str]) -> List[Template]:
    """Templates defined by ``ogmkdev_template_<trigger>`` keys in the file's EditorConfig."""
    result: List[Template] = []
    for key, value in custom.items():
        if not key.startswith(TEMPLATE_KEY_PREFIX):
            continue
        trigger = key[len(TEMPLATE_KEY_PREFIX):]
        if TRIGGER.match(trigger):
            result.append(Template(trigger, ANY_LANGUAGE, unescape(value), "defined in .editorconfig"))
    return result


@dataclass
class TemplateRegistry:
    templates: List[Template] = field(default_factory=list)

    def add(self, template: Template) -> None:
        self.templates.append(template)

    def complete(self, prefix: str, language: Optional[str] = None,
                 dialect: Optional[str] = None) -> List[Template]:
        """Templates whose trigger starts with ``prefix``. Without a language, all are considered."""
        matches = []
        for template in self.templates:
            if language is not None and template.language not in (language, ANY_LANGUAGE):
                continue
            if template.dialect and dialect is not None and template.dialect != dialect:
                continue
            if template.trigger.startswith(prefix):
                matches.append(template)
        return sorted(matches, key=lambda t: (len(t.trigger), t.trigger))


def languages_for(language: str, template: Optional[str] = None) -> Tuple[str, ...]:
    names: List[str] = []
    for name in (template, language):
        if name:
            for member in FAMILY.get(name, (name,)):
                if member not in names:
                    names.append(member)
    return tuple(names)


def registry_for(language: str, dialect: Optional[str], custom: Mapping[str, str],
                 template: Optional[str] = None) -> TemplateRegistry:
    """Every template that applies to a file: built-in for its language and dialect, then configured."""
    names = languages_for(language, template)
    chosen: Dict[str, Template] = {}
    # generic templates first, so that dialect-specific ones replace them
    for item in sorted(BUILTIN_TEMPLATES, key=lambda t: t.dialect is not None):
        if item.language in names and (item.dialect is None or item.dialect == dialect):
            chosen[item.trigger] = item
    for item in from_config(custom):
        chosen[item.trigger] = item
    return TemplateRegistry(list(chosen.values()))


def howl_rows(registry: TemplateRegistry) -> str:
    """The templates for the Howl editor (howl/lib/howl/editing/templates.moon): one row per template,
    "trigger<TAB>body", the body with its backslashes, line breaks and tabs escaped as in EditorConfig values.
    The templates keep no variables of their own: their defaults are in the bodies."""
    rows = []
    for template in registry.templates:
        if template.variables:
            raise ValueError(f"template {template.trigger!r} has variables, which the Howl editor does not take")
        body = template.body.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")
        rows.append(f"{template.trigger}\t{body}")
    return "\n".join(rows)


def builtin_registry() -> TemplateRegistry:
    return TemplateRegistry(list(BUILTIN_TEMPLATES))


def _t(trigger: str, language: str, description: str, body: str, dialect: Optional[str] = None) -> Template:
    return Template(trigger, language, body, description, dialect)


BUILTIN_TEMPLATES: Tuple[Template, ...] = (
    # PHP
    _t("foreach", "php", "foreach over an array with key",
       "foreach (${collection:$items} as ${key:key} => ${value:value}) {\n    $0\n}"),
    _t("fn", "php", "arrow function (PHP 7.4+)", "fn(${args:x}) => $0;"),
    _t("if", "php", "if block", "if (${condition:true}) {\n    $0\n}"),
    _t("ifelse", "php", "if / else block", "if (${condition:true}) {\n    $0\n} else {\n    \n}"),
    _t("while", "php", "while loop", "while (${condition:true}) {\n    $0\n}"),
    _t("try", "php", "try / catch", "try {\n    $0\n} catch (${exception:Exception} $${name:e}) {\n}"),
    _t("function", "php", "function definition", "function ${name:name}(${args:}) {\n    $0\n}"),
    _t("class", "php", "class with constructor",
       "class ${name:Name} {\n    public function __construct(${args:}) {\n        $0\n    }\n}"),
    _t("heredoc", "php", "heredoc string",
       "$${variable:text} = <<<${label:HEREDOC}\n$0\n${label:HEREDOC};"),
    # Python 2 and 3, PyPy
    _t("for", "python", "for loop", "for ${item:item} in ${collection:items}:\n    $0"),
    _t("def", "python", "function definition", "def ${name:function}(${args:self}):\n    $0"),
    _t("class", "python", "class definition", "class ${name:Name}:\n    def __init__(self):\n        $0"),
    _t("with", "python", "with statement", "with ${expr:open('file')} as ${name:f}:\n    $0"),
    _t("try", "python", "try / except", "try:\n    $0\nexcept ${exception:Exception} as ${name:e}:\n    pass"),
    _t("ifmain", "python", "script entry point", "if __name__ == '__main__':\n    $0"),
    _t("comp", "python", "list comprehension", "[${expr:item} for ${item:item} in ${collection:items}]"),
    # ECMAScript (KDevelop grammar: ES5 plus QML words)
    _t("for", "ecmascript", "for loop",
       "for (var ${index:i} = 0; ${index:i} < ${length:n}; ${index:i}++) {\n    $0\n}"),
    _t("forin", "ecmascript", "for-in loop", "for (var ${key:key} in ${object:obj}) {\n    $0\n}"),
    _t("function", "ecmascript", "function declaration", "function ${name:name}(${args:}) {\n    $0\n}"),
    _t("if", "ecmascript", "if block", "if (${condition:true}) {\n    $0\n}"),
    _t("try", "ecmascript", "try / catch", "try {\n    $0\n} catch (${error:e}) {\n}"),
    _t("switch", "ecmascript", "switch statement",
       "switch (${value:value}) {\n    case ${case:0}:\n        $0\n        break;\n    default:\n}"),
    _t("obj", "ecmascript", "object literal", "var ${name:obj} = {\n    $0\n};"),
    _t("log", "ecmascript", "console.log", "console.log(${value:value});$0"),
    # TypeScript and TSX
    _t("forof", "typescript", "for...of loop", "for (const ${item:item} of ${collection:items}) {\n    $0\n}"),
    _t("interface", "typescript", "interface", "interface ${name:Name} {\n    $0\n}"),
    _t("type", "typescript", "type alias", "type ${name:Name} = $0;"),
    _t("class", "typescript", "class with constructor",
       "class ${name:Name} {\n    constructor(${args:}) {\n        $0\n    }\n}"),
    _t("fn", "typescript", "typed function",
       "function ${name:name}(${args:arg: string}): ${returns:void} {\n    $0\n}"),
    _t("enum", "typescript", "enum", "enum ${name:Name} {\n    $0\n}"),
    _t("fc", "tsx", "function component",
       "const ${name:Component}: React.FC = () => {\n    return (\n        <div>$0</div>\n    );\n};"),
    _t("state", "tsx", "useState hook", "const [${value:value}, set${Value:Value}] = React.useState(${initial:null});"),
    _t("fc", "jsx", "function component",
       "function ${name:Component}() {\n    return (\n        <div>$0</div>\n    );\n}"),
    # SQL, generic and per dialect
    _t("select", "sql", "select statement", "SELECT ${columns:*}\nFROM ${table:table_name}\nWHERE $0;"),
    _t("join", "sql", "select with inner join",
       "SELECT ${columns:*}\nFROM ${table:table_name} AS ${alias:t}\nINNER JOIN ${other:other_table} AS ${alias2:o} ON $0;"),
    _t("insert", "sql", "insert statement", "INSERT INTO ${table:table_name} (${columns:column})\nVALUES (${values:value});"),
    _t("update", "sql", "update statement", "UPDATE ${table:table_name}\nSET ${column:column} = ${value:value}\nWHERE $0;"),
    _t("delete", "sql", "delete statement", "DELETE FROM ${table:table_name}\nWHERE $0;"),
    _t("with", "sql", "common table expression", "WITH ${name:cte} AS (\n    $0\n)\nSELECT * FROM ${name:cte};"),
    _t("createtable", "sql", "create table",
       "CREATE TABLE ${table:table_name} (\n    id INT NOT NULL,\n    $0\n);"),
    _t("createindex", "sql", "create index", "CREATE INDEX ${name:idx_name} ON ${table:table_name} (${column:column});"),
    _t("createtable", "sql", "create table with ENGINE and charset",
       "CREATE TABLE ${table:table_name} (\n    id INT NOT NULL AUTO_INCREMENT,\n    $0\n    PRIMARY KEY (id)\n) ENGINE=${engine:InnoDB} DEFAULT CHARSET=${charset:utf8mb4};", "mysql"),
    _t("createtable", "sql", "create table with ENGINE and charset",
       "CREATE TABLE ${table:table_name} (\n    id INT NOT NULL AUTO_INCREMENT,\n    $0\n    PRIMARY KEY (id)\n) ENGINE=${engine:InnoDB} DEFAULT CHARSET=${charset:utf8mb4};", "mariadb"),
    _t("createtable", "sql", "create table with identity column",
       "CREATE TABLE ${table:table_name} (\n    id INT IDENTITY(1,1) PRIMARY KEY,\n    $0\n);", "mssql"),
    _t("createtable", "sql", "create table with serial column",
       "CREATE TABLE ${table:table_name} (\n    id SERIAL PRIMARY KEY,\n    $0\n);", "postgresql"),
    _t("createtable", "sql", "create table with identity column",
       "CREATE TABLE ${table:table_name} (\n    id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,\n    $0\n);", "oracle"),
    _t("createtable", "sql", "create table stored as a Hive format",
       "CREATE TABLE ${table:table_name} (\n    $0\n)\nSTORED AS ${format:PARQUET};", "apache-hive"),
    # Markdown
    _t("link", "markdown", "inline link", "[${text:text}](${url:https://})"),
    _t("image", "markdown", "image", "![${alt:alt}](${url:image.png})"),
    _t("code", "markdown", "fenced code block", "```${language:}\n$0\n```"),
    _t("table", "markdown", "table", "| ${a:column} | ${b:column} |\n| --- | --- |\n| $0 |  |"),
    _t("todo", "markdown", "task list item", "- [ ] $0"),
    # BareDown
    _t("heading", "baredown", "heading", "= ${title:Title}\n$0"),
    _t("link", "baredown", "link to a page", "[[${target:Page}|${label:label}]]"),
    _t("code", "baredown", "fenced code block", "~~~ ${language:python}\n$0\n~~~"),
    _t("bullet", "baredown", "bullet item", "- $0"),
    _t("ordered", "baredown", "ordered item", "+ $0"),
    _t("quote", "baredown", "block quote", "> $0"),
    _t("note", "baredown", "comment line", "%% $0"),
    _t("rule", "baredown", "horizontal rule", "----"),
    # HTML
    _t("html5", "html", "HTML5 document",
       '<!DOCTYPE html>\n<html lang="${lang:en}">\n<head>\n    <meta charset="utf-8">\n'
       "    <title>${title:Title}</title>\n</head>\n<body>\n    $0\n</body>\n</html>"),
    _t("div", "html", "div element", '<div class="${class:name}">$0</div>'),
    _t("a", "html", "anchor", '<a href="${url:#}">$0</a>'),
    _t("img", "html", "image", '<img src="${src:image.png}" alt="${alt:alt}">'),
    _t("ul", "html", "unordered list", "<ul>\n    <li>$0</li>\n</ul>"),
    # JSON
    _t("obj", "json", "object", '{\n    "${key:key}": $0\n}'),
    _t("arr", "json", "array", "[\n    $0\n]"),
    # CSS
    _t("rule", "css", "style rule", "${selector:selector} {\n    $0\n}"),
    _t("media", "css", "media query", "@media (${feature:max-width}: ${value:600px}) {\n    $0\n}"),
    _t("flex", "css", "flex container",
       "display: flex;\njustify-content: ${justify:center};\nalign-items: ${align:center};$0"),
    # Mustache (template layer over the base language)
    _t("section", "mustache", "section", "{{#${name:items}}}\n    {{${field:name}}}$0\n{{/${name:items}}}"),
    _t("inverted", "mustache", "inverted section", "{{^${name:items}}}\n    $0\n{{/${name:items}}}"),
    _t("partial", "mustache", "partial", "{{> ${name:partial}}}"),
    _t("var", "mustache", "variable", "{{${name:name}}}$0"),
    # Twig (template layer over the base language)
    _t("for", "twig", "for loop", "{% for ${item:item} in ${collection:items} %}\n    $0\n{% endfor %}"),
    _t("if", "twig", "if block", "{% if ${condition:cond} %}\n    $0\n{% endif %}"),
    _t("rule", "scss", "style rule", "${selector:selector} {\n    $0\n}"),
    _t("media", "scss", "media query", "@media (${feature:max-width}: ${value:600px}) {\n    $0\n}"),
    _t("mixin", "scss", "mixin", "@mixin ${name:name}(${args}) {\n    $0\n}"),
    _t("include", "scss", "include a mixin", "@include ${name:name}($0);"),
    _t("rule", "less", "style rule", "${selector:selector} {\n    $0\n}"),
    _t("media", "less", "media query", "@media (${feature:max-width}: ${value:600px}) {\n    $0\n}"),
    _t("mixin", "less", "mixin", ".${name:name}(${args}) {\n    $0\n}"),
    _t("rule", "sass", "style rule", "${selector:selector}\n  $0"),
    _t("media", "sass", "media query", "@media (${feature:max-width}: ${value:600px})\n  $0"),
    _t("mixin", "sass", "mixin", "=${name:name}(${args})\n  $0"),
    _t("include", "sass", "include a mixin", "+${name:name}($0)"),
    _t("xml", "xml", "XML declaration", '<?xml version="1.0" encoding="UTF-8"?>'),
    _t("elem", "xml", "element", "<${name:element}>\n    $0\n</${name:element}>"),
    _t("comment", "xml", "comment", "<!-- $0 -->"),
    _t("svg", "svg", "SVG document",
       '<svg xmlns="http://www.w3.org/2000/svg" width="${width:64}" height="${height:64}"'
       ' viewBox="0 0 ${width:64} ${height:64}">\n    $0\n</svg>'),
    _t("rect", "svg", "rectangle",
       '<rect id="${id:shape}" x="${x:0}" y="${y:0}" width="${width:10}" height="${height:10}"/>'),
    _t("use", "svg", "reference to an element by id", '<use xlink:href="#${id:shape}"/>'),
    _t("schema", "xsd", "XML schema document",
       '<?xml version="1.0" encoding="UTF-8"?>\n<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"'
       ' elementFormDefault="qualified">\n    $0\n</xs:schema>'),
    _t("element", "xsd", "element declaration", '<xs:element name="${name:element}" type="xs:${type:string}"/>'),
    _t("complex", "xsd", "complex type",
       '<xs:complexType name="${name:type}">\n    <xs:sequence>\n        $0\n    </xs:sequence>\n</xs:complexType>'),
    _t("simple", "xsd", "simple type",
       '<xs:simpleType name="${name:type}">\n    <xs:restriction base="xs:${base:string}">\n        $0\n'
       '    </xs:restriction>\n</xs:simpleType>'),
    _t("attr", "xsd", "attribute declaration",
       '<xs:attribute name="${name:attribute}" type="xs:${type:string}" use="optional"/>'),
    _t("import", "xsd", "import another schema",
       '<xs:import namespace="urn:${namespace:example}" schemaLocation="${location:other.xsd}"/>'),
    _t("stylesheet", "xslt", "XSLT stylesheet",
       '<?xml version="1.0" encoding="UTF-8"?>\n<xsl:stylesheet version="1.0"'
       ' xmlns:xsl="http://www.w3.org/1999/XSL/Transform">\n    <xsl:output method="xml" indent="yes"/>\n'
       '    $0\n</xsl:stylesheet>'),
    _t("template", "xslt", "template for a node", '<xsl:template match="${match:/}">\n    $0\n</xsl:template>'),
    _t("named", "xslt", "named template",
       '<xsl:template name="${name:name}">\n    $0\n</xsl:template>'),
    _t("call", "xslt", "call a named template", '<xsl:call-template name="${name:name}"/>'),
    _t("foreach", "xslt", "for each node",
       '<xsl:for-each select="${select:item}">\n    $0\n</xsl:for-each>'),
    _t("value", "xslt", "value of an expression", '<xsl:value-of select="${select:.}"/>'),
    _t("import", "xslt", "import a stylesheet", '<xsl:import href="${href:common.xsl}"/>'),
    _t("include", "xslt", "include a stylesheet", '<xsl:include href="${href:common.xsl}"/>'),
    _t("rfcp", "tsx", "React function component with props and a CSS module",
       "import styles from './${name:Component}.module.css';\n\n"
       "interface ${name:Component}Props {\n  title?: string;\n}\n\n"
       "export function ${name:Component}({ title = '${name:Component}' }: ${name:Component}Props) {\n"
       "  return (\n    <section className={styles.root}>\n      <h2>{title}</h2>\n      $0\n    </section>\n  );\n}"),
    _t("sfc", "vue", "Vue single-file component with script setup",
       '<script setup lang="ts">\ndefineProps<{ title?: string }>();\n</script>\n\n<template>\n'
       '  <section class="${name:component}">\n    <h2>{{ title }}</h2>\n    $0\n  </section>\n</template>\n\n'
       '<style scoped>\n.${name:component} {\n}\n</style>'),
    _t("svelte", "svelte", "Svelte component",
       "<script lang=\"ts\">\n  export let title: string = '${name:Component}';\n</script>\n\n"
       "<section>\n  <h2>{title}</h2>\n  $0\n</section>\n\n<style>\n  section {\n  }\n</style>"),
    _t("ng", "typescript", "Angular component",
       "import { Component } from '@angular/core';\n\n@Component({\n"
       "  selector: 'app-${selector:component}',\n"
       "  templateUrl: './${selector:component}.component.html',\n"
       "  styleUrls: ['./${selector:component}.component.css']\n})\n"
       "export class ${class:Component}Component {\n  $0\n}"),
    _t("ngtpl", "html", "Angular component template", "<section>\n  $0\n</section>"),
    _t("lit", "typescript", "Lit web component",
       "import { LitElement, css, html } from 'lit';\n"
       "import { customElement, property } from 'lit/decorators.js';\n\n"
       "@customElement('${tag:my-element}')\nexport class ${class:MyElement} extends LitElement {\n"
       "  @property() title = '';\n\n  static styles = css`:host { display: block; }`;\n\n"
       "  render() {\n    return html`<h2>$0</h2>`;\n  }\n}"),
    _t("vite", "typescript", "Vite configuration",
       "import { defineConfig } from 'vite';\nimport react from '@vitejs/plugin-react';\n\n"
       "export default defineConfig({\n  plugins: [react()],\n  server: { port: ${port:5173} }\n});"),
    _t("block", "twig", "block", "{% block ${name:content} %}\n    $0\n{% endblock %}"),
    _t("extends", "twig", "extends a base template", '{% extends "${base:base.html.twig}" %}'),
    _t("include", "twig", "include a template", '{% include "${template:partial.html.twig}" %}'),
)
