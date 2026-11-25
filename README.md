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
- Light and dark mode (View menu or `--dark`), and three color schemes: `blend` (JetBrains
  structure with Eclipse's purple accent, the default), `jetbrains` and `eclipse`
  (`--scheme NAME`). All colors are checked for WCAG contrast in the tests.

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
| ECMAScript (JavaScript) | lexer ported from KDevelop's QML/JS lexer, LALR driver over KDevelop's generated tables (`tools/generate_ecmascript_tables.py`), syntax diagnostics, own highlighting | AST and outline on top of the parse tree |
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

## Project tools

- **Index** (`ogmkdev/index.py`): symbols of PHP (classes, interfaces, traits, enums, functions, methods,
  constants, properties, namespaces and `use` imports resolved), Python and JavaScript/TypeScript
  (classes, interfaces, functions). Files keep their size and modification time: `refresh()` re-reads
  only changed files, saving a file invalidates that file, and a JSON cache keeps the index between
  sessions (`$XDG_CACHE_HOME/ogmkdev/`).
- **Type hierarchy** (Project > Show Type Hierarchy, Ctrl+H): supertypes and subtypes, transitive, and
  the dependencies of the class under the cursor. Items navigate to their declaration on activation.
- **Class diagram**: the Hierarchy panel's "Diagram" tab draws the inheritance levels as columns; each
  class is a button. Built from GTK widgets, so no drawing library is needed.
- **Implementations** (Ctrl+Alt+B): all classes that extend or implement the type under the cursor.
- **Search in files** (Ctrl+Shift+F): text or regular expression over the project, results in the
  Search panel.
- **Inspections** (Project > Inspect Project): diagnostics of every indexed file plus unresolved
  supertypes; results in the Problems panel.

## Settings

Two scopes use the same keys, and both are EditorConfig files:

| Scope | File | Applies to |
|---|---|---|
| Global (Settings > Preferences) | `$XDG_CONFIG_HOME/ogmkdev/.editorconfig` | every file |
| Project (Project > Project Settings) | `.editorconfig` in the project root | files below the root |

A `.editorconfig` in a subdirectory still wins for its files. Setting a value to its default removes
the key, so it is inherited again. Error hinting has its own dialog (Settings > Error Hinting), and
every check can be turned off or set to error, warning or hint:

```ini
[*]
ogmkdev_diagnostics = on
ogmkdev_diagnostic_php_function = warning
ogmkdev_diagnostic_php_match = off        # per PHP feature: ogmkdev_diagnostic_php_<feature>

[*.php]
ogmkdev_dialect = 8.6                     # PHP version of the files
```

## PHP versions

`php_features.py` detects the syntax and library features of PHP 8.0 to 8.6 on a token stream from
`lexers/php_lexer.py`. Each feature is checked against the file's PHP version (`ogmkdev_dialect`).

- 8.0: attributes, nullsafe `?->`, `match`, `throw` as expression, named arguments, constructor
  promotion, `$object::class`, catch without a variable.
- 8.1: enums, readonly properties, first-class callables `f(...)`, `never`, intersection types,
  `0o` octal, `final const`. 8.2: readonly classes, DNF types, `true`/`null`/`false` types.
  8.3: typed class constants, `#[\Override]`, `$c::{$name}`. 8.4: property hooks, asymmetric
  visibility, `new` in a chain without parentheses, `#[\Deprecated]`.
- 8.5: pipe operator `|>`, `clone($x, [...])`, `#[\NoDiscard]`, closures in constant expressions,
  `array_first()` and `array_last()`.
- 8.6: partial function application with the `?` and `...` placeholders, default values for readonly
  properties, `clamp()`, `SortDirection`, `Time\Duration`, `Io\Poll`. Sources: php.net release notes
  for 8.5 and 8.6 and the RFCs they link. Some 8.6 details come from pre-release coverage; check the
  migration guide before relying on an edge case.

## Navigation, inspections and imports

- **Go to Definition** (Ctrl+B): the declaration of the name under the cursor. One match jumps; several
  are listed in the Search panel (classes first, then members with that name).
- **Go to Implementation** (Ctrl+Alt+B): the classes that extend or implement the type under the cursor.
  One implementation jumps; several are listed.
- **Inspections** (Project > Inspect Project) report, besides diagnostics: unused imports (warning),
  imports that the project does not define (hint), and concrete classes that do not implement a method of
  an interface or abstract class they inherit (error).
- **Organise Imports** (Edit > Organize Imports, Ctrl+Alt+O): sorts the top-level PHP `use` statements,
  drops unused ones and keeps `use function` and `use const`. Group imports (`use A\{B, C};`) are left
  alone.

## Workspace and keyboard

- **Workspace** (JetBrains-style): source folders (`ogmkdev_source_roots`), test folders
  (`ogmkdev_test_roots`, shown in a different color) and ignored folders (`ogmkdev_exclude`, hidden from
  the tree and not indexed or searched). Project > Add Folder to Workspace adds further project folders;
  each one is a top-level node in the Files tree.
- **Keymap**: every action can be rebound with `ogmkdev_key_<action> = <accelerator>` in the global or the
  project EditorConfig; `none` removes the shortcut. Example: `ogmkdev_key_save_current = <Primary>s`.
- **Current line** is highlighted with the Eclipse color; switch it off with `ogmkdev_current_line = false`.

## Packaging

`packaging/build-deb.sh` builds `dist/ogmkdev_<version>_all.deb` (tested), and `packaging/build-rpm.sh`
builds the openSUSE `.rpm` from `packaging/ogmkdev.spec` (written, not yet built here). Both use
`packaging/install-tree.sh`. See `packaging/README.md`.

## Templates

Every language has built-in templates (PHP, Python 2/3/PyPy, ECMAScript, TypeScript, TSX, JSX,
SQL with dialect variants, Markdown, BareDown, HTML, JSON, CSS, Mustache, Twig). Ctrl+Space shows
the matching templates; a single match is inserted directly.

Templates are configured in EditorConfig as `ogmkdev_template_<trigger>` properties. Escapes
`\n`, `\t` and `\\` are allowed in the value. Sections select the files, and directories can be
scoped with globs such as `[legacy/**]` or `[**/templates/**]`:

```ini
root = true

[*.php]
ogmkdev_template_fn = fn(${args:$x}) => $0;

[legacy/**]
ogmkdev_language = php                 # every file under legacy/ is PHP
ogmkdev_template_todo = // TODO(legacy): $0
```

A configured template applies to every file its section matches, whatever the language, and
replaces a built-in template with the same trigger. Template bodies use `${name}`,
`${name:default}` for variables and `$0` for the cursor.

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

- Git staging and a "changed files" view, a global search for files, symbols, actions and settings
  (Search Everywhere), quick open of files, and configurable file templates are not built yet.
- Coding-standard checks (trailing whitespace, indentation style, line length, final newline) are not
  added as diagnostics yet; the diagnostic severities are already configurable per check.
- The `.rpm` package is written but has not been built on openSUSE.

- Build an AST on top of the ECMAScript parse tree (outline, navigation).
- The PHP analysis is token based: it recognises each construct, but it is not a full PHP parser.
- Python and JavaScript references are not indexed; only their declarations are.
- The class diagram scrolls but has no zoom and no edge routing yet.
- The settings dialog covers the editor, PHP version and error hinting keys; the theme keys are
  still set from the View menu and command-line options.
- PHP and Python highlighting still comes from GtkSourceView's default scheme; the dark mode
  colors apply to our own languages only. Our own tokenizers for them would fix that.
- Dialect-specific SQL keyword sets; TypeScript and JSX lexers.
- Breakpoints do not move when lines are inserted above them.
- XDebug has no UI test yet; the end-to-end test covers GDB only.
- The debug console shows raw engine output; there is no structured variables view.
