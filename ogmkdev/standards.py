"""Coding standards as diagnostics: the rules of the EditorConfig that a file breaks.

A rule is active only when the EditorConfig sets it: trim_trailing_whitespace (trailing blanks),
indent_style (tabs or spaces, and no mix of them), max_line_length (the width of a line, tabs counted
with tab_width), end_of_line (the line endings, or mixed endings when none is set) and
insert_final_newline (a newline at the end of the file). The severity of each rule is configurable
with ogmkdev_diagnostic_<rule>; the defaults are set in the diagnostics.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .editorconfig import EditorSettings

TRAILING_BLANKS = re.compile(r"[ \t]+$")
LEADING_BLANKS = re.compile(r"^([ \t]*)")
COMMENT_CONTINUATION = re.compile(r"^\t+ \*")
LINE_ENDINGS = {"lf": "\n", "crlf": "\r\n"}

# (line, column, rule, default severity, message)
Problem = Tuple[int, int, str, str, str]


def _lines(text: str) -> List[str]:
    """The lines of the text without their line endings; a CRLF ending is kept as a trailing CR."""
    return text.split("\n")


def problems(text: str, settings: EditorSettings) -> List[Problem]:
    found: List[Problem] = []
    lines = _lines(text)
    body = [line[:-1] if line.endswith("\r") else line for line in lines]
    # the last piece is the text after the last newline; it is empty when the file ends with one
    last_index = len(lines)

    if settings.trim_trailing_whitespace:
        for number, line in enumerate(body, 1):
            match = TRAILING_BLANKS.search(line)
            if match:
                found.append((number, match.start() + 1, "trailing-whitespace", "hint",
                              "trailing spaces or tabs at the end of the line"))

    if settings.indent_style in ("tab", "space"):
        for number, line in enumerate(body, 1):
            leading = LEADING_BLANKS.match(line).group(1)
            if not leading or not line.strip():
                continue
            aligned = settings.indent_style == "tab" and COMMENT_CONTINUATION.match(line)
            if "\t" in leading and " " in leading and not aligned:
                found.append((number, 1, "indent-style", "warning", "indentation mixes tabs and spaces"))
            elif settings.indent_style == "space" and "\t" in leading:
                found.append((number, 1, "indent-style", "warning", "indented with a tab, the style is spaces"))
            elif settings.indent_style == "tab" and " " in leading and not aligned:
                found.append((number, 1, "indent-style", "warning", "indented with spaces, the style is tabs"))

    if settings.max_line_length:
        width_of_tab = settings.tab_width or 4
        for number, line in enumerate(body, 1):
            width = len(line.expandtabs(width_of_tab))
            if width > settings.max_line_length:
                found.append((number, settings.max_line_length + 1, "line-length", "warning",
                              f"line is {width} characters, the limit is {settings.max_line_length}"))

    crlf_count = text.count("\r\n")
    lf_count = text.count("\n") - crlf_count
    if settings.end_of_line in LINE_ENDINGS:
        wanted_crlf = settings.end_of_line == "crlf"
        for number, line in enumerate(lines[:-1], 1):
            ends_crlf = line.endswith("\r")
            if ends_crlf != wanted_crlf:
                found.append((number, len(body[number - 1]) + 1, "line-endings", "warning",
                              f"line ends with {'CRLF' if ends_crlf else 'LF'}, end_of_line is "
                              f"{settings.end_of_line.upper()}"))
    elif crlf_count and lf_count:
        found.append((1, 1, "line-endings", "warning",
                      f"mixed line endings: {crlf_count} with CRLF, {lf_count} with LF"))

    if settings.insert_final_newline and text and not text.endswith("\n"):
        found.append((last_index, len(body[-1]) + 1, "final-newline", "hint",
                      "the file does not end with a newline"))
    return found
