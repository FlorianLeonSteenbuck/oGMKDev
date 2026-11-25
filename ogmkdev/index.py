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
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from . import diagnostics, editorconfig, languages, organize
from .lexers import php_lexer

SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules"})
PHP_EXTENSIONS = frozenset({".php", ".phtml"})
PYTHON_EXTENSIONS = frozenset({".py"})
SCRIPT_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"})
INDEXED = PHP_EXTENSIONS | PYTHON_EXTENSIONS | SCRIPT_EXTENSIONS


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
    tokens = [t for t in php_lexer.tokenize(source) if t.kind not in ("html", "open", "close", "comment", "doc")]
    texts = [source[t.start:t.end] for t in tokens]
    lower = [t.lower() for t in texts]
    kinds = [t.kind for t in tokens]
    n = len(tokens)
    namespace = ""
    imports: Dict[str, str] = {}
    records: List[dict] = []
    functions: List[dict] = []
    file_refs: List[str] = []
    depth = 0
    paren = 0
    class_stack: List[dict] = []
    pending: Optional[dict] = None

    def resolve(name: str) -> str:
        name = name.strip()
        if name.startswith("\\"):
            return name[1:]
        first, _, rest = name.partition("\\")
        if first.lower() in imports:
            return imports[first.lower()] + ("\\" + rest if rest else "")
        return f"{namespace}\\{name}" if namespace else name

    i = 0
    while i < n:
        kind, text, low = kinds[i], texts[i], lower[i]
        if kind == "operator" and text == "{":
            depth += 1
            if pending is not None:
                class_stack.append({"rec": pending, "depth": depth, "paren": paren})
                pending = None
            i += 1
            continue
        if kind == "operator" and text == "}":
            if class_stack and class_stack[-1]["depth"] == depth:
                class_stack.pop()
            depth -= 1
            i += 1
            continue
        if kind == "operator" and text == "(":
            paren += 1
        elif kind == "operator" and text == ")":
            paren -= 1
        if kind == "keyword" and low == "namespace" and i + 1 < n and kinds[i + 1] == "name":
            namespace = texts[i + 1].strip("\\")
            i += 2
            continue
        if kind == "keyword" and low == "use" and not class_stack and depth == 0 \
                and not (i + 1 < n and texts[i + 1] == "("):
            j = i + 1
            while j < n and texts[j] != ";":
                if kinds[j] == "name":
                    fqn = texts[j].strip("\\")
                    alias = fqn.rsplit("\\", 1)[-1]
                    if j + 2 < n and lower[j + 1] == "as" and kinds[j + 2] == "name":
                        alias = texts[j + 2]
                        j += 2
                    imports[alias.lower()] = fqn
                j += 1
            i = j + 1
            continue
        if kind == "keyword" and low in ("class", "interface", "trait", "enum") and i + 1 < n \
                and kinds[i + 1] == "name" and not (i > 0 and texts[i - 1] in ("::", "->", "new")):
            line, column = _position(source, tokens[i + 1].start)
            rec = {"name": f"{namespace}\\{texts[i + 1]}" if namespace else texts[i + 1], "kind": low,
                   "line": line, "column": column, "supertypes": [], "traits": [], "refs": [], "members": [],
                   "abstract": low == "interface" or (i > 0 and lower[i - 1] == "abstract")}
            j, mode = i + 2, None
            while j < n and texts[j] not in ("{", ";"):
                if lower[j] == "extends":
                    mode = "extends"
                elif lower[j] == "implements":
                    mode = "implements"
                elif kinds[j] == "name" and mode:
                    rec["supertypes"].append(resolve(texts[j]))
                j += 1
            records.append(rec)
            pending = rec
            i = j
            continue
        if class_stack and depth == class_stack[-1]["depth"] and paren == class_stack[-1]["paren"]:
            rec = class_stack[-1]["rec"]
            if kind == "keyword" and low == "use":
                j = i + 1
                while j < n and texts[j] not in (";", "{"):
                    if kinds[j] == "name":
                        rec["traits"].append(resolve(texts[j]))
                    j += 1
                i = j if j < n and texts[j] == "{" else j + 1
                continue
            if kind == "keyword" and low == "function" and i + 1 < n and kinds[i + 1] == "name":
                line, column = _position(source, tokens[i + 1].start)
                rec["members"].append(("method", texts[i + 1], line, column))
            elif kind == "keyword" and low == "const":
                j = i + 1
                if j + 1 < n and kinds[j] != "operator" and kinds[j + 1] == "name":
                    j += 1
                if j < n and kinds[j] == "name":
                    line, column = _position(source, tokens[j].start)
                    rec["members"].append(("constant", texts[j], line, column))
            elif kind == "variable" and i + 1 < n and texts[i + 1] in ("=", ";", "{", ","):
                line, column = _position(source, tokens[i].start)
                rec["members"].append(("property", texts[i], line, column))
        if kind == "keyword" and low == "function" and depth == 0 and not class_stack \
                and i + 1 < n and kinds[i + 1] == "name":
            line, column = _position(source, tokens[i + 1].start)
            full = f"{namespace}\\{texts[i + 1]}" if namespace else texts[i + 1]
            functions.append({"name": full, "line": line, "column": column})
        if kind == "name" and not (i + 1 < n and texts[i + 1] == "("):
            before = texts[i - 1].lower() if i > 0 else ""
            after = texts[i + 1] if i + 1 < n else ""
            if before in ("new", "instanceof", "extends", "implements", "(", ",", ":", "|", "&", "?") \
                    or after == "::":
                target = resolve(texts[i])
                if class_stack:
                    class_stack[-1]["rec"]["refs"].append(target)
                else:
                    file_refs.append(target)
        i += 1

    symbols: List[Symbol] = []
    for rec in records:
        symbols.append(Symbol(rec["name"], rec["kind"], path, rec["line"], rec["column"],
                              tuple(rec["supertypes"]), tuple(rec["traits"]), None,
                              tuple(dict.fromkeys(rec["refs"])), rec["abstract"]))
        for member_kind, member, line, column in rec["members"]:
            symbols.append(Symbol(f"{rec['name']}::{member}", member_kind, path, line, column,
                                  container=rec["name"]))
    for function in functions:
        symbols.append(Symbol(function["name"], "function", path, function["line"], function["column"]))
    return symbols


