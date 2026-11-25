"""Language registry and file detection.

Detection order (first match wins):

1. EditorConfig scoping: ``ogmkdev_language`` (and optionally ``ogmkdev_dialect``)
   in any ``.editorconfig`` section that matches the file.
2. Compound extensions:
   * template layers ``<name>.mustache.<base>`` / ``<name>.twig.<base>``, where the
     base extension decides the highlighted language (``x.mustache.html`` -> HTML
     inside a Mustache template);
   * SQL dialect suffixes ``<name>.<dialect>.sql`` (``schema.mysql.sql``).
3. The last extension (``.py``, ``.tsx``, ``.phtml`` ...).
4. A shebang line (``#!/usr/bin/env pypy3``).
5. Plain text.

Languages and their dialects/versions are data, so adding one is a table entry.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

SCOPE_LANGUAGE_KEY = "ogmkdev_language"
SCOPE_DIALECT_KEY = "ogmkdev_dialect"


@dataclass(frozen=True)
class Language:
    id: str
    name: str
    extensions: Tuple[str, ...] = ()
    dialects: Tuple[str, ...] = ()
    default_dialect: Optional[str] = None
    # GtkSourceView 3 language id used for highlighting; None when GtkSourceView has none.
    gtk_source_id: Optional[str] = None


LANGUAGES: Dict[str, Language] = {
    lang.id: lang
    for lang in (
        Language("php", "PHP", ("php", "phtml", "php5"),
                 ("7.4", "8.0", "8.1", "8.2", "8.3", "8.4"), "8.4", "php"),
        # Python 2 and 3 share the grammar; the dialect selects the interpreter family.
        Language("python", "Python", ("py", "pyw", "pyi"), ("2", "3"), "3", "python3"),
        Language("pypy", "PyPy", (), ("2", "3"), "3", "python3"),
        Language("typescript", "TypeScript", ("ts", "mts", "cts"), (), None, "js"),
        Language("tsx", "TypeScript JSX", ("tsx",), (), None, "js"),
        Language("ecmascript", "ECMAScript",
                 ("js", "mjs", "cjs"),
                 ("es3", "es5", "es2015", "es2017", "es2020", "es2022", "es2024", "jscript"),
                 "es2022", "js"),
        Language("jsx", "JSX", ("jsx",), (), None, "js"),
        Language("sql", "SQL", ("sql",),
                 ("generic", "oracle", "apache-hive", "mysql", "mariadb", "mssql", "postgresql"),
                 "generic", "sql"),
        Language("markdown", "Markdown", ("md", "markdown", "mdown"), (), None, "markdown"),
        Language("html", "HTML", ("html", "htm", "xhtml"), (), None, "html"),
        Language("json", "JSON", ("json",), (), None, "json"),
        Language("css", "CSS", ("css",), (), None, "css"),
        Language("text", "Plain text", ("txt",), (), None, None),
    )
}

# Template layers: they wrap a base language; they are not standalone languages.
TEMPLATE_LAYERS: Dict[str, str] = {"mustache": "Mustache", "twig": "Twig"}

# Scope values that are shorthands for a language + dialect pair.
SCOPE_ALIASES: Dict[str, Tuple[str, Optional[str]]] = {
    "python2": ("python", "2"),
    "python3": ("python", "3"),
    "pypy2": ("pypy", "2"),
    "pypy3": ("pypy", "3"),
    "javascript": ("ecmascript", None),
    "js": ("ecmascript", None),
    "jscript": ("ecmascript", "jscript"),
    "wscript": ("ecmascript", "jscript"),
    "postgres": ("sql", "postgresql"),
    "postgresql": ("sql", "postgresql"),
    "mssql": ("sql", "mssql"),
    "tsql": ("sql", "mssql"),
    "plsql": ("sql", "oracle"),
    "hive": ("sql", "apache-hive"),
    "mysql": ("sql", "mysql"),
    "mariadb": ("sql", "mariadb"),
    "oracle": ("sql", "oracle"),
}

_SHEBANG = re.compile(r"^#!\s*(?:\S*/)?(?:env\s+(?:-\S+\s+)*)?([A-Za-z0-9_.\-]+)")


def _build_extension_map() -> Dict[str, Tuple[str, Optional[str]]]:
    mapping: Dict[str, Tuple[str, Optional[str]]] = {}
    for lang in LANGUAGES.values():
        for ext in lang.extensions:
            mapping[ext] = (lang.id, lang.default_dialect)
    return mapping


EXTENSION_MAP = _build_extension_map()
SQL_DIALECT_SUFFIXES = frozenset(LANGUAGES["sql"].dialects) - {"generic"}


@dataclass(frozen=True)
class Detection:
    language: str                 # language id used for highlighting
    dialect: Optional[str]        # dialect/version within the language
    template: Optional[str]       # 'mustache' | 'twig' | None
    source: str                   # 'editorconfig' | 'compound' | 'extension' | 'shebang' | 'default'

    @property
    def name(self) -> str:
        base = LANGUAGES[self.language].name if self.language in LANGUAGES else self.language
        if self.dialect:
            base = f"{base} {self.dialect}"
        if self.template:
            return f"{TEMPLATE_LAYERS[self.template]} ({base})"
        return base


def language_for_shebang(first_line: str) -> Optional[Tuple[str, Optional[str]]]:
    match = _SHEBANG.match(first_line.strip())
    if not match:
        return None
    interpreter = match.group(1).lower()
    if interpreter == "node":
        return ("ecmascript", "es2022")
    if interpreter.startswith("pypy"):
        return ("pypy", "2" if "2" in interpreter else "3")
    if interpreter.startswith("python"):
        return ("python", "2" if interpreter.startswith("python2") else "3")
    if interpreter.startswith("php"):
        return ("php", LANGUAGES["php"].default_dialect)
    return None


def resolve_scope(value: str, dialect: Optional[str] = None) -> Optional[Tuple[str, Optional[str]]]:
    """Turn an ``ogmkdev_language`` value (plus optional dialect) into (language, dialect)."""
    key = value.strip().lower()
    dialect = dialect.strip().lower() if dialect else None
    if key in SCOPE_ALIASES:
        language, alias_dialect = SCOPE_ALIASES[key]
        dialect = dialect or alias_dialect
    else:
        language = key
    if language not in LANGUAGES:
        return None
    spec = LANGUAGES[language]
    if dialect is None or dialect not in spec.dialects:
        dialect = spec.default_dialect
    return language, dialect


def detect(path: str, custom: Optional[Dict[str, str]] = None,
           first_line: Optional[str] = None) -> Detection:
    """Classify ``path``. ``custom`` is :attr:`EditorSettings.custom` for the file."""
    custom = custom or {}
    parts = os.path.basename(path).lower().split(".")
    template: Optional[str] = None
    language, dialect, source = "text", None, "default"

    if len(parts) >= 3 and parts[-2] in TEMPLATE_LAYERS:
        template = parts[-2]
        inner = EXTENSION_MAP.get(parts[-1])
        if inner:
            language, dialect = inner
        source = "compound"
    elif len(parts) >= 3 and parts[-1] == "sql" and parts[-2] in SQL_DIALECT_SUFFIXES:
        language, dialect, source = "sql", parts[-2], "compound"
    elif len(parts) >= 2 and parts[-1] in EXTENSION_MAP:
        language, dialect = EXTENSION_MAP[parts[-1]]
        source = "extension"
    elif first_line:
        shebang = language_for_shebang(first_line)
        if shebang:
            language, dialect = shebang
            source = "shebang"

    scope = custom.get(SCOPE_LANGUAGE_KEY)
    if scope:
        if scope.strip().lower() in TEMPLATE_LAYERS:
            template = scope.strip().lower()
        else:
            resolved = resolve_scope(scope, custom.get(SCOPE_DIALECT_KEY))
            if resolved:
                language, dialect = resolved
                source = "editorconfig"
    elif SCOPE_DIALECT_KEY in custom and language in LANGUAGES:
        wanted = custom[SCOPE_DIALECT_KEY].strip().lower()
        if wanted in LANGUAGES[language].dialects:
            dialect = wanted
            source = "editorconfig"

    return Detection(language=language, dialect=dialect, template=template, source=source)


def detect_file(path: str, custom: Optional[Dict[str, str]] = None) -> Detection:
    """Detect using the file's first line for shebang support, when it can be read."""
    first_line = None
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            first_line = handle.readline()
    except OSError:
        pass
    return detect(path, custom, first_line)
