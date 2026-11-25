"""Documentation of a project as HTML pages, built from the declarations of its index.

Each indexed file gets a page with its declarations in source order, the doc comment above a
declaration as its description. PHP, JavaScript and TypeScript read the ``/** */`` block directly
above the declaration (attributes and decorators may sit in between). Python reads the docstring,
the first statement of a class or function. A block is split into a summary, a description and
tags: ``@param``, ``@return``, ``@property``, ``@throws`` and the rest, in the forms PHPDoc and
JSDoc write them. Python docstrings use the Google sections Args, Returns, Attributes and Raises.

``export`` writes ``index.html``, ``style.css`` and one page per file under ``pages/``. The command
line exports folders:  python3 -m ogmkdev.htmldoc FOLDER... --out DIR
"""

from __future__ import annotations

import argparse
import ast
import html
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .index import ProjectIndex, Symbol

DECLARATION_KINDS = frozenset({"class", "interface", "trait", "enum", "function", "method", "constant", "property"})
PYTHON_SUFFIXES = (".py", ".pyi")

TAG_LINE = re.compile(r"^@([A-Za-z][\w-]*)\s*(.*)$")
JS_TYPE = re.compile(r"^\{([^}]*)\}\s*(.*)$")
PHP_SUBJECT = re.compile(r"^&?(?:\.\.\.)?\$\w+$")
SECTION = re.compile(r"^(Args|Arguments|Parameters|Attributes|Returns|Return|Raises|Yields)\s*:\s*$")
SECTION_ENTRY = re.compile(r"^(\*{0,2}\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$")


@dataclass
class Tag:
    name: str
    type: str = ""
    subject: str = ""
    text: str = ""


@dataclass
class Doc:
    summary: str = ""
    description: List[str] = field(default_factory=list)
    tags: List[Tag] = field(default_factory=list)


@dataclass
class Entry:
    symbol: Symbol
    signature: str
    doc: Optional[Doc]


@dataclass
class Export:
    out_dir: str
    files: int
    declarations: int
    documented: int


# ---------------------------------------------------------------- finding the doc comment

def _is_skipped(line: str) -> bool:
    """Blank lines, attributes and decorators, and the closing brackets of a multi-line one."""
    stripped = line.strip()
    return (stripped == "" or stripped.startswith("#[") or stripped.startswith("@")
            or re.fullmatch(r"[\)\]\},;]+", stripped) is not None)


def block_above(lines: Sequence[str], line: int) -> Optional[str]:
    """The text of the ``/** */`` block that ends right above the 1-based line, or None."""
    index = line - 2
    while index >= 0 and _is_skipped(lines[index]):
        index -= 1
    if index < 0 or not lines[index].rstrip().endswith("*/"):
        return None

    start = index
    while start >= 0 and "/*" not in lines[start]:
        start -= 1
    if start < 0 or not lines[start].lstrip().startswith("/**"):
        return None

    text_lines = []
    for position, raw in enumerate(lines[start:index + 1]):
        text = raw.strip()
        if position == 0:
            text = text[3:]
        if text.endswith("*/"):
            text = text[:-2]
        text = text.lstrip()
        if text.startswith("*"):
            text = text[1:]
            text = text[1:] if text.startswith(" ") else text
        text_lines.append(text.rstrip())
    return "\n".join(text_lines).strip("\n")


