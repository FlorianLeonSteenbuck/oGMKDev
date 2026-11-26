"""What the Preview page of the frame shows, read without GTK.

A Markdown file (the common part of CommonMark) and a BareDown file are read into blocks: headings, paragraphs,
list items, quotes, code blocks, rules and images. A block's text is a list of spans, each with its styles (bold,
italic, code) and, for a link, the target it points to. The frame draws the blocks (ogmkdev/frame/preview.py).

An image file is shown as the picture itself, for the raster formats only: an SVG is XML text, edited in the editor,
and has no preview.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import baredown

MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown", ".mdown"})
BAREDOWN_EXTENSIONS = frozenset({".bd", ".baredown"})
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"})


@dataclass(frozen=True)
class Span:
    """A run of text with its styles. A link has the target it points to; an image in a line of text has its
    source as the target and its alt text as the text."""
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    target: str = ""
    image: bool = False


@dataclass(frozen=True)
class Block:
    """One block of a document. Headings, paragraphs and list items keep their text in ``spans``; a code block its
    code in ``text`` and the language of its fence in ``language``; an image its source in ``target`` and its alt
    text in ``text``. ``level`` is the heading level, ``depth`` the nesting of a list item, ``number`` the number of
    an ordered item, and ``quote`` how deeply the block is quoted (0 for none)."""
    kind: str                       # heading | paragraph | bullet | ordered | quote | code | rule | image
    spans: Tuple[Span, ...] = ()
    level: int = 0
    depth: int = 0
    number: int = 0
    quote: int = 0
    text: str = ""
    language: str = ""
    target: str = ""


def kind_of(path: str) -> Optional[str]:
    """'markdown', 'baredown', 'image', or None when the file has no preview."""
    extension = os.path.splitext(path)[1].lower()
    if extension in MARKDOWN_EXTENSIONS:
        return "markdown"
    if extension in BAREDOWN_EXTENSIONS:
        return "baredown"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    return None


def blocks_of(kind: str, text: str) -> List[Block]:
    """The blocks of a Markdown or a BareDown text (see kind_of); none for any other kind."""
    text = text.lstrip("﻿").replace("\r\n", "\n")
    if kind == "markdown":
        lines = text.split("\n")
        if lines and lines[-1] == "":  # the line break that ends the file is no line of its own
            lines.pop()
        return _markdown_blocks(lines)
    if kind == "baredown":
        return _baredown_blocks(text)
    return []


# ------------------------------------------------------------------ Markdown

ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})[ \t]*([^`\s]*)")
RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
QUOTE = re.compile(r"^ {0,3}>[ \t]?(.*)$")
BULLET = re.compile(r"^([ \t]*)[-*+](?:[ \t]+(.*))?$")
ORDERED = re.compile(r"^([ \t]*)(\d{1,9})[.)](?:[ \t]+(.*))?$")
IMAGE_ONLY = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)(?:[ \t]+\"[^\"]*\")?\)$")
INLINE = re.compile(
    r"(?P<code>(?P<ticks>`+)(?P<code_text>.+?)(?P=ticks))"
    r"|(?P<image>!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:[ \t]+\"[^\"]*\")?\))"
    r"|(?P<link>\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)(?:[ \t]+\"[^\"]*\")?\))"
    r"|(?P<auto><(?P<url>(?:https?|mailto):[^>\s]+)>)"
    r"|(?:\*\*(?P<strong_star>.+?)\*\*|(?<!\w)__(?P<strong_under>.+?)__(?!\w))"
    r"|(?:\*(?!\s)(?P<em_star>.+?)(?<!\s)\*|(?<!\w)_(?!\s)(?P<em_under>.+?)(?<!\s)_(?!\w))"
    r"|\\(?P<escaped>[!-/:-@\[-`{-~])"
)


def _spans(text: str, bold: bool = False, italic: bool = False, target: str = "") -> List[Span]:
    """The spans of a line of text: code, images, links, emphasis (nested emphasis inside emphasis), escapes."""
    spans: List[Span] = []
    position = 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            spans.append(Span(text[position:match.start()], bold, italic, False, target))
        if match.group("code") is not None:
            spans.append(Span(match.group("code_text"), bold, italic, True, target))
        elif match.group("image") is not None:
            spans.append(Span(match.group("alt") or match.group("src"), bold, italic, False, match.group("src"), True))
        elif match.group("link") is not None:
            spans.extend(_spans(match.group("label"), bold, italic, match.group("href")))
        elif match.group("auto") is not None:
            spans.append(Span(match.group("url"), bold, italic, False, match.group("url")))
        elif match.group("strong_star") is not None or match.group("strong_under") is not None:
            inner = match.group("strong_star") if match.group("strong_star") is not None else match.group("strong_under")
            spans.extend(_spans(inner, True, italic, target))
        elif match.group("em_star") is not None or match.group("em_under") is not None:
            inner = match.group("em_star") if match.group("em_star") is not None else match.group("em_under")
            spans.extend(_spans(inner, bold, True, target))
        else:  # an escaped punctuation mark stands for itself
            spans.append(Span(match.group("escaped"), bold, italic, False, target))
        position = match.end()
    if position < len(text):
        spans.append(Span(text[position:], bold, italic, False, target))
    return spans


def _join(lines: Sequence[str]) -> str:
    """The text of a paragraph or a list item: its lines joined by a space; two spaces at the end of a line make a
    line break."""
    text = ""
    previous = None
    for line in lines:
        if previous is not None:
            text += "\n" if previous.endswith("  ") else " "
        text += line.strip()
        previous = line
    return text


def _paragraph(lines: Sequence[str], quote: int) -> Block:
    text = _join(lines)
    image = IMAGE_ONLY.match(text)
    if image:
        return Block("image", text=image.group(1), target=image.group(2), quote=quote)
    return Block("paragraph", spans=tuple(_spans(text)), quote=quote)


def _unindent(line: str, width: int) -> str:
    return re.sub(rf"^ {{0,{width}}}", "", line)


def _markdown_blocks(lines: Sequence[str], quote: int = 0) -> List[Block]:
    out: List[Block] = []
    paragraph: List[str] = []
    item: List = []  # the open list item: its kind, depth, number and lines; empty when there is none

    def end_paragraph() -> None:
        if paragraph:
            out.append(_paragraph(paragraph, quote))
            paragraph.clear()

    def end_item() -> None:
        if item:
            kind, depth, number, parts = item
            out.append(Block(kind, spans=tuple(_spans(_join(parts))), depth=depth, number=number, quote=quote))
            item.clear()

    def end_all() -> None:
        end_paragraph()
        end_item()

    index = 0
    while index < len(lines):
        line = lines[index].expandtabs(4)
        if not line.strip():
            end_all()
            index += 1
            continue
        fence = FENCE.match(line)
        if fence:
            end_all()
            marker = fence.group(2)
            width = len(fence.group(1))
            body: List[str] = []
            index += 1
            while index < len(lines):
                inner = lines[index].expandtabs(4)
                stripped = inner.strip()
                if stripped and set(stripped) == {marker[0]} and len(stripped) >= len(marker):
                    break
                body.append(_unindent(inner, width))
                index += 1
            index += 1  # the closing fence; a fence that is never closed reads to the end
            out.append(Block("code", text="\n".join(body), language=fence.group(3).lower(), quote=quote))
            continue
        if paragraph and SETEXT.match(line):  # an underline makes the paragraph above a heading
            level = 1 if line.strip().startswith("=") else 2
            out.append(Block("heading", spans=tuple(_spans(_join(paragraph))), level=level, quote=quote))
            paragraph.clear()
            index += 1
            continue
        atx = ATX.match(line)
        if atx:
            end_all()
            title = re.sub(r"(?:^|[ \t]+)#+$", "", atx.group(2) or "").strip()
            out.append(Block("heading", spans=tuple(_spans(title)), level=len(atx.group(1)), quote=quote))
            index += 1
            continue
        if RULE.match(line):
            end_all()
            out.append(Block("rule", quote=quote))
            index += 1
            continue
        if QUOTE.match(line):
            end_all()
            inner: List[str] = []
            while index < len(lines):
                marked = QUOTE.match(lines[index].expandtabs(4))
                if not marked:
                    break
                inner.append(marked.group(1))
                index += 1
            out.extend(_markdown_blocks(inner, quote + 1))
            continue
        bullet = BULLET.match(line)
        ordered = ORDERED.match(line)
        if bullet or ordered:
            end_all()
            if bullet:
                item.extend(["bullet", len(bullet.group(1)) // 2, 0, [bullet.group(2) or ""]])
            else:
                item.extend(["ordered", len(ordered.group(1)) // 2, int(ordered.group(2)), [ordered.group(3) or ""]])
            index += 1
            continue
        if line.startswith("    ") and not paragraph and not item:  # indented code, outside of any block
            body = []
            while index < len(lines):
                inner_line = lines[index].expandtabs(4)
                if inner_line.strip() and not inner_line.startswith("    "):
                    break
                body.append(inner_line[4:] if inner_line.startswith("    ") else "")
                index += 1
            while body and not body[-1].strip():
                body.pop()
            out.append(Block("code", text="\n".join(body), quote=quote))
            continue
        if item:  # the text under a list item continues the item
            item[3].append(line)
        else:
            paragraph.append(line)
        index += 1
    end_all()
    return out


# ------------------------------------------------------------------ BareDown

def _baredown_spans(text: str) -> Tuple[Span, ...]:
    spans: List[Span] = []
    for inline in baredown.inline(text):
        if inline.kind == "bold":
            spans.append(Span(inline.text, bold=True))
        elif inline.kind == "italic":
            spans.append(Span(inline.text, italic=True))
        elif inline.kind == "code":
            spans.append(Span(inline.text, code=True))
        elif inline.kind == "link":
            spans.append(Span(inline.text, target=inline.target))
        else:
            spans.append(Span(inline.text))
    return tuple(spans)


def _baredown_blocks(text: str) -> List[Block]:
    out: List[Block] = []
    for block in baredown.parse(text):
        if block.kind == "comment":
            continue
        if block.kind == "rule":
            out.append(Block("rule"))
        elif block.kind == "code":
            out.append(Block("code", text=block.text, language=block.language.lower()))
        elif block.kind == "heading":
            out.append(Block("heading", spans=_baredown_spans(block.text), level=block.level))
        elif block.kind == "bullet":
            out.append(Block("bullet", spans=_baredown_spans(block.text)))
        elif block.kind == "ordered":
            out.append(Block("ordered", spans=_baredown_spans(block.text)))
        elif block.kind == "quote":
            out.append(Block("paragraph", spans=_baredown_spans(block.text), quote=1))
        else:
            out.append(Block("paragraph", spans=_baredown_spans(block.text)))
    return out
