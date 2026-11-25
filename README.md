# ogmkdev

A lightweight code editor written in Python with GTK 3 (PyGObject and GtkSourceView 3).
The window follows the layout of KDevelop: menu bar, icon toolbar, tool panels around a tabbed
editor, and a status bar. The product is the editor; its base is the KDevelop source tree in
`kdevelop/`, which is rewritten into Python module by module, plus the Python modules in `ogmkdev/`.

Pure source: no build system beyond `pyproject.toml`, no service, no plugin host, no external
grammar or language server. Every language here is implemented in this repository.

## The editor

- Menu bar (File, Edit, Run, Debug, Help) and icon toolbar, both generated from one action table
  (`ACTIONS` in `ogmkdev/ui/app.py`).
- Left panel: project files (lazy tree) and run configurations. Bottom panel: console and watches.
- Tabs with new, open, save, save as, close, and a `*` marker for unsaved changes.
- EditorConfig applied on open and save: indent, tab width, line endings, charset, trailing
  whitespace, final newline. Scoping keys: `ogmkdev_language`, `ogmkdev_dialect`.
- Language detection with compound extensions (`page.mustache.html`, `schema.mysql.sql`),
  shebang lines and EditorConfig overrides.
- Own syntax highlighting (`ogmkdev/highlight.py`) for ECMAScript, BareDown and SQL.
- Diagnostics in the status line: ECMAScript lexical errors, BareDown unclosed code blocks,
  PHP heredoc errors, and SQL `ENGINE=` checks (MySQL and MariaDB engine names).
- Variable-based template completion (Ctrl+Space). Templates are the only completion source.
- Breakpoints (F9) in the gutter, run configurations, and GDB (GDB/MI) and XDebug (DBGp)
  debugging: continue, step over, step into, step out, stop, watch expressions, current-line marker.
- Find next, undo and redo.

## Keys

| Key | Action |
|---|---|
| Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+W | new / open / save / close tab |
| Ctrl+F | focus the find bar; Enter for next match |
| Ctrl+Space | expand the template whose trigger precedes the cursor |
| Ctrl+Z / Ctrl+Y | undo / redo |
| F9 | toggle breakpoint on the cursor line |
| F5 | run the selected configuration, or continue when debugging |
| F10 / F11 / Shift+F11 | step over / step into / step out |

## BareDown: our own markup language

BareDown is not Markdown. Its grammar is line based, implemented in `ogmkdev/baredown.py`:

| Syntax | Meaning |
|---|---|
| `= Title` | heading, level 1 (`==` level 2, up to six `=`) |
| `**bold**` | bold text |
| `//italic//` | italic text |
| `\|code\|` | inline code |
| `[[Page]]`, `[[Page\|label]]` | link to a page, optional label |
| `- item` | bullet list item |
| `+ item` | ordered list item |
| `> text` | block quote |
| `%% text` | comment, not rendered |
| `----` | horizontal rule (four or more dashes alone on a line) |
| `~~~ lang` … `~~~` | fenced code block; the language is optional |

Paragraphs are lines up to the next blank line. Files use the extensions `.bd` and `.baredown`.
`baredown.to_html()` renders a document; `baredown.problems()` reports unclosed code blocks.

## Languages

| Language | Current source | Next step |
|---|---|---|
| ECMAScript (JavaScript) | tokenizer ported from KDevelop's QML/JS lexer (`kdevelop/plugins/qmljs`), own highlighting and diagnostics | port the parser (`qmljs.g`) |
| BareDown | own tokenizer, parser and HTML renderer | - |
| SQL (Oracle, Apache Hive, MySQL, MariaDB, MSSQL, PostgreSQL) | lexer rules and keyword list ported from Howl, `ENGINE=` checks, own highlighting | dialect-specific keyword sets |
| PHP | heredoc and nowdoc scanner, diagnostics; highlighting by GtkSourceView | own parser |
| Python 2 / 3 / PyPy | dialect detection; highlighting by GtkSourceView | own parser |
| TypeScript, JSX, TSX | GtkSourceView JavaScript grammar as an approximation | own lexer |
| Mustache, Twig | detection of compound extensions, templates; highlighting of the base language | own grammar |
| Markdown, HTML, JSON, CSS | GtkSourceView | none yet |
| C++ | KDevelop `plugins/clang` in the source tree | rewrite to Python or bind |
| Java | excluded | - |

