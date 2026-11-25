"""Diagnostics for the editor, built from the language modules.

Checks and their default severities:

* PHP heredoc and nowdoc errors (``heredoc-*``, error);
* PHP features newer than the file's PHP version, per feature (``php-<feature>``, error),
  library functions and classes (``php-function``, ``php-class``, warning);
* ECMAScript lexical and syntax errors (``js-lexical``, ``js-syntax``, error);
* BareDown unclosed code blocks (``baredown-fence``, warning);
* SQL ``ENGINE`` checks (``sql-unknown_engine`` warning, ``sql-not_supported`` warning).

Severities are configurable per check in EditorConfig: ``ogmkdev_diagnostic_<code>`` with the
values ``error``, ``warning``, ``hint`` or ``off`` (dashes become underscores, for example
``ogmkdev_diagnostic_php_match = off``). ``ogmkdev_diagnostics = off`` disables all checks.
Every diagnostic has a 1-based line and column.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional

from . import baredown, heredoc, php_features, sql
from .editorconfig import EditorSettings
from .languages import Detection
from .lexers import ecmascript_lexer
from .parsers import ecmascript as jsparser

SEVERITIES = ("error", "warning", "hint", "off")


@dataclass(frozen=True)
class Diagnostic:
    line: int
    column: int
    severity: str        # error | warning | hint
    code: str
    message: str


def _position(text: str, offset: int):
    line = text.count("\n", 0, offset) + 1
    column = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, column


def severity_setting(custom: Dict[str, str], code: str, default: str) -> str:
    value = custom.get("ogmkdev_diagnostic_" + code.replace("-", "_"), "").strip().lower()
    return value if value in SEVERITIES else default


def analyze(text: str, detection: Detection, settings: Optional[EditorSettings] = None) -> List[Diagnostic]:
    custom = dict(settings.custom) if settings is not None else {}
    if custom.get("ogmkdiagnostics", custom.get("ogmkdev_diagnostics", "on")).strip().lower() == "off":
        return []
    found: List[Diagnostic] = []
    if detection.language == "php" and detection.template is None:
        scan = heredoc.scan(text)
        for error in scan.errors:
            line, column = _position(text, error.offset)
            found.append(Diagnostic(line, column, "error", f"heredoc-{error.code}", error.message))
        for finding in php_features.findings_above(text, detection.dialect or "8.6"):
            if finding.kind == "feature":
                code, default = f"php-{finding.feature}", "error"
            else:
                code, default = f"php-{finding.kind}", "warning"
            found.append(Diagnostic(finding.line, finding.column, default, code, finding.message))
    if detection.language == "ecmascript":
        lexical = ecmascript_lexer.problems(text)
        for line, column, message in lexical:
            found.append(Diagnostic(line, column, "error", "js-lexical", message))
        if not lexical:
            try:
                jsparser.parse(text)
            except jsparser.ParseError as error:
                found.append(Diagnostic(error.line, error.column, "error", "js-syntax", error.message))
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
            found.append(Diagnostic(line, column, "warning", f"sql-{clause.problem}", message))
    resolved: List[Diagnostic] = []
    for item in found:
        severity = severity_setting(custom, item.code, item.severity)
        if severity != "off":
            resolved.append(replace(item, severity=severity))
    return sorted(resolved, key=lambda d: (d.line, d.column, d.code))


def summary(diagnostics: List[Diagnostic]) -> str:
    if not diagnostics:
        return "no diagnostics"
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = sum(1 for d in diagnostics if d.severity == "warning")
    first = diagnostics[0]
    return f"{errors} error(s), {warnings} warning(s); first: line {first.line}: {first.message}"