_PY_CLASS = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:", re.M)
_PY_DEF = re.compile(r"^def\s+(\w+)\s*\(", re.M)


def _extract_python(source: str, path: str) -> List[Symbol]:
    symbols = []
    for match in _PY_CLASS.finditer(source):
        bases = [b.split("=")[0].strip() for b in (match.group(2) or "").split(",") if b.strip() and "=" not in b]
        line, column = _position(source, match.start(1))
        symbols.append(Symbol(match.group(1), "class", path, line, column, tuple(b for b in bases if b)))
    for match in _PY_DEF.finditer(source):
        line, column = _position(source, match.start(1))
        symbols.append(Symbol(match.group(1), "function", path, line, column))
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
    return []


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
            if os.path.splitext(path)[1].lower() in INDEXED and not (self.excluded and self.excluded(path)):
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
        if ignored or not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in INDEXED:
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
        self.files[path] = FileEntry(mtime, size, extract(path, source))

    def _rebuild(self) -> None:
        self._by_name = {}
        self._subtypes = {}
        self._members = {}
        for entry in self.files.values():
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
        data = {path_: {"mtime_ns": e.mtime_ns, "size": e.size, "symbols": [asdict(s) for s in e.symbols]}
                for path_, e in self.files.items()}
        with open(target, "w", encoding="utf-8") as handle:
            json.dump({"roots": self.roots, "files": data}, handle)

    def load_cache(self, path: str) -> None:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("roots") != self.roots:
            return
        self.files = {}
        for file_path, entry in data.get("files", {}).items():
            symbols = [Symbol(s["name"], s["kind"], s["file"], s["line"], s["column"],
                              tuple(s["supertypes"]), tuple(s["traits"]), s["container"],
                              tuple(s["references"]), s.get("abstract", False)) for s in entry["symbols"]]
            self.files[file_path] = FileEntry(entry["mtime_ns"], entry["size"], symbols)
        self._rebuild()
