"""Markup and style languages: JSON, XML (SVG, XSD, XSLT, IntelliJ module files), HTML and the CSS family.

Checks, used by :mod:`ogmkdev.diagnostics`:

* JSON syntax (``json-syntax``, error);
* XML well-formedness, for XML and SVG (``xml-syntax``, error);
* duplicate ``id`` values in XML, SVG and HTML (``duplicate-id``, warning);
* unbalanced braces in CSS, SCSS and LESS (``css-braces``, error); Sass is indented and has no braces.

Documents as elements (:func:`collect`): each element with its parent, its place among the element
siblings (``child_position``, CSS ``:nth-child``) and among the siblings with the same tag
(``type_position``, XPath ``[n]``), its attributes, and the character offsets of its start tag and of its
end. :func:`element_at` finds the innermost element under a cursor, and
:func:`reference_at` the value of a file or id reference under a cursor. All line and column numbers are
1-based.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from xml.parsers import expat

Problem = Tuple[int, int, str]

MARKUP_EXTENSIONS = frozenset({".xml", ".svg", ".xsd", ".xsl", ".xslt", ".iml", ".dtd", ".xul",
                               ".html", ".htm", ".xhtml"})
HTML_EXTENSIONS = frozenset({".html", ".htm", ".xhtml"})
VOID_ELEMENTS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                           "param", "source", "track", "wbr"})

# id="value" or id='value'; data-id and grid-id are not ids
ID_ATTRIBUTE = re.compile(r"""(?<![\w:.\-])id\s*=\s*(["'])([^"'<>]*)\1""")
TAG_NAME = re.compile(r"<\s*([\w:.\-]+)")
REFERENCE_ATTRIBUTES = frozenset({"href", "src", "xlink:href", "schemaLocation", "noNamespaceSchemaLocation",
                                  "location", "data", "action", "poster"})
ATTRIBUTE_VALUE = re.compile(r"""([\w:.\-]+)\s*=\s*(["'])([^"'<>]*)\2""")
CSS_URL = re.compile(r"""url\(\s*(["']?)([^)"'\s]+)\1\s*\)""")
CSS_IMPORT = re.compile(r"""@import\s+(["'])([^"']+)\1""")


def position(text: str, offset: int) -> Tuple[int, int]:
    """1-based line and column of a character offset."""
    line = text.count("\n", 0, offset) + 1
    column = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, column


def json_problems(text: str) -> List[Problem]:
    stripped = text.lstrip("﻿")
    if not stripped.strip():
        return []
    try:
        json.loads(stripped)
    except json.JSONDecodeError as error:
        return [(error.lineno, error.colno, f"JSON syntax error: {error.msg}")]
    return []


def xml_problems(text: str) -> List[Problem]:
    """Well-formedness problems of an XML document (SVG, XSD, XSLT and module files included)."""
    parser = expat.ParserCreate(encoding="utf-8")
    try:
        parser.Parse(text.encode("utf-8"), True)
    except expat.ExpatError as error:
        return [(error.lineno, error.offset + 1, f"XML syntax error: {expat.ErrorString(error.code)}")]
    return []


def id_positions(text: str) -> List[Tuple[str, int, int, str]]:
    """Every id value with its line, column and the element it belongs to: (id, line, column, tag)."""
    found = []
    for match in ID_ATTRIBUTE.finditer(text):
        line, column = position(text, match.start(2))
        start_tag = text.rfind("<", 0, match.start())
        tag = ""
        if start_tag >= 0:
            tag_match = TAG_NAME.match(text, start_tag)
            tag = tag_match.group(1) if tag_match else ""
        found.append((match.group(2), line, column, tag))
    return found


def duplicate_id_problems(text: str) -> List[Problem]:
    first: Dict[str, int] = {}
    problems: List[Problem] = []
    for name, line, column, _tag in id_positions(text):
        if not name:
            continue
        if name in first:
            problems.append((line, column, f"duplicate id '{name}' (first at line {first[name]})"))
        else:
            first[name] = line
    return problems


def braces_problems(text: str, line_comments: bool = False) -> List[Problem]:
    """Unbalanced ``{`` and ``}`` outside comments and strings. ``line_comments`` enables ``//`` (SCSS, LESS)."""
    problems: List[Problem] = []
    opened: List[int] = []
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
            continue
        if line_comments and text.startswith("//", index):
            end = text.find("\n", index)
            index = length if end < 0 else end
            continue
        char = text[index]
        if char in "\"'":
            end = index + 1
            while end < length and text[end] not in (char, "\n"):
                end += 2 if text[end] == "\\" else 1
            index = end + 1
            continue
        if char == "{":
            opened.append(index)
        elif char == "}":
            if opened:
                opened.pop()
            else:
                line, column = position(text, index)
                problems.append((line, column, "unexpected '}'"))
        index += 1
    for offset in opened:
        line, column = position(text, offset)
        problems.append((line, column, "'{' is never closed"))
    return problems


def reference_at(line: str, column: int) -> Optional[str]:
    """The value of a reference (href, src, xlink:href, schemaLocation, url(...), @import) under a
    1-based column of a line, or None. The value is returned as written."""
    index = column - 1
    if index < 0:
        return None
    for match in ATTRIBUTE_VALUE.finditer(line):
        if match.group(1) in REFERENCE_ATTRIBUTES and match.start(3) <= index <= match.end(3):
            return match.group(3)
    for pattern in (CSS_URL, CSS_IMPORT):
        for match in pattern.finditer(line):
            if match.start(2) <= index < match.end(2):
                return match.group(2)
    return None


# ----------------------------------------------------------------------- elements

@dataclass
class Element:
    index: int
    tag: str
    id: str
    classes: Tuple[str, ...]
    attributes: Dict[str, str]
    depth: int
    parent: Optional[int]
    line: int           # line and column (1-based) of the start tag
    column: int
    start: int          # character offsets: the start tag, and the end of the element
    end: int
    child_position: int  # 1-based among the element siblings
    type_position: int   # 1-based among the element siblings with the same tag


class _Lines:
    """Line starts of a text, to turn a line and a column into a character offset."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = [0] + [match.end() for match in re.finditer("\n", text)]

    def offset(self, line: int, column0: int) -> int:
        if line < 1 or line > len(self.starts):
            return len(self.text)
        return min(self.starts[line - 1] + column0, len(self.text))

    def tag_end(self, offset: int) -> int:
        """The offset just after the '>' that closes the tag at offset (quotes respected)."""
        text = self.text
        quote = None
        index = offset
        while index < len(text):
            char = text[index]
            if quote:
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == ">":
                return index + 1
            index += 1
        return len(text)


def _new_element(index, tag, attributes, depth, parent, line, column, start, end, counts, tag_counts) -> Element:
    counts[parent] = counts.get(parent, 0) + 1
    key = (parent, tag)
    tag_counts[key] = tag_counts.get(key, 0) + 1
    return Element(index=index, tag=tag, id=attributes.get("id", ""),
                   classes=tuple(attributes.get("class", "").split()), attributes=attributes, depth=depth,
                   parent=parent, line=line, column=column, start=start, end=end,
                   child_position=counts[parent], type_position=tag_counts[key])


class _HtmlCollector(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.text = text
        self.lines = _Lines(text)
        self.elements: List[Element] = []
        self.stack: List[int] = []
        self.counts: Dict[Optional[int], int] = {}
        self.tag_counts: Dict[Tuple[Optional[int], str], int] = {}

    def _here(self) -> Tuple[int, int, int]:
        line, column = self.getpos()
        return line, column, self.lines.offset(line, column)

    def handle_starttag(self, tag, attrs):
        line, column, start = self._here()
        parent = self.stack[-1] if self.stack else None
        attributes = {name: (value or "") for name, value in attrs}
        element = _new_element(len(self.elements), tag, attributes, len(self.stack), parent, line, column + 1,
                               start, self.lines.tag_end(start), self.counts, self.tag_counts)
        self.elements.append(element)
        if tag not in VOID_ELEMENTS:
            self.stack.append(element.index)

    def handle_endtag(self, tag):
        _line, _column, start = self._here()
        for depth in range(len(self.stack) - 1, -1, -1):
            element = self.elements[self.stack[depth]]
            if element.tag == tag:
                for index in self.stack[depth + 1:]:  # elements left open inside it end here
                    self.elements[index].end = start
                element.end = self.lines.tag_end(start)
                del self.stack[depth:]
                return


def _collect_xml(text: str) -> Tuple[List[Element], Optional[str]]:
    lines = _Lines(text)
    parser = expat.ParserCreate(encoding="utf-8")
    elements: List[Element] = []
    stack: List[int] = []
    counts: Dict[Optional[int], int] = {}
    tag_counts: Dict[Tuple[Optional[int], str], int] = {}

    def start(name, attributes):
        line, column = parser.CurrentLineNumber, parser.CurrentColumnNumber
        start_offset = lines.offset(line, column)
        parent = stack[-1] if stack else None
        element = _new_element(len(elements), name, dict(attributes), len(stack), parent, line, column + 1,
                               start_offset, lines.tag_end(start_offset), counts, tag_counts)
        elements.append(element)
        stack.append(element.index)

    def end(_name):
        line, column = parser.CurrentLineNumber, parser.CurrentColumnNumber
        if stack:
            element = elements[stack.pop()]
            element.end = lines.tag_end(lines.offset(line, column))

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(text.encode("utf-8"), True)
    except expat.ExpatError as error:
        return elements, expat.ErrorString(error.code)
    return elements, None


def collect(text: str, html: bool = False) -> Tuple[List[Element], Optional[str]]:
    """The elements of a document in document order. XML and the other XML dialects are read strictly,
    HTML leniently. Returns the elements read and an error message (None when the document was read
    completely)."""
    if html:
        collector = _HtmlCollector(text)
        error = None
        try:
            collector.feed(text)
            collector.close()
        except Exception as problem:  # the HTML parser is lenient; never let the view crash on it
            error = str(problem)
        for index in collector.stack:
            collector.elements[index].end = len(text)
        return collector.elements, error
    return _collect_xml(text)


def element_at(elements: List[Element], text: str, line: int, column: int) -> Optional[Element]:
    """The innermost element that contains the 1-based line and column, or None."""
    offset = _Lines(text).offset(line, column - 1)
    best: Optional[Element] = None
    for element in elements:
        if element.start <= offset < element.end and (best is None or element.start >= best.start):
            best = element
    return best


def elements(text: str, html: bool = False) -> Tuple[List[dict], Optional[str]]:
    """The elements as dictionaries (depth, tag, id, class, line, column) for the structure view."""
    found, error = collect(text, html)
    return [{"depth": e.depth, "tag": e.tag, "id": e.id, "class": " ".join(e.classes),
             "line": e.line, "column": e.column} for e in found], error


def label(node) -> str:
    """'tag#id.class1.class2' for the structure view (a dictionary from :func:`elements` or an Element)."""
    if isinstance(node, Element):
        tag, element_id, classes = node.tag, node.id, " ".join(node.classes)
    else:
        tag, element_id, classes = node["tag"], node.get("id", ""), node.get("class", "")
    text = tag
    if element_id:
        text += "#" + element_id
    for name in classes.split():
        text += "." + name
    return text
