"""File templates: the text a new file starts with, chosen by the file's extension.

The setting ``ogmkdev_filetemplate_<extension>`` names the file that holds the template, an absolute
path or one relative to the project folder. Without the setting, a built-in template is used when the
extension has one; otherwise the new file is empty. In a template ``${name}`` is the file name without
its extension, ``${Name}`` the same in PascalCase, ``${folder}`` the name of the folder the file goes
into, ``${year}`` and ``${date}`` the date, and ``$0`` marks where the cursor goes (the text keeps no
``$0``).
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from . import templates
from .scaffold import pascal

KEY_PREFIX = "ogmkdev_filetemplate_"

BUILTIN: Dict[str, str] = {
    "php": "<?php\n\ndeclare(strict_types=1);\n\n$0\n",
    "py": '"""${Name}."""\n\n\n$0\n',
    "js": "'use strict';\n\n$0\n",
    "ts": "$0\n",
    "html": ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
             "<title>${Name}</title>\n</head>\n<body>\n$0\n</body>\n</html>\n"),
    "css": "/* ${name} */\n\n$0\n",
    "md": "# ${Name}\n\n$0\n",
}


class FileTemplateError(ValueError):
    """A configured template file that cannot be read."""


def extension_of(file_name: str) -> str:
    return os.path.splitext(file_name)[1][1:].lower()


def setting_key(extension: str) -> str:
    return KEY_PREFIX + extension.lower()


def template_body(extension: str, properties: Mapping[str, str], project_dir: str) -> Optional[str]:
    """The template text for an extension: the configured file, else the built-in one, else None."""
    configured = properties.get(setting_key(extension), "").strip()
    if configured:
        path = configured if os.path.isabs(configured) else os.path.join(project_dir, configured)
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError as problem:
            raise FileTemplateError(f"file template {configured} cannot be read: {problem.strerror}") from problem
    return BUILTIN.get(extension)


def variables(file_name: str, folder_name: str, today: Optional[datetime.date] = None) -> Dict[str, str]:
    today = today or datetime.date.today()
    base = os.path.splitext(file_name)[0]
    return {"name": base, "Name": pascal(base), "folder": folder_name,
            "year": str(today.year), "date": today.isoformat()}


def new_file_text(file_name: str, properties: Mapping[str, str], project_dir: str, folder_name: str,
                  today: Optional[datetime.date] = None) -> Tuple[str, int, bool]:
    """(text, cursor, has_template) of a new file; the text is empty when no template applies."""
    body = template_body(extension_of(file_name), properties, project_dir)
    if body is None:
        return "", 0, False
    expansion = templates.expand(templates.Template(trigger="", language="", body=body),
                                 variables(file_name, folder_name, today))
    return expansion.text, expansion.cursor, True


@dataclass(frozen=True)
class NewFile:
    path: str
    line: int
    column: int
    message: str


def create_new_file(folder: str, file_name: str, project_dir: str, properties: Mapping[str, str],
                    today: Optional[datetime.date] = None) -> NewFile:
    """Writes a new file in folder from its file template. Raises ValueError (FileTemplateError is one)
    for a name with folders, a file that exists already, or a template that cannot be read."""
    file_name = file_name.strip()
    if not file_name or "/" in file_name or "\\" in file_name or file_name in (".", ".."):
        raise ValueError("the file name is a name without folders")
    path = os.path.join(folder, file_name)
    if os.path.exists(path):
        raise ValueError(f"not created, {file_name} exists already")

    text, cursor, has_template = new_file_text(file_name, properties, project_dir,
                                               os.path.basename(folder), today)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    line = text[:cursor].count("\n") + 1
    column = cursor - (text.rfind("\n", 0, cursor) + 1) + 1
    if has_template:
        message = f"created {file_name} from its file template"
    else:
        extension = extension_of(file_name) or "(none)"
        message = (f"created an empty {file_name}: no file template for {extension} "
                   f"(set {setting_key(extension)} to a template file)")
    return NewFile(path, line, column, message)
