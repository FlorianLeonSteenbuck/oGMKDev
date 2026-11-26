"""Project index: symbols, type hierarchy, dependencies, find-in-files and inspections.

* Symbols: PHP classes, interfaces, traits, enums, functions, methods, constants and properties
  (namespaces and ``use`` imports resolved), Python classes and functions, and JavaScript or
  TypeScript classes, interfaces and functions.
* Hierarchy: supertypes (extends, implements, traits) and subtypes, transitively; cycles are cut.
* Dependencies: the class names a class refers to (new, instanceof, ::, type hints, supertypes).
* Invalidation: every indexed file keeps its size and modification time. ``refresh()`` re-reads only
  files that were added or changed and drops deleted ones; ``invalidate(path)`` forces one file, which
  the editor calls after saving. Derived tables are rebuilt after each change.
* Cache: ``save_cache`` / ``load_cache`` keep the index between sessions; loading re-checks each file.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import ast
import bisect
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from . import baredown, diagnostics, editorconfig, languages, markup, organize
from .lexers import ecmascript_lexer as js_lexer
from .parsers import javascript as jsparser
from . import php_analysis
from .parsers import php as phpparser
from .lexers import sql_lexer

SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules"})
PHP_EXTENSIONS = frozenset({".php", ".phtml"})
PYTHON_EXTENSIONS = frozenset({".py"})
SCRIPT_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"})
SQL_EXTENSIONS = frozenset({".sql"})
STYLE_EXTENSIONS = frozenset({".css", ".scss", ".less", ".sass"})
JSON_EXTENSIONS = frozenset({".json"})
BAREDOWN_EXTENSIONS = frozenset({".bd", ".baredown"})
INDEXED = (PHP_EXTENSIONS | PYTHON_EXTENSIONS | SCRIPT_EXTENSIONS | markup.MARKUP_EXTENSIONS | SQL_EXTENSIONS
           | STYLE_EXTENSIONS | JSON_EXTENSIONS | BAREDOWN_EXTENSIONS)
# lock files of the package managers: generated, large, and full of keys that say nothing about the code
GENERATED_FILES = frozenset({"package-lock.json", "npm-shrinkwrap.json"})


def is_indexed(path: str) -> bool:
    """Whether a file is read into the index: its extension is one of INDEXED and it is no generated lock file."""
    return os.path.splitext(path)[1].lower() in INDEXED and os.path.basename(path).lower() not in GENERATED_FILES


@dataclass(frozen=True)
class Symbol:
    name: str                       # fully qualified for PHP ("App\\Shape"), plain otherwise
    kind: str                       # class | interface | trait | enum | function | method | constant | property
    file: str
    line: int
    column: int
    supertypes: Tuple[str, ...] = ()
    traits: Tuple[str, ...] = ()
    container: Optional[str] = None
    references: Tuple[str, ...] = ()
    abstract: bool = False

    @property
    def member(self) -> str:
        """Member name of a method, property or constant (empty for top-level symbols)."""
        return self.name.split("::", 1)[1].lstrip("$") if self.container else ""

    @property
    def short(self) -> str:
        return self.name.rsplit("\\", 1)[-1]


@dataclass
class FileEntry:
    mtime_ns: int
    size: int
    symbols: List[Symbol] = field(default_factory=list)
    references: List["Reference"] = field(default_factory=list)


# Occurrence of an identifier: name, line and column (both 1-based, column in characters)
Reference = Tuple[str, int, int]
# Version of the index cache: a cache of another version is ignored and rebuilt
CACHE_VERSION = 9
REFERENCE_SCRIPT_EXTENSIONS = SCRIPT_EXTENSIONS
# the parse options of a script: (typed, jsx); plain JavaScript reads JSX as the diagnostics do
SCRIPT_DIALECTS = {".ts": (True, False), ".tsx": (True, True), ".jsx": (False, True)}


@dataclass(frozen=True)
class SearchHit:
    file: str
    line: int
    column: int
    text: str


@dataclass(frozen=True)
class Inspection:
    file: str
    line: int
    column: int
    severity: str
    code: str
    message: str


def _position(source: str, offset: int) -> Tuple[int, int]:
    line = source.count("\n", 0, offset) + 1
    return line, offset - (source.rfind("\n", 0, offset) + 1) + 1


# ------------------------------------------------------------------ extraction

def _extract_php(source: str, path: str) -> List[Symbol]:
    """The declarations of a PHP file, read from its parse tree (see php_analysis): the classes, interfaces, traits and
    enums with their members, then the functions. A broken statement is skipped: the rest of the file is indexed."""
    tree, _errors = phpparser.parse_partial(source)
    symbols: List[Symbol] = []
    functions: List[Symbol] = []
    for declaration in php_analysis.declarations(tree, source):
        if declaration.kind == "function":
            functions.append(Symbol(declaration.name, "function", path, declaration.line, declaration.column))
            continue
        symbols.append(Symbol(declaration.name, declaration.kind, path, declaration.line, declaration.column,
                              declaration.supertypes, declaration.traits, None, declaration.references,
                              declaration.abstract))
        for member in declaration.members:
            symbols.append(Symbol(f"{declaration.name}::{member.name}", member.kind, path, member.line, member.column,
                                  container=declaration.name))
    return symbols + functions


_PY_CLASS = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", re.M)
_PY_DEF = re.compile(r"^def\s+(\w+)\s*\(", re.M)
_PY_METHOD = re.compile(r"(?:async[ \t]+)?def[ \t]+(\w+)[ \t]*\(")


def _python_methods(source: str) -> List[Tuple[str, str, int, int]]:
    """(class, method, line, column) of the methods written directly in the body of a top-level class. The body is
    the run of lines indented like its first statement; a line at column 0 that is neither blank nor a comment ends
    it, so the functions of a method and the members of a nested class are left out."""
    found: List[Tuple[str, str, int, int]] = []
    owner: Optional[str] = None
    body_indent: Optional[str] = None
    for number, text in enumerate(source.split("\n"), start=1):
        stripped = text.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if not text[0].isspace():
            header = _PY_CLASS.match(text)
            owner = header.group(1) if header else None
            body_indent = None
            continue
        if owner is None:
            continue
        indent = text[: len(text) - len(stripped)]
        if body_indent is None:
            body_indent = indent
        if indent != body_indent:
            continue
        method = _PY_METHOD.match(text, len(indent))
        if method:
            found.append((owner, method.group(1), number, method.start(1) + 1))
    return found


def _extract_python(source: str, path: str) -> List[Symbol]:
    symbols = []
    for match in _PY_CLASS.finditer(source):
        bases = [b.split("=")[0].strip() for b in (match.group(2) or "").split(",") if b.strip() and "=" not in b]
        line, column = _position(source, match.start(1))
        symbols.append(Symbol(match.group(1), "class", path, line, column, tuple(b for b in bases if b)))
    for match in _PY_DEF.finditer(source):
        line, column = _position(source, match.start(1))
        symbols.append(Symbol(match.group(1), "function", path, line, column))
    for owner, method, line, column in _python_methods(source):
        symbols.append(Symbol(f"{owner}::{method}", "method", path, line, column, container=owner))
    return symbols


_JS_CLASS = re.compile(r"^[ \t]*(?:export\s+)?(?:default\s+)?(class|interface)\s+(\w+)"
                       r"(?:\s+(?:extends|implements)\s+([\w.,\s<>]+?))?\s*(?:\{|$)", re.M)
_JS_FUNCTION = re.compile(r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(\w+)", re.M)


def _extract_script(source: str, path: str) -> List[Symbol]:
    symbols = []
    for match in _JS_CLASS.finditer(source):
        supers = []
        for part in (match.group(3) or "").split(","):
            name = re.sub(r"<.*>", "", part).strip()
            if name:
                supers.append(name)
        line, column = _position(source, match.start(2))
        symbols.append(Symbol(match.group(2), match.group(1), path, line, column, tuple(supers)))
    for match in _JS_FUNCTION.finditer(source):
        line, column = _position(source, match.start(1))
        symbols.append(Symbol(match.group(1), "function", path, line, column))
    return symbols


def extract(path: str, source: str) -> List[Symbol]:
    extension = os.path.splitext(path)[1].lower()
    if extension in PHP_EXTENSIONS:
        return _extract_php(source, path)
    if extension in PYTHON_EXTENSIONS:
        return _extract_python(source, path)
    if extension in SCRIPT_EXTENSIONS:
        return _extract_script(source, path)
    if extension in markup.MARKUP_EXTENSIONS:
        return _extract_markup(source, path)
    return []


def _char_column(line: str, byte_offset: int) -> int:
    """The 1-based column in characters for a column the ast module gives in UTF-8 bytes."""
    return len(line.encode("utf-8")[:byte_offset].decode("utf-8", errors="replace")) + 1


def _references_python(source: str) -> List[Reference]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    lines = source.split("\n")
    found: List[Reference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            line = lines[node.lineno - 1]
            found.append((node.id, node.lineno, _char_column(line, node.col_offset)))
        elif isinstance(node, ast.Attribute):
            # the attribute name ends the expression: `value.name`
            line = lines[node.end_lineno - 1]
            column = _char_column(line, node.end_col_offset) - len(node.attr)
            found.append((node.attr, node.end_lineno, column))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            line = lines[node.lineno - 1]
            start = line.find(node.name, _char_column(line, node.col_offset) - 1)
            if start >= 0:
                found.append((node.name, node.lineno, start + 1))
        elif isinstance(node, ast.arg):
            line = lines[node.lineno - 1]
            found.append((node.arg, node.lineno, _char_column(line, node.col_offset)))
        elif isinstance(node, ast.alias) and "." not in node.name and getattr(node, "lineno", None):
            line = lines[node.lineno - 1]
            found.append((node.name, node.lineno, _char_column(line, node.col_offset)))
    return found


def _references_parsed(source: str, typed: bool, jsx: bool) -> Optional[List[Reference]]:
    """The identifiers and JSX names of a parsed script; JSX text is no name. None: the script does not parse."""
    try:
        tree = jsparser.parse(source, typed=typed, jsx=jsx)
    except (jsparser.ParseError, RecursionError):
        return None
    found: List[Reference] = []
    pending = [tree]
    while pending:
        node = pending.pop()
        if node.kind in ("Identifier", "JSXName"):
            line, column = _position(source, node.start)
            found.append((source[node.start:node.end], line, column))
        pending.extend(getattr(node, "children", []))
    return sorted(found, key=lambda reference: (reference[1], reference[2]))


def _references_script(source: str) -> List[Reference]:
    starts = [0] + [index + 1 for index, char in enumerate(source) if char == "\n"]
    found: List[Reference] = []
    for token in js_lexer.tokenize(source):
        if token.kind != "identifier":
            continue
        line = bisect.bisect_right(starts, token.start)
        found.append((source[token.start:token.end], line, token.start - starts[line - 1] + 1))
    return found


def _references_php(source: str) -> List[Reference]:
    """The names of the code of a PHP file (see php_analysis.occurrences)."""
    tree, _errors = phpparser.parse_partial(source)
    return php_analysis.occurrences(tree, source)


def _references_sql(source: str) -> List[Reference]:
    """The identifiers of a SQL file: table, column and alias names. Keywords, comments and strings hold none."""
    found: List[Reference] = []
    for token in sql_lexer.tokenize(source):
        if token.kind != "identifier":
            continue
        line, column = _position(source, token.start)
        found.append((source[token.start:token.end], line, column))
    return found


def _blank(match) -> str:
    """The match with every character but the line breaks replaced by a space: the offsets stay the same."""
    return re.sub(r"[^\n]", " ", match.group(0))


_MARKUP_TAG = re.compile(r"</?\s*([A-Za-z_][\w:.\-]*)")
_MARKUP_CLASS = re.compile(r"""(?<![\w:.\-])class\s*=\s*(["'])([^"'<>]*)\1""")
_MARKUP_HASH_REFERENCE = re.compile(r"""(?<![\w:.\-])(?:href|src|xlink:href)\s*=\s*(["'])#([^"'<>\s]+)\1""")


def _references_markup(source: str) -> List[Reference]:
    """The names of a markup file: element names, the ids it declares and refers to (href="#id", url(#id)), and
    the classes. Comments hold none."""
    text = re.sub(r"<!--.*?-->", _blank, source, flags=re.S)
    found: List[Reference] = []

    def add(offset: int, name: str) -> None:
        line, column = _position(source, offset)
        found.append((name, line, column))

    for match in _MARKUP_TAG.finditer(text):
        add(match.start(1), match.group(1))
    for match in markup.ID_ATTRIBUTE.finditer(text):
        add(match.start(2), match.group(2))
    for match in _MARKUP_CLASS.finditer(text):
        for token in re.finditer(r"\S+", match.group(2)):
            add(match.start(2) + token.start(), token.group(0))
    for match in _MARKUP_HASH_REFERENCE.finditer(text):
        add(match.start(2), match.group(2))
    for match in markup.CSS_URL.finditer(text):
        if match.group(2).startswith("#"):
            add(match.start(2) + 1, match.group(2)[1:])
    return sorted(found, key=lambda reference: (reference[1], reference[2]))


_STYLE_STRING_OR_COMMENT = re.compile(r"/\*.*?\*/|\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'", re.S)
_STYLE_BLOCK = re.compile(r"([^{};]+)\{")
_STYLE_ATTRIBUTE = re.compile(r"\[[^\]]*\]")
_STYLE_CLASS = re.compile(r"\.(-?[A-Za-z_][\w-]*)")
_STYLE_ID = re.compile(r"#([A-Za-z_][\w-]*)")
_STYLE_TYPE = re.compile(r"(?<![\w.#:\-$%&@(\[])([A-Za-z][\w-]*)")


def _references_style(source: str) -> List[Reference]:
    """The names in the selectors of a style sheet: classes, ids and element names. Comments, strings, attribute
    selectors, at-rules and declarations hold none."""
    text = _STYLE_STRING_OR_COMMENT.sub(_blank, source)
    found: List[Reference] = []
    for block in _STYLE_BLOCK.finditer(text):
        selector = block.group(1)
        if selector.lstrip().startswith("@"):
            continue
        selector = _STYLE_ATTRIBUTE.sub(lambda match: " " * len(match.group(0)), selector)
        for pattern in (_STYLE_CLASS, _STYLE_ID, _STYLE_TYPE):
            for match in pattern.finditer(selector):
                line, column = _position(source, block.start(1) + match.start(1))
                found.append((match.group(1), line, column))
    return sorted(found, key=lambda reference: (reference[1], reference[2]))


# ---------------------------------------------------------------- references of JSON, BareDown and templates

JSON_NAME = re.compile(r"[A-Za-z_]\w*(?:\\\\[A-Za-z_]\w*)*")
JSON_STRING_OR_COMMENT = re.compile(r'"((?:[^"\\\n]|\\.)*)"|//[^\n]*|/\*.*?\*/', re.S)
GENERIC_NAME = re.compile(r"(?<![\w$])[A-Za-z_]\w*")  # an identifier; a variable ($name) is none
BAREDOWN_TARGET = re.compile(r"\[\[([^\]|]+)")
TARGET_NAME = re.compile(r"[A-Za-z_]\w*(?:[\\/][A-Za-z_]\w*)*")
# the language a code block names in its fence, and the extension whose reference rules read the block
FENCE_EXTENSIONS = {"php": ".php", "python": ".py", "py": ".py", "javascript": ".js", "js": ".js",
                    "typescript": ".ts", "ts": ".ts", "tsx": ".tsx", "jsx": ".jsx", "sql": ".sql",
                    "html": ".html", "xml": ".xml", "svg": ".svg", "css": ".css", "scss": ".scss",
                    "less": ".less", "sass": ".sass", "json": ".json"}
# the tags of the template layers: Mustache {{name}}, {{{raw}}}, {{#section}}, {{! comment}};
# Twig {{ value }}, {% tag %} and {# comment #}
TEMPLATE_TAGS = {
    "mustache": re.compile(r"\{\{\{.*?\}\}\}|\{\{.*?\}\}", re.S),
    "twig": re.compile(r"\{#.*?#\}|\{\{.*?\}\}|\{%.*?%\}", re.S),
}
TEMPLATE_STRING = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'")
TWIG_KEYWORDS = frozenset({
    "and", "apply", "as", "autoescape", "block", "cache", "deprecated", "do", "else", "elseif", "embed", "endapply",
    "endautoescape", "endblock", "endcache", "endembed", "endfilter", "endfor", "endif", "endmacro", "endsandbox",
    "endset", "endspaceless", "endverbatim", "endwith", "extends", "false", "filter", "flush", "for", "from", "if",
    "ignore", "import", "in", "include", "is", "macro", "missing", "none", "not", "null", "only", "or", "sandbox",
    "set", "spaceless", "true", "types", "use", "verbatim", "with",
})


def _names_in(source: str, text: str, base: int) -> List[Reference]:
    """The identifiers of a code text that starts at offset ``base`` of the source."""
    found: List[Reference] = []
    for match in GENERIC_NAME.finditer(text):
        line, column = _position(source, base + match.start())
        found.append((match.group(0), line, column))
    return found


def _references_json(source: str) -> List[Reference]:
    """The names in the strings of a JSON file, keys and values alike. A string is a name when it is an identifier,
    or a qualified name, which counts as its last part, as in PHP. Comments, as tsconfig files have them, hold none."""
    found: List[Reference] = []
    for match in JSON_STRING_OR_COMMENT.finditer(source):
        raw = match.group(1)
        if raw is None or not JSON_NAME.fullmatch(raw):
            continue
        last = raw.rsplit("\\\\", 1)[-1]
        line, column = _position(source, match.start(1) + len(raw) - len(last))
        found.append((last, line, column))
    return found


def _link_name(source: str, start: int, end: int) -> List[Reference]:
    """The name a BareDown link points to: [[Target]], or the last part of [[docs/Target|label]]."""
    match = BAREDOWN_TARGET.match(source, start, end)
    if match is None:
        return []
    raw = match.group(1)
    target = raw.strip()
    if not TARGET_NAME.fullmatch(target):
        return []
    last = re.split(r"[\\/]", target)[-1]
    first = match.start(1) + len(raw) - len(raw.lstrip())
    line, column = _position(source, first + len(target) - len(last))
    return [(last, line, column)]


def _references_baredown(source: str) -> List[Reference]:
    """The names a BareDown document uses: the identifiers of its code spans (|code|) and code blocks, a block in a
    language the index reads being read with that language's rules, and the last part of a link target. Its prose
    and its comments hold none."""
    found: List[Reference] = []
    for token in baredown.tokenize(source):
        if token.kind == "code-inline":
            found.extend(_names_in(source, source[token.start + 1:token.end - 1], token.start + 1))
        elif token.kind == "link":
            found.extend(_link_name(source, token.start, token.end))
    for block in baredown.parse(source):
        if block.kind != "code":
            continue
        extension = FENCE_EXTENSIONS.get(block.language.lower())
        if extension is None:
            for number, text_line in enumerate(block.text.split("\n"), start=1):
                for match in GENERIC_NAME.finditer(text_line):
                    found.append((match.group(0), block.line + number, match.start() + 1))
            continue
        # PHP in a document often has no open tag: it is read after one, which takes up a line of its own
        shift = 1 if extension == ".php" else 0
        code = "<?php\n" + block.text if shift else block.text
        for name, line, column in _references_by_extension(extension, code):
            found.append((name, block.line + line - shift, column))
    return sorted(found, key=lambda reference: (reference[1], reference[2]))


def _references_template(layer: str, base: str, source: str) -> List[Reference]:
    """The names of a Mustache or Twig template: the identifiers in its tags, such as user.name in {{ user.name }}
    or items in {% for item in items %}. A filter after a pipe is no name, nor a Twig keyword, nor a string in a tag.
    Comments hold none. The base language (the extension after the layer, such as .html) is read with the tags
    left out."""
    found: List[Reference] = []
    for match in TEMPLATE_TAGS[layer].finditer(source):
        text = match.group(0)
        if text.startswith(("{#", "{{!", "{{=")):  # a comment, or a change of the delimiters
            continue
        masked = TEMPLATE_STRING.sub(_blank, text)
        for name in re.finditer(r"(?<!\w)[A-Za-z_]\w*", masked):
            word = name.group(0)
            if masked[:name.start()].rstrip().endswith("|") or (layer == "twig" and word.lower() in TWIG_KEYWORDS):
                continue
            line, column = _position(source, match.start() + name.start())
            found.append((word, line, column))
    found.extend(_references_by_extension(base, TEMPLATE_TAGS[layer].sub(_blank, source)))
    return sorted(found, key=lambda reference: (reference[1], reference[2]))


def _references_by_extension(extension: str, source: str) -> List[Reference]:
    if extension in PHP_EXTENSIONS:
        return _references_php(source)
    if extension in SQL_EXTENSIONS:
        return _references_sql(source)
    if extension in STYLE_EXTENSIONS:
        return _references_style(source)
    if extension in markup.MARKUP_EXTENSIONS:
        return _references_markup(source)
    if extension in PYTHON_EXTENSIONS:
        return _references_python(source)
    if extension in REFERENCE_SCRIPT_EXTENSIONS:
        parsed = _references_parsed(source, *SCRIPT_DIALECTS.get(extension, (False, True)))
        return parsed if parsed is not None else _references_script(source)
    if extension in JSON_EXTENSIONS:
        return _references_json(source)
    if extension in BAREDOWN_EXTENSIONS:
        return _references_baredown(source)
    return []


def extract_references(path: str, source: str) -> List[Reference]:
    """Identifier occurrences of a PHP, Python, SQL, script, markup, style, JSON or BareDown file, and of a Mustache or
    Twig template (see _references_template). Comments, strings and JSX text hold none; keywords are not identifiers.
    A script that does not parse is read as tokens."""
    parts = os.path.basename(path).lower().split(".")
    if len(parts) >= 3 and parts[-2] in languages.TEMPLATE_LAYERS:
        return _references_template(parts[-2], "." + parts[-1], source)
    return _references_by_extension(os.path.splitext(path)[1].lower(), source)


XSD_DECLARATIONS = frozenset({"element", "complexType", "simpleType", "group", "attributeGroup", "attribute"})
XSLT_DECLARATIONS = frozenset({"template", "variable", "param", "attribute-set", "key", "function"})


def _extract_markup(source: str, path: str) -> List[Symbol]:
    """The id attributes of XML, SVG and HTML documents (each id is a declaration named by its value), and
    in XML Schema and XSLT the named declarations: schema types and elements, named templates, variables."""
    found = [Symbol(name=name, kind="id", file=path, line=line, column=column)
             for name, line, column, _tag in markup.id_positions(source) if name]
    extension = os.path.splitext(path)[1].lower()
    if extension in (".xsd", ".xsl", ".xslt"):
        elements, _error = markup.collect(source)
        for element in elements:
            name = element.attributes.get("name", "")
            prefix, _sep, local = element.tag.rpartition(":")
            if not name:
                continue
            if (prefix in ("xs", "xsd") and local in XSD_DECLARATIONS) or (prefix == "xsl" and local in XSLT_DECLARATIONS):
                found.append(Symbol(name=name, kind="declaration", file=path, line=element.line,
                                    column=element.column))
    return found


# ----------------------------------------------------------------------- index

class ProjectIndex:
    """Index of one or more project folders; ``excluded`` drops paths the workspace ignores."""

    def __init__(self, roots, cache_path: Optional[str] = None, excluded=None) -> None:
        self.roots: List[str] = [os.path.abspath(r) for r in ([roots] if isinstance(roots, str) else roots)]
        self.excluded = excluded
        self.cache_path = cache_path
        self.files: Dict[str, FileEntry] = {}
        self._by_name: Dict[str, List[Symbol]] = {}
        self._subtypes: Dict[str, List[str]] = {}
        self._dirty = True
        if cache_path and os.path.isfile(cache_path):
            self.load_cache(cache_path)
        self.refresh()

    # --- invalidation

    def _walk(self):
        for root in self.roots:
            for directory, subdirs, names in os.walk(root):
                subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS
                              and not (self.excluded and self.excluded(os.path.join(directory, d)))]
                for name in names:
                    yield os.path.join(directory, name)

    def _scan(self) -> Dict[str, Tuple[int, int]]:
        found: Dict[str, Tuple[int, int]] = {}
        for path in self._walk():
            if is_indexed(path) and not (self.excluded and self.excluded(path)):
                stat = os.stat(path)
                found[path] = (stat.st_mtime_ns, stat.st_size)
        return found

    def refresh(self) -> Dict[str, int]:
        """Re-index added and changed files, drop deleted ones. Returns the counts."""
        current = self._scan()
        counts = {"added": 0, "changed": 0, "removed": 0}
        for path in list(self.files):
            if path not in current:
                del self.files[path]
                counts["removed"] += 1
        for path, (mtime, size) in current.items():
            entry = self.files.get(path)
            if entry is None:
                counts["added"] += 1
            elif entry.mtime_ns != mtime or entry.size != size:
                counts["changed"] += 1
            else:
                continue
            self._index_file(path, mtime, size)
        if any(counts.values()):
            self._rebuild()
        return counts

    def invalidate(self, path: str) -> bool:
        """Re-index one file (after a save). Returns True when it is indexed now."""
        path = os.path.abspath(path)
        ignored = self.excluded is not None and self.excluded(path)
        if ignored or not os.path.isfile(path) or not is_indexed(path):
            removed = self.files.pop(path, None) is not None
            if removed:
                self._rebuild()
            return False
        stat = os.stat(path)
        self._index_file(path, stat.st_mtime_ns, stat.st_size)
        self._rebuild()
        return True

    def _index_file(self, path: str, mtime: int, size: int) -> None:
        with open(path, encoding="utf-8", errors="replace") as handle:
            source = handle.read()
        self.files[path] = FileEntry(mtime, size, extract(path, source), extract_references(path, source))

    def _rebuild(self) -> None:
        self._by_name = {}
        self._subtypes = {}
        self._members = {}
        self._refs = {}
        for path, entry in self.files.items():
            for name, line, column in entry.references:
                self._refs.setdefault(name, []).append((path, line, column))
            for symbol in entry.symbols:
                self._by_name.setdefault(symbol.name.lower(), []).append(symbol)
                if symbol.container:
                    self._by_name.setdefault(symbol.member.lower(), []).append(symbol)
                    self._members.setdefault(symbol.container.lower(), []).append(symbol)
                elif symbol.short.lower() != symbol.name.lower():
                    self._by_name.setdefault(symbol.short.lower(), []).append(symbol)
                for parent in symbol.supertypes + symbol.traits:
                    self._subtypes.setdefault(parent.lower(), []).append(symbol.name)
        self._dirty = False

    # --- queries

    @property
    def symbols(self) -> List[Symbol]:
        return [s for entry in self.files.values() for s in entry.symbols]

    def find(self, name: str) -> List[Symbol]:
        return [s for s in self._by_name.get(name.lower(), []) if s.container is None]

    def references(self, name: str) -> List[Reference]:
        """Every occurrence of an identifier with exactly this name, as (file, line, column), in file order."""
        return sorted(self._refs.get(name, []))

    def definitions(self, name: str) -> List[Symbol]:
        """Declarations a name can refer to: classes, functions, and members with that name.

        Classes come first; a member is listed for every class that declares it.
        """
        found = self._by_name.get(name.lower(), [])
        return sorted(found, key=lambda s: (s.container is not None, s.file, s.line))

    def members_of(self, name: str, kind: Optional[str] = None) -> List[Symbol]:
        return [s for s in self._members.get(name.lower(), []) if kind is None or s.kind == kind]

    def missing_implementations(self) -> List[Tuple[Symbol, str, str]]:
        """(class, interface or abstract class, method) for concrete classes lacking an inherited method."""
        result: List[Tuple[Symbol, str, str]] = []
        for symbol in self.symbols:
            if symbol.container is not None or symbol.kind != "class" or symbol.abstract:
                continue
            provided = set()
            for candidate in [symbol] + [a for a in self.supertypes(symbol.name) if a.kind != "unresolved"]:
                if candidate.kind == "interface":
                    continue
                provided.update(m.member.lower() for m in self.members_of(candidate.name, "method"))
                for trait in candidate.traits:
                    provided.update(m.member.lower() for m in self.members_of(trait, "method"))
            for ancestor in self.supertypes(symbol.name):
                if ancestor.kind == "unresolved" or not (ancestor.kind == "interface" or ancestor.abstract):
                    continue
                for method in self.members_of(ancestor.name, "method"):
                    if method.member.lower() not in provided:
                        result.append((symbol, ancestor.short, method.member))
        return result

    def supertypes(self, name: str, transitive: bool = True) -> List[Symbol]:
        seen: Dict[str, Symbol] = {}
        pending = [name]
        while pending:
            current = pending.pop()
            for symbol in self.find(current):
                for parent in symbol.supertypes + symbol.traits:
                    if parent.lower() not in seen and parent.lower() != name.lower():
                        target = self.find(parent)
                        seen[parent.lower()] = target[0] if target else Symbol(parent, "unresolved", "", 0, 0)
                        if transitive:
                            pending.append(parent)
            if not transitive:
                break
        return list(seen.values())

    def _canonical(self, name: str) -> str:
        """The full name of a class given by its short or full name (unchanged when unknown)."""
        found = self.find(name)
        return found[0].name if found else name

    def subtypes(self, name: str, transitive: bool = True) -> List[Symbol]:
        seen: Dict[str, Symbol] = {}
        pending = list(dict.fromkeys(symbol.name for symbol in self.find(name))) or [name]
        while pending:
            current = pending.pop()
            for child in self._subtypes.get(current.lower(), []):
                if child.lower() not in seen:
                    for symbol in self.find(child):
                        seen[child.lower()] = symbol
                        if transitive:
                            pending.append(child)
            if not transitive:
                break
        return list(seen.values())

    def implementations(self, name: str) -> List[Symbol]:
        return self.subtypes(name, transitive=True)

    def hierarchy(self, name: str, depth: int = 8) -> dict:
        """Tree for the class ``name``: ``up`` (supertypes) and ``down`` (subtypes), cycle-safe."""
        def up(current: str, seen: frozenset, level: int) -> List[dict]:
            if level >= depth:
                return []
            nodes = []
            for symbol in self.find(current):
                for parent in symbol.supertypes + symbol.traits:
                    if parent.lower() in seen:
                        continue
                    target = self.find(parent)
                    node = {"name": parent, "symbol": target[0] if target else None}
                    node["children"] = up(parent, seen | {parent.lower()}, level + 1)
                    nodes.append(node)
            return nodes

        def down(current: str, seen: frozenset, level: int) -> List[dict]:
            if level >= depth:
                return []
            nodes = []
            for child_name in self._subtypes.get(current.lower(), []):
                if child_name.lower() in seen:
                    continue
                children = self.find(child_name)
                if not children:
                    continue
                node = {"name": child_name, "symbol": children[0]}
                node["children"] = down(child_name, seen | {child_name.lower()}, level + 1)
                nodes.append(node)
            return nodes

        target = self.find(name)
        canonical = target[0].name if target else name
        return {"name": canonical, "symbol": target[0] if target else None,
                "up": up(canonical, frozenset({canonical.lower()}), 0),
                "down": down(canonical, frozenset({canonical.lower()}), 0)}

    def dependencies(self, name: str) -> List[str]:
        names: List[str] = []
        for symbol in self.find(name):
            names.extend(symbol.supertypes + symbol.traits + symbol.references)
        return list(dict.fromkeys(names))

    def unresolved_supertypes(self) -> List[Tuple[Symbol, str]]:
        result = []
        for symbol in self.symbols:
            if symbol.container is None and symbol.kind in ("class", "interface", "trait", "enum"):
                for parent in symbol.supertypes + symbol.traits:
                    if not self.find(parent):
                        result.append((symbol, parent))
        return result

    def find_in_files(self, pattern: str, regex: bool = False, case_sensitive: bool = False,
                      glob: str = "*", limit: int = 1000) -> List[SearchHit]:
        flags = 0 if case_sensitive else re.IGNORECASE
        matcher = re.compile(pattern if regex else re.escape(pattern), flags)
        hits: List[SearchHit] = []
        for path in sorted(self._walk()):
            if not fnmatch.fnmatch(os.path.basename(path), glob):
                continue
            try:
                with open(path, "rb") as handle:
                    raw = handle.read()
            except OSError:
                continue
            if b"\0" in raw[:1024]:
                continue
            for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
                for match in matcher.finditer(line):
                    hits.append(SearchHit(path, number, match.start() + 1, line.strip()))
                    if len(hits) >= limit:
                        return hits
        return hits
        return hits

    def inspect(self) -> List[Inspection]:
        """Inspections over the project: diagnostics of every file and unresolved supertypes."""
        results: List[Inspection] = []
        for path in sorted(self.files):
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            settings = editorconfig.settings_for(path)
            detection = languages.detect_file(path, settings.custom)
            for item in diagnostics.analyze(text, detection, settings):
                results.append(Inspection(path, item.line, item.column, item.severity, item.code, item.message))
        for symbol, missing in self.unresolved_supertypes():
            results.append(Inspection(symbol.file, symbol.line, symbol.column, "warning", "unresolved-supertype",
                                      f"{symbol.short} extends or implements unknown type {missing}"))
        for symbol, interface, method in self.missing_implementations():
            results.append(Inspection(symbol.file, symbol.line, symbol.column, "error", "missing-implementation",
                                      f"{symbol.short} does not implement {method}() from {interface}"))
        for path in sorted(self.files):
            if os.path.splitext(path)[1].lower() in PHP_EXTENSIONS:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                for statement in organize.unused_imports(text):
                    results.append(Inspection(path, statement.line, statement.column, "warning", "unused-import",
                                              f"import {statement.fqn} is never used"))
                for statement in organize.unresolved_imports(text, self):
                    results.append(Inspection(path, statement.line, statement.column, "hint", "unresolved-import",
                                              f"import {statement.fqn} cannot be resolved in the project"))
        return results

    # --- cache

    def save_cache(self, path: Optional[str] = None) -> None:
        target = path or self.cache_path
        if target is None:
            raise ValueError("no cache path")
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        data = {path_: {"mtime_ns": e.mtime_ns, "size": e.size, "symbols": [asdict(s) for s in e.symbols],
                        "references": [list(r) for r in e.references]}
                for path_, e in self.files.items()}
        with open(target, "w", encoding="utf-8") as handle:
            json.dump({"version": CACHE_VERSION, "roots": self.roots, "files": data}, handle)

    def load_cache(self, path: str) -> None:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("version") != CACHE_VERSION or data.get("roots") != self.roots:
            return
        self.files = {}
        for file_path, entry in data.get("files", {}).items():
            symbols = [Symbol(s["name"], s["kind"], s["file"], s["line"], s["column"],
                              tuple(s["supertypes"]), tuple(s["traits"]), s["container"],
                              tuple(s["references"]), s.get("abstract", False)) for s in entry["symbols"]]
            references = [(r[0], r[1], r[2]) for r in entry.get("references", [])]
            self.files[file_path] = FileEntry(entry["mtime_ns"], entry["size"], symbols, references)
        self._rebuild()
