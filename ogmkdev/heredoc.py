"""PHP heredoc / nowdoc scanner with PHP's own closing-label rules.

PHP semantics (PHP >= 7.3) that this scanner follows:

* the opener is ``<<<`` + optional blanks + ``LABEL`` (heredoc) or ``'LABEL'`` (nowdoc),
  followed by a newline; ``"LABEL"`` is accepted as a heredoc;
* the closing line must start with the *same* label after optional spaces/tabs, and the
  label must not be followed by another identifier character. Anything after the label
  on that line (``;``, ``)``, ``,`` ...) is ordinary code;
* the closing indentation is removed from every body line, and a non-empty body line
  indented less than the closing label is an error;
* inside code, ``<<<`` is only an opener when it is not part of a string, a comment or
  inline HTML.

A typo such as ``<<<HEREDOC ... ENDDOC;`` is therefore reported as unterminated, exactly
like ``php -l`` reports it. ``ENDDOC`` is not a closing label for ``HEREDOC``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

_OPENER = re.compile(r"<<<[ \t]*(['\"]?)([A-Za-z_\x80-\U0010ffff][A-Za-z0-9_\x80-\U0010ffff]*)\1(\r?\n)")
_IDENT_CHAR = re.compile(r"[A-Za-z0-9_\x80-\U0010ffff]")


@dataclass(frozen=True)
class HeredocSpan:
    kind: str           # "heredoc" | "nowdoc"
    label: str
    start: int         # offset of "<<<"
    body_start: int    # offset of the first body character
    body_end: int      # offset of the closing line (its indentation included)
    end: int           # offset just after the closing label
    indent: str        # indentation of the closing label
    value: str         # body with closing indentation removed, final newline dropped


@dataclass(frozen=True)
class HeredocError:
    code: str           # "unterminated" | "bad_indent"
    offset: int
    message: str


@dataclass(frozen=True)
class HeredocScan:
    spans: Tuple[HeredocSpan, ...]
    errors: Tuple[HeredocError, ...]


def _skip_string(src: str, i: int, quote: str) -> int:
    j = i + 1
    n = len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
        elif c == quote:
            return j + 1
        else:
            j += 1
    return n


def _line_comment_end(src: str, i: int) -> int:
    newline = src.find("\n", i)
    end = len(src) if newline < 0 else newline
    close_tag = src.find("?>", i, end)
    return close_tag if close_tag >= 0 else end


def _read_heredoc(src: str, start: int, match: "re.Match[str]") -> Tuple[Optional[HeredocSpan], Optional[HeredocError], int]:
    quote, label = match.group(1), match.group(2)
    kind = "nowdoc" if quote == "'" else "heredoc"
    body_start = match.end()
    n = len(src)
    position = body_start
    while position <= n:
        line_end = src.find("\n", position)
        line_end = n if line_end < 0 else line_end
        line = src[position:line_end].rstrip("\r")
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith(label):
            after = stripped[len(label):len(label) + 1]
            if not after or not _IDENT_CHAR.match(after):
                body_end = position
                closing_end = position + len(indent) + len(label)
                raw_body = src[body_start:body_end]
                value, bad = _dedent(raw_body, indent)
                if bad is not None:
                    return None, HeredocError("bad_indent", bad, "closing label indentation is deeper than a body line"), closing_end
                if value.endswith("\r\n"):
                    value = value[:-2]
                elif value.endswith("\n"):
                    value = value[:-1]
                span = HeredocSpan(kind, label, start, body_start, body_end, closing_end, indent, value)
                return span, None, closing_end
        if line_end >= n:
            break
        position = line_end + 1
    error = HeredocError("unterminated", start, f"no closing label '{label}' for heredoc opened here")
    return None, error, n


def _dedent(raw_body: str, indent: str) -> Tuple[str, Optional[int]]:
    """Remove the closing indentation; return (text, offset_of_bad_line or None)."""
    if not indent:
        return raw_body, None
    out: List[str] = []
    offset = 0
    for line in raw_body.splitlines(keepends=True):
        if line.startswith(indent):
            out.append(line[len(indent):])
        elif line.strip(" \t\r\n") == "":  # whitespace-only lines may be shallower
            out.append(line.lstrip(" \t"))
        else:
            return raw_body, offset
        offset += len(line)
    return "".join(out), None


def scan(src: str) -> HeredocScan:
    """Find every heredoc/nowdoc in the PHP code of ``src``."""
    spans: List[HeredocSpan] = []
    errors: List[HeredocError] = []
    n = len(src)
    i = 0
    in_php = False
    while i < n:
        if not in_php:
            open_tag = src.find("<?", i)
            if open_tag < 0:
                break
            if src.startswith("<?php", open_tag):
                i = open_tag + 5
                in_php = True
            elif src.startswith("<?=", open_tag):
                i = open_tag + 3
                in_php = True
            else:
                i = open_tag + 2
            continue
        if src.startswith("?>", i):
            in_php = False
            i += 2
            continue
        c = src[i]
        if c in "'\"":
            i = _skip_string(src, i, c)
            continue
        if src.startswith("//", i) or (c == "#" and not src.startswith("#[", i)):
            i = _line_comment_end(src, i)
            continue
        if src.startswith("/*", i):
            close = src.find("*/", i + 2)
            i = n if close < 0 else close + 2
            continue
        if src.startswith("<<<", i):
            match = _OPENER.match(src, i)
            if match:
                span, error, nxt = _read_heredoc(src, i, match)
                if span:
                    spans.append(span)
                if error:
                    errors.append(error)
                i = nxt
                continue
        i += 1
    return HeredocScan(tuple(spans), tuple(errors))
