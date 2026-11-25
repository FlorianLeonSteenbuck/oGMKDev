"""Diagnostics for the editor, built from the Python language modules.

* PHP: heredoc/nowdoc errors from :mod:`ogmkdev.heredoc` (unterminated labels, bad indent).
* SQL: ``ENGINE`` table options checked against the dialect by :mod:`ogmkdev.sql`.

Every diagnostic has a 1-based line and column so the GUI can place it in the buffer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import baredown, heredoc, sql
from .lexers import ecmascript_lexer
from .editorconfig import EditorSettings
from .languages import Detection


@dataclass(frozen=True)
class Diagnostic:
    line: int
    column: int
    severity: str        # "error" | "warning"
    code: str
    message: str


def _position(text: str, offset: int) -> tuple:
    line = text.count("\n", 0, offset) + 1
    column = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, column


def analyze(text: str, detection: Detection, settings: Optional[EditorSettings] = None) -> List[Diagnostic]:
    found: List[Diagnostic] = []
    if detection.language == "php" and detection.template is None:
        scan = heredoc.scan(text)
        for error in scan.errors:
            line, column = _position(text, error.offset)
            found.append(Diagnostic(line, column, "error", f"heredoc-{error.code}", error.message))
    if detection.language == "ecmascript":
        for line, column, message in ecmascript_lexer.problems(text):
            found.append(Diagnostic(line, column, "error", "js-syntax", message))
    if detection.language == "baredown":
        for line, message in baredown.problems(text):
            found.append(Diagnostic(line, 1, "warning", "baredown-fence", message))
    if detection.language == "sql":
        dialect = detection.dialect or "generic"
        for clause in sql.engine_clauses(text, dialect):
            if clause.problem is None:
                continue
            line, column = _position(text, clause.offset)
            if clause.problem == "unknown_engine":
                message = f"unknown storage engine '{clause.name}' for {dialect}"
            else:
                message = f"ENGINE={clause.name} is a MySQL/MariaDB table option; {dialect} does not support it"
            found.append(Diagnostic(line, column, "warning", clause.problem, message))
    return sorted(found, key=lambda d: (d.line, d.column))


def summary(diagnostics: List[Diagnostic]) -> str:
    if not diagnostics:
        return "no diagnostics"
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = len(diagnostics) - errors
    first = diagnostics[0]
    return f"{errors} error(s), {warnings} warning(s); first: line {first.line}: {first.message}"