def python_docstrings(text: str) -> Dict[int, str]:
    """The docstrings of the classes and functions in a Python source, by line of their definition."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    found: Dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=True)
            if doc:
                found[node.lineno] = doc
    return found


# ---------------------------------------------------------------- parsing a block

def _param_parts(rest: str) -> Tuple[str, str, str]:
    """(type, name, text) of a @param or @property: PHPDoc ``type $name text``, JSDoc ``{type} name - text``."""
    match = JS_TYPE.match(rest)
    if match:
        words = match.group(2).split(None, 1)
        subject = words[0].strip("[]").split("=")[0] if words else ""
        text = words[1] if len(words) > 1 else ""
        return match.group(1).strip(), subject, re.sub(r"^-\s*", "", text).strip()

    words = rest.split(None, 2)
    if len(words) >= 2 and PHP_SUBJECT.match(words[1]):
        return words[0], words[1], words[2] if len(words) > 2 else ""
    if words and PHP_SUBJECT.match(words[0]):
        return "", words[0], rest[len(words[0]):].strip()
    if words:
        return "", words[0].strip("[]"), rest[len(words[0]):].strip()
    return "", "", ""


def _return_parts(rest: str) -> Tuple[str, str]:
    """(type, text) of a @return: PHPDoc ``type text``, JSDoc ``{type} text``."""
    match = JS_TYPE.match(rest)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    words = rest.split(None, 1)
    if not words:
        return "", ""
    return words[0], words[1] if len(words) > 1 else ""


def _make_tag(name: str, rest: str) -> Tag:
    if name in ("param", "property", "property-read", "property-write", "var"):
        type_, subject, text = _param_parts(rest)
        return Tag(name, type=type_, subject=subject, text=text)
    if name in ("return", "returns"):
        type_, text = _return_parts(rest)
        return Tag("return", type=type_, text=text)
    if name in ("throws", "throw", "exception"):
        words = rest.split(None, 1)
        return Tag("throws", type=words[0] if words else "", text=words[1] if len(words) > 1 else "")
    return Tag(name, text=rest)


def _paragraphs(lines: List[str]) -> List[str]:
    paragraphs, current = [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


def parse_block(text: str) -> Doc:
    """Splits the text of a PHPDoc or JSDoc block into its summary, description and tags."""
    description: List[str] = []
    tags: List[Tag] = []
    current: Optional[Tag] = None
    for line in text.split("\n"):
        match = TAG_LINE.match(line.strip())
        if match:
            current = _make_tag(match.group(1), match.group(2).strip())
            tags.append(current)
        elif current is not None:
            if line.strip():
                current.text = (current.text + " " + line.strip()).strip()
        else:
            description.append(line)

    paragraphs = _paragraphs(description)
    return Doc(summary=paragraphs[0] if paragraphs else "", description=paragraphs[1:], tags=tags)


def parse_python_docstring(text: str) -> Doc:
    """Splits a Python docstring: the text before the Google sections, then the sections as tags."""
    lines = text.split("\n")
    head: List[str] = []
    tags: List[Tag] = []
    section: Optional[str] = None
    body: List[str] = []

    def flush() -> None:
        if section is None:
            return
        entries: List[List[str]] = []
        indent = None
        for line in body:
            if not line.strip():
                continue
            width = len(line) - len(line.lstrip())
            if indent is None:
                indent = width
            if width <= indent:
                entries.append([line.strip()])
            elif entries:
                entries[-1].append(line.strip())
        for entry in entries:
            _add_section_tag(tags, section, entry)

    for line in lines:
        header = SECTION.match(line.strip()) if not line.startswith(" ") else None
        if header:
            flush()
            section, body = header.group(1), []
        elif section is None:
            head.append(line)
        else:
            body.append(line)
    flush()

    paragraphs = _paragraphs(head)
    return Doc(summary=paragraphs[0] if paragraphs else "", description=paragraphs[1:], tags=tags)


def _add_section_tag(tags: List[Tag], section: str, entry: List[str]) -> None:
    first = entry[0]
    rest = " ".join(entry[1:])
    match = SECTION_ENTRY.match(first)
    if section in ("Args", "Arguments", "Parameters", "Attributes"):
        if match:
            name, type_, text = match.group(1).lstrip("*"), match.group(2) or "", match.group(3)
            tags.append(Tag("property" if section == "Attributes" else "param", type=type_,
                            subject=name, text=" ".join(filter(None, [text, rest]))))
        else:
            tags.append(Tag("property" if section == "Attributes" else "param", subject=first,
                            text=rest))
    elif section in ("Returns", "Return", "Yields"):
        tags.append(Tag("yields" if section == "Yields" else "return",
                        text=" ".join(filter(None, [first, rest]))))
    elif section == "Raises":
        if match:
            tags.append(Tag("throws", type=match.group(1), text=" ".join(filter(None, [match.group(3), rest]))))
        else:
            tags.append(Tag("throws", text=" ".join(entry)))


# ---------------------------------------------------------------- the entries of a file

def _entries_for(path: str, symbols: List[Symbol]) -> List[Entry]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        text = ""
    lines = text.splitlines()
    python = path.endswith(PYTHON_SUFFIXES)
    docstrings = python_docstrings(text) if python else {}

    entries = []
    for symbol in symbols:
        signature = lines[symbol.line - 1].strip() if 0 < symbol.line <= len(lines) else symbol.name
        if python:
            raw = docstrings.get(symbol.line)
            doc = parse_python_docstring(raw) if raw else None
        else:
            raw = block_above(lines, symbol.line)
            doc = parse_block(raw) if raw else None
        entries.append(Entry(symbol, signature, doc))
    return entries


# ---------------------------------------------------------------- HTML

STYLE = """
:root { color-scheme: light dark; --fg: #1d1f21; --muted: #6b7078; --line: #d7dae0; --code: #f4f5f7; --link: #1f6feb; }
@media (prefers-color-scheme: dark) {
  :root { --fg: #d8dbe0; --muted: #9aa1ab; --line: #3a3f47; --code: #20242a; --link: #6cb6ff; }
}
body { font: 15px/1.5 system-ui, sans-serif; color: var(--fg); margin: 0 auto; max-width: 960px; padding: 24px 16px; }
a { color: var(--link); }
h1 { font-size: 1.6em; margin: 0.4em 0; }
h2 { font-size: 1.15em; border-bottom: 1px solid var(--line); padding-bottom: 4px; margin-top: 2em; }
.kind { color: var(--muted); font-weight: normal; font-size: 0.85em; text-transform: uppercase; }
pre.signature, code { background: var(--code); border-radius: 4px; font: 13px/1.4 ui-monospace, monospace; }
pre.signature { padding: 8px 10px; overflow-x: auto; }
.summary { font-weight: 600; }
.undocumented { color: var(--muted); font-style: italic; }
dl.tags { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; }
dl.tags dt { color: var(--muted); }
dl.tags dd { margin: 0; }
ul.files li { margin: 4px 0; }
.count { color: var(--muted); }
"""


def _document(title: str, body: str, depth: int) -> str:
    style = "../" * depth + "style.css"
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{html.escape(title)}</title>\n<link rel="stylesheet" href="{style}">\n'
            f'</head>\n<body>\n{body}\n</body>\n</html>\n')


def _anchor(symbol: Symbol) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", f"{symbol.kind}-{symbol.name}")


def _render_entry(entry: Entry) -> str:
    symbol = entry.symbol
    parts = [f'<section id="{_anchor(symbol)}">',
             f'<h2><span class="kind">{html.escape(symbol.kind)}</span> {html.escape(symbol.name)}</h2>',
             f'<pre class="signature">{html.escape(entry.signature)}</pre>']
    doc = entry.doc
    if doc is None:
        parts.append('<p class="undocumented">No doc comment.</p>')
    else:
        if doc.summary:
            parts.append(f'<p class="summary">{html.escape(doc.summary)}</p>')
        for paragraph in doc.description:
            parts.append(f'<p>{html.escape(paragraph)}</p>')
        if doc.tags:
            parts.append('<dl class="tags">')
            for tag in doc.tags:
                label = "@" + tag.name + (f" {tag.subject}" if tag.subject else "")
                details = " ".join(filter(None, [f"<code>{html.escape(tag.type)}</code>" if tag.type else "",
                                                 html.escape(tag.text)]))
                parts.append(f"<dt>{html.escape(label)}</dt><dd>{details}</dd>")
            parts.append("</dl>")
    parts.append("</section>")
    return "\n".join(parts)


def _render_page(title: str, entries: List[Entry], depth: int) -> str:
    body = [f'<p><a href="{"../" * depth}index.html">All files</a></p>', f"<h1>{html.escape(title)}</h1>"]
    body.extend(_render_entry(entry) for entry in entries)
    return _document(title, "\n".join(body), depth)


def _render_index(title: str, pages: List[Tuple[str, str, List[Entry]]]) -> str:
    items = []
    for rel, page, entries in pages:
        documented = sum(1 for entry in entries if entry.doc is not None)
        top = [entry for entry in entries if entry.symbol.container is None]
        links = ", ".join(f'<a href="{page}#{_anchor(entry.symbol)}">{html.escape(entry.symbol.short)}</a>'
                          for entry in top)
        items.append(f'<li><a href="{page}">{html.escape(rel)}</a> '
                     f'<span class="count">{_count(len(entries), "declaration")}, {documented} documented</span>'
                     + (f"<br>{links}" if links else "") + "</li>")
    body = f"<h1>{html.escape(title)}</h1>\n<ul class=\"files\">\n" + "\n".join(items) + "\n</ul>"
    return _document(title, body, 0)


# ---------------------------------------------------------------- export

def _count(number: int, word: str) -> str:
    return f"{number} {word}" + ("" if number == 1 else ("es" if word.endswith("s") else "s"))


def _relative(path: str, roots: Sequence[str]) -> str:
    for root in roots:
        if path.startswith(root + os.sep):
            rel = os.path.relpath(path, root)
            return os.path.join(os.path.basename(root), rel) if len(roots) > 1 else rel
    return os.path.basename(path)


def export(index: ProjectIndex, out_dir: str, title: str = "Documentation") -> Export:
    """Writes the pages of the index's declarations into out_dir."""
    by_file: Dict[str, List[Symbol]] = {}
    for symbol in index.symbols:
        if symbol.kind in DECLARATION_KINDS:
            by_file.setdefault(symbol.file, []).append(symbol)

    os.makedirs(out_dir, exist_ok=True)
    pages: List[Tuple[str, str, List[Entry]]] = []
    declarations = documented = 0
    for path in sorted(by_file):
        symbols = sorted(by_file[path], key=lambda s: (s.line, s.column))
        entries = _entries_for(path, symbols)
        rel = _relative(path, index.roots)
        page = os.path.join("pages", rel + ".html").replace(os.sep, "/")
        target = os.path.join(out_dir, page)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        depth = page.count("/")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(_render_page(rel, entries, depth))
        pages.append((rel, page, entries))
        declarations += len(entries)
        documented += sum(1 for entry in entries if entry.doc is not None)

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(_render_index(title, pages))
    with open(os.path.join(out_dir, "style.css"), "w", encoding="utf-8") as handle:
        handle.write(STYLE.strip() + "\n")
    return Export(out_dir=out_dir, files=len(pages), declarations=declarations, documented=documented)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ogmkdev.htmldoc",
                                     description="Export the doc comments of project folders as HTML pages.")
    parser.add_argument("folders", nargs="+", help="project folders to document")
    parser.add_argument("-o", "--out", required=True, help="folder for the pages")
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = export(ProjectIndex(args.folders), args.out)
    print(f"{_count(result.files, 'file')}, {_count(result.declarations, 'declaration')} ({result.documented} with a doc "
          f"comment) written to {result.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
