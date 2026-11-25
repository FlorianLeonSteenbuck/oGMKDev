"""SQL dialects and the table ``ENGINE`` option.

``ENGINE=InnoDB`` is a MySQL/MariaDB table option. The engine name is validated against
the storage engines each server ships with. Names are case-insensitive in MySQL and
MariaDB, so ``engine=innodb`` is accepted and reported with its canonical spelling.

Scanning skips string literals, quoted identifiers and comments, so ``'ENGINE=InnoDB'``
inside a string is not a table option. MySQL-executable comments (``/*!40101 ... */``,
written by mysqldump) are code and are scanned.

Known limitation: ``ENGINE`` followed by a column type (``engine VARCHAR(20)``) is not
treated as a table option; only ``ENGINE=name`` and, for MySQL/MariaDB, ``ENGINE name``
with a known engine name are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

MYSQL_ENGINES: FrozenSet[str] = frozenset({
    "InnoDB", "MyISAM", "MEMORY", "HEAP", "CSV", "ARCHIVE", "BLACKHOLE", "MERGE",
    "MRG_MYISAM", "FEDERATED", "EXAMPLE", "NDBCLUSTER", "NDB", "PERFORMANCE_SCHEMA",
})
MARIADB_EXTRA_ENGINES: FrozenSet[str] = frozenset({
    "Aria", "XtraDB", "ColumnStore", "CONNECT", "OQGRAPH", "ROCKSDB", "MyRocks",
    "SPIDER", "S3", "SEQUENCE", "SPHINX", "MROONGA", "CASSANDRA",
})

ENGINES_BY_DIALECT: Dict[str, FrozenSet[str]] = {
    "mysql": MYSQL_ENGINES,
    "mariadb": MYSQL_ENGINES | MARIADB_EXTRA_ENGINES,
}
MYSQL_LIKE = frozenset(ENGINES_BY_DIALECT)
DEFAULT_ENGINE: Dict[str, str] = {"mysql": "InnoDB", "mariadb": "InnoDB"}

_ENGINE_EQ = re.compile(r"\bENGINE\s*=\s*([A-Za-z_]\w*)", re.IGNORECASE)
_ENGINE_BARE = re.compile(r"\bENGINE\s+([A-Za-z_]\w*)", re.IGNORECASE)


@dataclass(frozen=True)
class EngineClause:
    offset: int
    name: str                 # as written in the file
    canonical: Optional[str]  # canonical spelling if the engine is known for the dialect
    problem: Optional[str]    # None | "unknown_engine" | "not_supported"


def _code_regions(sql: str, dialect: str) -> List[Tuple[int, int]]:
    """Half-open ranges of ``sql`` that are code, not string/identifier/comment text."""
    regions: List[Tuple[int, int]] = []
    n = len(sql)
    mysql_like = dialect in MYSQL_LIKE
    start = 0
    i = 0

    def skip_quoted(pos: int, quote: str) -> int:
        j = pos + 1
        while j < n:
            ch = sql[j]
            if mysql_like and quote in "'\"" and ch == "\\":
                j += 2
                continue
            if ch == quote:
                if j + 1 < n and sql[j + 1] == quote:  # doubled quote escapes itself
                    j += 2
                    continue
                return j + 1
            j += 1
        return n

    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if (c == "-" and nxt == "-") or (c == "#" and mysql_like):
            if i > start:
                regions.append((start, i))
            end = sql.find("\n", i)
            i = n if end < 0 else end + 1
            start = i
        elif c == "/" and nxt == "*":
            if i > start:
                regions.append((start, i))
            if mysql_like and sql.startswith("/*!", i):
                body = i + 3
                while body < n and sql[body].isdigit():
                    body += 1
                end = sql.find("*/", body)
                end = n if end < 0 else end
                regions.append((body, end))
                i = end + 2
            else:
                end = sql.find("*/", i + 2)
                i = n if end < 0 else end + 2
            start = i
        elif c in "'\"`" or (c == "[" and dialect == "mssql"):
            if i > start:
                regions.append((start, i))
            if c == "[":
                close = sql.find("]", i + 1)
                i = n if close < 0 else close + 1
            else:
                i = skip_quoted(i, c)
            start = i
        else:
            i += 1
    if n > start:
        regions.append((start, n))
    return regions


def engine_clauses(sql: str, dialect: str) -> List[EngineClause]:
    """Every ``ENGINE`` table option in ``sql`` with its validation result."""
    if dialect in MYSQL_LIKE:
        known = ENGINES_BY_DIALECT[dialect]
        lookup = {name.lower(): name for name in known}
    else:
        known = MYSQL_ENGINES | MARIADB_EXTRA_ENGINES
        lookup = {name.lower(): name for name in known}

    found: Dict[int, EngineClause] = {}
    for start, end in _code_regions(sql, dialect):
        for match in _ENGINE_EQ.finditer(sql, start, end):
            name = match.group(1)
            canonical = lookup.get(name.lower())
            if dialect in MYSQL_LIKE:
                problem = None if canonical else "unknown_engine"
            else:
                # Outside MySQL/MariaDB only real MySQL engine names are flagged, so
                # `SET engine = 'x'` or a column called engine is not reported.
                if canonical is None:
                    continue
                problem = "not_supported"
            found[match.start(1)] = EngineClause(match.start(1), name, canonical, problem)
        if dialect in MYSQL_LIKE:
            for match in _ENGINE_BARE.finditer(sql, start, end):
                canonical = lookup.get(match.group(1).lower())
                if canonical:
                    found.setdefault(match.start(1), EngineClause(match.start(1), match.group(1), canonical, None))
    return [found[key] for key in sorted(found)]


def default_engine(dialect: str) -> Optional[str]:
    return DEFAULT_ENGINE.get(dialect)
