"""BareDown: a small markup language of our own, implemented in pure Python.

It is not Markdown and no external system is involved. The grammar is line-based:

    = Title               heading, level 1 (use more "=" for levels 2 to 6)
    Plain paragraph text. Inline: **bold**, //italic//, |code|, [[Target]] and [[Target|label]]
    - bullet item         unordered list item
    + ordered item        ordered list item
    > quoted text         block quote
    %% comment           comment line, not rendered
    ----                  horizontal rule (four or more dashes alone on a line)
    ~~~ python            fenced code block, closed by a line with ~~~ (the language is optional)

Paragraphs are lines up to the next blank line or block start. A code fence that is never
closed is reported by :func:`problems`.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import List, NamedTuple, Tuple

HEADING = re.compile(r"^(=+)[ \t]+(.*\S)$")
BULLET = re.compile(r"^-[ \t]+(.*)$")
ORDERED = re.compile(r"^\+[ \t]+(.*)$")
QUOTE = re.compile(r"^>[ \t]?(.*)$")
COMMENT = re.compile(r"^%%(.*)$")
RULE = re.compile(r"^-{4,}$")
FENCE = re.compile(r"^~~~[ \t]*([A-Za-z0-9_+.-]*)$")
INLINE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*"
    r"|//(?P<italic>.+?)//"
    r"|\|(?P<code>[^|]+)\|"
    r"|\[\[(?P<target>[^\]|]+)(?:\|(?P<label>[^\]]+))?\]\]"
)
MAX_LEVEL = 6


@dataclass(frozen=True)
class Block:
    kind: str                 # heading | paragraph | bullet | ordered | quote | comment | rule | code
    text: str = ""
    level: int = 0
    language: str = ""
    line: int = 1
    closed: bool = True       # code blocks only: whether the closing fence was found


@dataclass(frozen=True)
class Inline:
    kind: str                 # text | bold | italic | code | link
    text: str
    target: str = ""


class Token(NamedTuple):
    kind: str
    start: int
    end: int


def parse(source: str) -> List[Block]:
    lines = source.splitlines()
    blocks: List[Block] = []
    paragraph: List[str] = []
    paragraph_line = 1

    def flush() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph), line=paragraph_line))
            paragraph = []

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        number = index + 1
        if not line.strip():
            flush()
            index += 1
            continue
        fence = FENCE.match(line)
        if fence:
            flush()
            body: List[str] = []
            closed = False
            scan = index + 1
            while scan < len(lines):
                if lines[scan].rstrip() == "~~~":
                    closed = True
                    break
                body.append(lines[scan])
                scan += 1
            blocks.append(Block("code", "\n".join(body), language=fence.group(1), line=number, closed=closed))
            index = scan + 1
            continue
        if RULE.match(line):
            flush()
            blocks.append(Block("rule", line=number))
        elif COMMENT.match(line):
            flush()
            blocks.append(Block("comment", COMMENT.match(line).group(1).strip(), line=number))
        elif HEADING.match(line):
            flush()
            match = HEADING.match(line)
            blocks.append(Block("heading", match.group(2), level=min(len(match.group(1)), MAX_LEVEL), line=number))
        elif BULLET.match(line):
            flush()
            blocks.append(Block("bullet", BULLET.match(line).group(1), line=number))
        elif ORDERED.match(line):
            flush()
            blocks.append(Block("ordered", ORDERED.match(line).group(1), line=number))
        elif QUOTE.match(line):
            flush()
            blocks.append(Block("quote", QUOTE.match(line).group(1), line=number))
        else:
            if not paragraph:
                paragraph_line = number
            paragraph.append(line.strip())
        index += 1
    flush()
    return blocks


def inline(text: str) -> List[Inline]:
    spans: List[Inline] = []
    position = 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            spans.append(Inline("text", text[position:match.start()]))
        if match.group("bold") is not None:
            spans.append(Inline("bold", match.group("bold")))
        elif match.group("italic") is not None:
            spans.append(Inline("italic", match.group("italic")))
        elif match.group("code") is not None:
            spans.append(Inline("code", match.group("code")))
        else:
            target = match.group("target").strip()
            spans.append(Inline("link", (match.group("label") or target).strip(), target))
        position = match.end()
    if position < len(text):
        spans.append(Inline("text", text[position:]))
    return spans


def _inline_tokens(text: str, base: int) -> List[Token]:
    tokens: List[Token] = []
    for match in INLINE.finditer(text):
        if match.group("bold") is not None:
            kind = "bold"
        elif match.group("italic") is not None:
            kind = "italic"
        elif match.group("code") is not None:
            kind = "code-inline"
        else:
            kind = "link"
        tokens.append(Token(kind, base + match.start(), base + match.end()))
    return tokens


def tokenize(source: str) -> List[Token]:
    """Highlighting tokens (possibly overlapping: block kind first, inline spans on top)."""
    tokens: List[Token] = []
    offset = 0
    in_code = False
    for raw in source.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        start = offset
        end = start + len(line)
        offset += len(raw)
        stripped = line.rstrip()
        if in_code:
            in_code = stripped != "~~~"
            tokens.append(Token("fence" if not in_code else "code", start, end))
            continue
        if FENCE.match(stripped):
            tokens.append(Token("fence", start, end))
            in_code = True
        elif RULE.match(stripped):
            tokens.append(Token("rule", start, end))
        elif COMMENT.match(stripped):
            tokens.append(Token("comment", start, end))
        elif HEADING.match(stripped):
            match = HEADING.match(stripped)
            tokens.append(Token("marker", start, start + len(match.group(1))))
            tokens.append(Token("heading", start, end))
            tokens.extend(_inline_tokens(match.group(2), start + match.start(2)))
        elif BULLET.match(stripped) or ORDERED.match(stripped) or QUOTE.match(stripped):
            for pattern, kind in ((BULLET, "bullet"), (ORDERED, "ordered"), (QUOTE, "quote")):
                match = pattern.match(stripped)
                if match:
                    tokens.append(Token("marker", start, start + 1))
                    tokens.append(Token(kind, start, end))
                    tokens.extend(_inline_tokens(match.group(1), start + match.start(1)))
                    break
        else:
            tokens.extend(_inline_tokens(line, start))
    return tokens


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _render_inline(text: str) -> str:
    parts = []
    for span in inline(text):
        if span.kind == "bold":
            parts.append(f"<strong>{_escape(span.text)}</strong>")
        elif span.kind == "italic":
            parts.append(f"<em>{_escape(span.text)}</em>")
        elif span.kind == "code":
            parts.append(f"<code>{_escape(span.text)}</code>")
        elif span.kind == "link":
            parts.append(f'<a href="{_escape(span.target)}">{_escape(span.text)}</a>')
        else:
            parts.append(_escape(span.text))
    return "".join(parts)


def to_html(source: str) -> str:
    out: List[str] = []
    open_list = None
    for block in parse(source):
        if block.kind in ("bullet", "ordered"):
            tag = "ul" if block.kind == "bullet" else "ol"
            if open_list != tag:
                if open_list:
                    out.append(f"</{open_list}>")
                out.append(f"<{tag}>")
                open_list = tag
            out.append(f"<li>{_render_inline(block.text)}</li>")
            continue
        if open_list:
            out.append(f"</{open_list}>")
            open_list = None
        if block.kind == "heading":
            out.append(f"<h{block.level}>{_render_inline(block.text)}</h{block.level}>")
        elif block.kind == "paragraph":
            out.append(f"<p>{_render_inline(block.text)}</p>")
        elif block.kind == "quote":
            out.append(f"<blockquote>{_render_inline(block.text)}</blockquote>")
        elif block.kind == "rule":
            out.append("<hr>")
        elif block.kind == "code":
            klass = f' class="language-{_escape(block.language)}"' if block.language else ""
            out.append(f"<pre><code{klass}>{_escape(block.text)}</code></pre>")
    if open_list:
        out.append(f"</{open_list}>")
    return "\n".join(out)


def problems(source: str) -> List[Tuple[int, str]]:
    """(line, message) for structural problems that the editor reports."""
    return [(block.line, "unterminated code block: missing closing ~~~")
            for block in parse(source) if block.kind == "code" and not block.closed]
