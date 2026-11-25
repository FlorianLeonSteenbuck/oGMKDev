# ogmkdev

A lightweight code editor written in Python with GTK 3 (PyGObject and GtkSourceView 3).
The product is the editor. The base it is built on is the KDevelop source tree in `kdevelop/`,
which is being rewritten into Python module by module, plus the Python core modules in `ogmkdev/`.

Pure source: no build system beyond `pyproject.toml`, no service, no plugin host.

## What the editor does today

- Tabs with several documents, new / open / save / save as / close, unsaved marker (`*`).
- Project file tree (lazy loading) with `.editorconfig` and `.run/` visible.
- EditorConfig applied on open and save: indent, tab width, line endings, charset, trailing
  whitespace, final newline. Language scoping keys: `ogmkdev_language`, `ogmkdev_dialect`.
- Language detection with compound extensions (`page.mustache.html`, `schema.mysql.sql`),
  shebang detection, and EditorConfig overrides.
- Diagnostics in the status line: heredoc/nowdoc errors for PHP (`<<<LABEL ... LABEL;` rules),
  `ENGINE=` checks for SQL dialects (MySQL and MariaDB engine names).
- Variable-based template completion (Ctrl+Space). Templates are the only completion source.
- Breakpoints (F9) shown in the gutter.
- JetBrains-compatible run configurations (`.run/*.run.xml`, `.idea/runConfigurations/*.xml`).
  Run executes the command and streams its output into the console.
- Debugging with GDB (GDB/MI) and XDebug (DBGp): start, continue, step over, step into,
  step out, stop, watch expressions, current-line marker.
- Find next (Enter in the find bar), undo and redo.

## Keys

| Key | Action |
|---|---|
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+W | new / open / save / close tab |
| Ctrl+F | focus find bar, Enter for next match |
| Ctrl+Space | expand the template whose trigger precedes the cursor |
| Ctrl+Z / Ctrl+Y | undo / redo |
| F9 | toggle breakpoint on the cursor line |
| F5 | run the selected configuration, or continue when debugging |
| F10 / F11 / Shift+F11 | step over / step into / step out |

## Layout of the repository

| Path | Contents |
|---|---|
| `ogmkdev/ui/app.py` | GTK editor window |
| `ogmkdev/document.py` | document model (text, settings, language, diagnostics), no GUI |
| `ogmkdev/editorconfig.py` | EditorConfig parser, globs, hierarchy, settings |
| `ogmkdev/languages.py` | language registry and detection |
| `ogmkdev/heredoc.py` | PHP heredoc and nowdoc scanner |
| `ogmkdev/sql.py` | SQL dialects and the `ENGINE` table option |
| `ogmkdev/lexers/` | SQL lexer ported from Howl's rules, with the keyword list |
| `ogmkdev/diagnostics.py` | diagnostics built from the modules above |
| `ogmkdev/templates.py` | variable-based templates |
| `ogmkdev/runconfig.py` | JetBrains run configuration model (XML) |
| `ogmkdev/debug/` | debugger interface, GDB/MI backend, DBGp (XDebug) backend |
| `ogmkdev/bridges/kdevelop.py` | reads `.kdev4` (KConfig) and extracts KDevelop's GDB/MI test transcripts |
| `ogmkdev/editing.py` | line handling and charset on save |
| `kdevelop/` | KDevelop source tree (see `kdevelop/FORK.md`), the base to rewrite |
| `tests/` | unit tests and integration tests (GDB, XDebug, GTK) |

## Base and source origins

- `kdevelop/` is a copy of https://github.com/KDE/kdevelop at commit `e09ea0cf`. It is imported
  as plain source. The GitHub fork relation is not set up; `kdevelop/FORK.md` records the pin.
- The SQL lexer rules and keyword list in `ogmkdev/lexers/` are ported from Howl
  (https://github.com/howl-editor/howl, MIT). Howl's runtime is not used.
- The MI debugger parser is tested against the GDB/MI transcripts from KDevelop's own tests
  (`kdevelop/plugins/debuggercommon/tests`, `kdevelop/plugins/gdb/unittests`).
- Attribution is in `THIRD_PARTY_NOTICES.md`.

### Language coverage

| Language | Current source | Next step |
|---|---|---|
| Python 2 / 3 / PyPy | GtkSourceView highlighting, dialect detection | own parser |
| PHP | heredoc diagnostics, GtkSourceView highlighting | own parser |
| ECMAScript, JSX, TypeScript, TSX | GtkSourceView (JavaScript grammar as approximation) | rewrite KDevelop `plugins/qmljs` lexer and parser |
| SQL (Oracle, Apache Hive, MySQL, MariaDB, MSSQL, PostgreSQL) | Howl-style lexer, `ENGINE` checks | connect the lexer to highlighting |
| Mustache, Twig | detection and templates, highlighting of the base language | own grammar |
| Markdown, HTML, JSON, CSS | GtkSourceView | none yet |
| C++ | KDevelop `plugins/clang` in the source tree | rewrite to Python, or bind it |
| Java | excluded | - |

## License

The project is distributed under the **GNU GPL, version 2 or later** (`LICENSE`).

The reason is the KDevelop source: rewritten KDevelop code is a derivative work of GPL-licensed
code, so the combined project must be GPL-compatible. An MIT license is only possible for code
written from scratch without KDevelop sources. Howl's MIT-licensed parts fit into a GPL project.

## Configuration

The only configuration file format is `.editorconfig`:

```ini
[*.{php,mustache.html}]
ogmkdev_language = php

[*.sql]
ogmkdev_language = sql
ogmkdev_dialect = mariadb

[*.js]
ogmkdev_language = wscript      # JScript dialect of ECMAScript
```

Run and debug configurations are JetBrains XML under `.run/*.run.xml`. Debug configurations use
the types `OgmkdevGdbConfigurationType` (options `PROGRAM`, `ARGUMENTS`, `WORKING_DIRECTORY`) and
`OgmkdevXdebugConfigurationType` (options `SCRIPT_NAME`, `PORT`).

## Run and test

Use the interpreter that has PyGObject: `/usr/bin/python3.12` (the default `python3` has no `gi`).

```bash
/usr/bin/python3.12 -m unittest discover -s tests -t .
xvfb-run -a /usr/bin/python3.12 -m unittest discover -s tests -t .    # includes GTK tests
/usr/bin/python3.12 -m ogmkdev path/to/file_or_folder                  # start the editor
```

System packages: `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-gtksource-3.0`. The integration tests use
`gdb`, `gcc`, and `php-cli` with `php-xdebug` when those are installed; otherwise they are skipped.

## Open items

- Rewrite KDevelop's language code into Python (ECMAScript first, then C++ or drop it).
- Use the SQL lexer tokens for highlighting instead of the generic GtkSourceView SQL grammar.
- Breakpoints do not move when lines are inserted above them.
- XDebug has no UI test yet; the end-to-end test covers GDB only.
- The debug console shows raw engine output; there is no structured variables view.