## Base and source origins

- `kdevelop/` is a copy of https://github.com/KDE/kdevelop at commit `e09ea0cf`, imported as plain
  source. The GitHub fork relation is not set up; `kdevelop/FORK.md` records the pin.
- The ECMAScript lexer in `ogmkdev/lexers/ecmascript_lexer.py` is a port of
  `kdevelop/plugins/qmljs/.../qmljslexer.cpp`. Differences are documented in the module.
- The SQL lexer rules and keyword list in `ogmkdev/lexers/` are ported from Howl
  (https://github.com/howl-editor/howl, MIT). Howl's runtime is not used.
- The GDB/MI parser is tested against the transcripts in KDevelop's own tests
  (`kdevelop/plugins/debuggercommon/tests`, `kdevelop/plugins/gdb/unittests`).
- Attribution: `THIRD_PARTY_NOTICES.md`.

## License

The project is distributed under the **GNU GPL, version 2 or later** (`LICENSE`).

Rewritten KDevelop code is a derivative work of GPL-licensed code, so the combined project must be
GPL-compatible. An MIT license is only possible for code written from scratch without KDevelop
sources. Howl's MIT-licensed parts fit into a GPL project.

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

## Layout of the repository

| Path | Contents |
|---|---|
| `ogmkdev/ui/app.py` | editor window: menus, toolbar, tabs, panels, debugging |
| `ogmkdev/document.py` | document model (text, settings, language, diagnostics), no GUI |
| `ogmkdev/highlight.py` | highlighting spans from our own tokenizers, tag styles |
| `ogmkdev/baredown.py` | BareDown parser, tokenizer, HTML renderer |
| `ogmkdev/lexers/` | ECMAScript lexer (from KDevelop), SQL lexer and keywords (from Howl) |
| `ogmkdev/editorconfig.py` | EditorConfig parser, globs, hierarchy, settings |
| `ogmkdev/languages.py` | language registry and detection |
| `ogmkdev/heredoc.py`, `ogmkdev/sql.py` | PHP heredoc scanner, SQL dialects and engines |
| `ogmkdev/diagnostics.py` | diagnostics built from the modules above |
| `ogmkdev/templates.py` | variable-based templates |
| `ogmkdev/runconfig.py` | JetBrains run configuration model (XML) |
| `ogmkdev/debug/` | debugger interface, GDB/MI backend, DBGp (XDebug) backend |
| `ogmkdev/bridges/kdevelop.py` | reads `.kdev4` (KConfig) and extracts KDevelop's GDB/MI transcripts |
| `ogmkdev/editing.py` | line handling and charset on save |
| `kdevelop/` | KDevelop source tree (see `kdevelop/FORK.md`), the base being rewritten |
| `tests/` | unit tests and integration tests (GDB, XDebug, GTK under Xvfb) |

## Run and test

Use the interpreter that has PyGObject: `/usr/bin/python3.12` (the default `python3` has no `gi`).

```bash
/usr/bin/python3.12 -m unittest discover -s tests -t .
xvfb-run -a /usr/bin/python3.12 -m unittest discover -s tests -t .    # includes GTK tests
/usr/bin/python3.12 -m ogmkdev path/to/file_or_folder                  # start the editor
```

System packages: `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-gtksource-3.0`, and an icon theme with
the standard action icons (Humanity or Adwaita). The integration tests use `gdb`, `gcc`, and
`php-cli` with `php-xdebug` when installed; otherwise they are skipped.

## Open items

- Port the ECMAScript parser (`qmljs.g` tables and actions) so the editor gets an AST and outline.
- Dialect-specific SQL keyword sets; TypeScript and JSX lexers.
- Breakpoints do not move when lines are inserted above them.
- XDebug has no UI test yet; the end-to-end test covers GDB only.
- The debug console shows raw engine output; there is no structured variables view.
