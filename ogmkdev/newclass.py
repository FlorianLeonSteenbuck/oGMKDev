"""New classes: a file with the class, its namespace and its imports, for PHP, Python, TypeScript and JavaScript.

The file is named after the class; in Python the class name is the file name in PascalCase. PHP gets
the ``namespace`` and ``use`` lines; the default namespace follows the PSR-4 mapping of composer.json
when the folder lies under one, and the folder path otherwise. TypeScript and JavaScript get one
``import`` per module path, the symbol being the module's name in PascalCase; Python gets ``from ...
import`` lines for dotted names. The cursor goes into the body of the class.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, Iterable, List, Sequence, Tuple

from . import filetemplates
from .filetemplates import NewFile
from .scaffold import pascal

PHP_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")
PHP_NAME = re.compile(r"^[A-Za-z_]\w*(?:\\[A-Za-z_]\w*)*$")
PY_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")
PY_DOTTED = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
MODULE_PATH = re.compile(r"^[.\w@/-]+$")
JS_IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*$")
LANGUAGES = ("php", "py", "ts", "js")


class ClassError(ValueError):
    """A class file that cannot be created from the given name, namespace or imports."""


def _psr4_mapping(project_dir: str) -> Dict[str, str]:
    """The PSR-4 prefix → directory pairs of composer.json, prefixes without the trailing backslash."""
    try:
        with open(os.path.join(project_dir, "composer.json"), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    mapping: Dict[str, str] = {}
    for prefix, directory in (data.get("autoload", {}).get("psr-4", {}) or {}).items():
        target = directory[0] if isinstance(directory, list) and directory else directory
        if isinstance(target, str):
            mapping[prefix.rstrip("\\")] = target
    return mapping


def default_namespace(folder: str, project_dir: str) -> str:
    """The namespace of a folder: from the PSR-4 mapping when one covers it, else from its path."""
    relative = os.path.relpath(folder, project_dir).replace(os.sep, "/")
    relative = "" if relative == "." else relative
    best: Tuple[str, str] = ("", "")
    found = False
    for prefix, directory in _psr4_mapping(project_dir).items():
        base = directory.strip("/").replace("\\", "/")
        if base == "" or relative == base or relative.startswith(base + "/"):
            if not found or len(base) > len(best[1]):
                best, found = (prefix, base), True
    if found:
        prefix, base = best
        rest = relative[len(base):].strip("/") if base else relative
        parts = [part for part in rest.split("/") if part]
        return "\\".join(([prefix] if prefix else []) + [pascal(part) for part in parts])
    return "\\".join(pascal(part) for part in relative.split("/") if part)


def _php(name: str, namespace: str, imports: Sequence[str]) -> str:
    lines = ["<?php", "", "declare(strict_types=1);", ""]
    if namespace:
        lines += [f"namespace {namespace};", ""]
    if imports:
        lines += [f"use {item};" for item in imports] + [""]
    lines += [f"class {name}", "{", "    $0", "}", ""]
    return "\n".join(lines)


def _typescript(name: str, imports: Sequence[str]) -> str:
    lines = []
    for module in imports:
        symbol = pascal(module.rstrip("/").rsplit("/", 1)[-1].split(".")[0])
        lines.append(f"import {{ {symbol} }} from '{module}';")
    if lines:
        lines.append("")
    lines += [f"export class {name} {{", "  $0", "}", ""]
    return "\n".join(lines)


def _javascript(name: str, imports: Sequence[str]) -> str:
    return _typescript(name, imports)


def _python(name: str, imports: Sequence[str]) -> str:
    lines = [f'"""{name}."""', ""]
    for dotted in imports:
        package, _, symbol = dotted.rpartition(".")
        lines.append(f"from {package} import {symbol}" if package else f"import {symbol}")
    if imports:
        lines.append("")
    lines += ["", f"class {name}:", '    """A class."""', "", "    $0", ""]
    return "\n".join(lines)


def _clean_imports(imports: Iterable[str], pattern: re.Pattern, message: str) -> List[str]:
    result: List[str] = []
    for item in (part.strip() for part in imports):
        if not item:
            continue
        if not pattern.match(item):
            raise ClassError(f"{message}: {item}")
        if item not in result:
            result.append(item)
    return result


def create_class_file(folder: str, file_name: str, project_dir: str, namespace: str = "",
                      imports: Iterable[str] = ()) -> NewFile:
    """Writes the class file into folder and returns where its cursor goes.

    ``namespace`` is '' for the default of the folder, '-' for none (PHP only). Raises ClassError for an
    unsupported language or an invalid name, and ValueError for a file that exists already."""
    file_name = file_name.strip()
    if not file_name or "/" in file_name or "\\" in file_name or file_name in (".", ".."):
        raise ClassError("the file name is a name without folders")
    extension = filetemplates.extension_of(file_name)
    if extension not in LANGUAGES:
        raise ClassError("classes are created for PHP (.php), Python (.py), TypeScript (.ts) and "
                         "JavaScript (.js)")
    path = os.path.join(folder, file_name)
    if os.path.exists(path):
        raise ValueError(f"not created, {file_name} exists already")

    base = os.path.splitext(file_name)[0]
    name = base
    if extension == "py":
        name = pascal(base)
        if not PY_IDENTIFIER.match(name):
            raise ClassError(f"not a class name for Python: {name}")
        cleaned = _clean_imports(imports, PY_DOTTED, "not a dotted Python name")
        text = _python(name, cleaned)
    elif extension == "php":
        if not PHP_IDENTIFIER.match(base):
            raise ClassError(f"not a PHP class name: {base}")
        if namespace == "-":
            space = ""
        elif namespace.strip():
            space = namespace.strip().strip("\\")
            if not PHP_NAME.match(space):
                raise ClassError(f"not a PHP namespace: {space}")
        else:
            space = default_namespace(folder, project_dir)
        cleaned = _clean_imports((item.strip().lstrip("\\") for item in imports), PHP_NAME,
                                 "not a PHP name to import")
        text = _php(base, space, cleaned)
    else:
        name = base
        if not JS_IDENTIFIER.match(name):
            raise ClassError(f"not a class name: {name}")
        cleaned = _clean_imports(imports, MODULE_PATH, "not a module path")
        text = (_typescript if extension == "ts" else _javascript)(name, cleaned)

    cursor = text.index("$0")
    text = text.replace("$0", "", 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    line = text[:cursor].count("\n") + 1
    column = cursor - (text.rfind("\n", 0, cursor) + 1) + 1
    return NewFile(path, line, column, f"created class {name} in {file_name}")
