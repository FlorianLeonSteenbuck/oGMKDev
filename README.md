# ogmkdev

Schlanke IDE-Basis in **Python + GTK 3** (PyGObject, GtkSourceView 3). Der Code ist bewusst klein
gehalten und in Module mit Tests aufgeteilt.

## Stand in einem Blick

| Bereich | Modul | Stand |
|---|---|---|
| Konfiguration nur über EditorConfig | `ogmkdev/editorconfig.py` | fertig: Glob-Semantik, Hierarchie, `unset`, `root = true`, Normalisierung |
| Spracherkennung inkl. `.mustache.html`, `.twig.html`, `<name>.mysql.sql`, Shebang, EditorConfig-Scoping | `ogmkdev/languages.py` | fertig |
| Heredoc/Nowdoc nach PHP-Regeln | `ogmkdev/heredoc.py` | fertig, gegen `php -l` geprüft |
| SQL-Dialekte, `ENGINE=InnoDB` (MySQL/MariaDB) | `ogmkdev/sql.py` | fertig (Engine-Tabelle, Groß/Klein, Kommentare und Strings übersprungen) |
| Diagnosen für den Editor (Heredoc, SQL-Engine) | `ogmkdev/diagnostics.py` | fertig |
| Variablenbasierte Vorlagen als einzige Completion-Quelle | `ogmkdev/templates.py` | fertig (Ctrl+Space im Fenster) |
| JetBrains-Run-Konfigurationen (XML, `.run/`, `.idea/runConfigurations/`) | `ogmkdev/runconfig.py` | fertig: lesen, schreiben, unbekannte Elemente bleiben erhalten |
| Debugger-Schnittstelle (Breakpoints, Watches, Step, Events) | `ogmkdev/debug/base.py` | fertig, angelehnt an KDevelops `IDebugSession` |
| GDB über GDB/MI | `ogmkdev/debug/gdb_mi.py` | fertig, Integrationstest mit echtem gdb 15 |
| XDebug über DBGp | `ogmkdev/debug/dbgp.py` | fertig, Integrationstest mit PHP 8.3 + XDebug |
| GTK-Editorfenster | `ogmkdev/ui/app.py` | Grundfunktion: Öffnen, Speichern, Diagnosen, Vorlagen, Run-Liste |
| KDevelop-Anbindung: `.kdev4` lesen | `ogmkdev/bridges/kdevelop.py` | fertig (liest `vendor/kdevelop/kdevelop.kdev4`) |
| KDevelop-Anbindung: C++-Testdaten als Prüforakel für den MI-Parser | `ogmkdev/bridges/kdevelop.py` | fertig, alle MI-Transkripte aus KDevelops Tests werden geparst |
| KDevelop-C++-Parser (`plugins/clang`) einbinden | – | **offen**, braucht Build von KDevelop gegen Qt und KDE-Frameworks |

## Sprachabdeckung und Herkunft

Die Sprache für Syntax und Analyse kommt aus dem KDevelop-Quellcode, wo KDevelop sie mitbringt.
Wo KDevelop nichts liefert, kommt der Code aus den Python-Modulen. Howl ist nicht im Weg.

| Sprache | Herkunft heute | Ziel |
|---|---|---|
| C++ | KDevelop `plugins/clang` (libclang) | Build von KDevelop, danach Anbindung. **Noch nicht gebunden.** |
| ECMAScript / JS / JSX | KDevelop `plugins/qmljs` (QML/JS-Parser aus `qmljs.g`) | Build nötig. Dialekte (ES3 bis ES2024, JScript) per Scope. |
| qmake | KDevelop `plugins/qmakemanager/parser/qmake.g` | optional |
| Python 2, Python 3, PyPy | GtkSourceView `python`/`python3`, Dialekt per Shebang oder Scope | Dialekt-Erkennung fertig, eigener Parser offen |
| PHP | `heredoc.py` (Heredoc-Diagnose), GtkSourceView `php` | eigener PHP-Parser offen |
| TypeScript, TSX | GtkSourceView `js` als Näherung | eigener Parser offen |
| SQL (Oracle, Apache Hive, MySQL, MariaDB, MSSQL, PostgreSQL) | `sql.py` (Engine-Prüfung), GtkSourceView `sql` generisch | **Ansatz offen** (siehe Entscheidungen) |
| Mustache, Twig | Erkennung über Doppelendungen, Vorlagen in `templates.py` | Highlighting über Basissprache, eigener Parser offen |
| Markdown, HTML, JSON, CSS | GtkSourceView | ausreichend für den Start |
| Java | ausgeschlossen | – |
| C und kompilierte Sprachen | nicht als Sprache unterstützt (C-Fixture nur für gdb-Tests) | – |

Howl wird nicht verwendet, weder seine Lexer noch seine Lua-Umgebung. Das Submodul wurde entfernt.

## Konfiguration

Die einzige Konfigurationsdatei ist `.editorconfig`. Sprach-Scoping läuft über eigene Schlüssel:

```ini
[*.{php,mustache.html}]
ogmkdev_language = php

[*.sql]
ogmkdev_language = mysql        # oder: ogmkdev_language = sql + ogmkdev_dialect = mariadb

[*.js]
ogmkdev_language = wscript      # JScript, ECMAScript-Dialekt
```

Run- und Debug-Konfigurationen sind JetBrains-XML unter `.run/*.run.xml`.

## Start und Tests

Der Python-Interpreter mit PyGObject liegt unter `/usr/bin/python3.12`. Der Standard-`python3`
(3.13) hat kein `gi`.

```bash
git submodule update --init --depth 1 vendor/kdevelop
/usr/bin/python3.12 -m unittest discover -s tests -t .
xvfb-run -a /usr/bin/python3.12 -m unittest discover -s tests -t .   # mit GTK-Smoke-Tests
/usr/bin/python3.12 -m ogmkdev pfad/zur/datei.php                    # Editorfenster starten
```

Benötigt auf dem System: `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-gtksource-3.0`, `gdb`,
für die Integrationstests zusätzlich `gcc`, `php-cli` mit `php-xdebug`.

## Entscheidungen und offene Punkte

1. **KDevelop-C++ bauen.** Der C++-Parser (`plugins/clang`) und der QML/JS-Parser brauchen Qt und
   KDE-Frameworks. Zum Bauen fehlen Entwicklungspakete. Ich habe die Installation in dieser Session
   nicht ausgeführt, weil Paketinstallationen nicht freigegeben sind. Die Freigabe ist nötig.
2. **Lizenz.** KDevelop ist GPL-lizenziert. Sobald KDevelop-Code gelinkt wird, muss die Lizenz
   von ogmkdev dazu passen. Bisher ist keine Lizenz gesetzt.
3. **SQL.** Für SQL und Datenbanken ist ein anderer Ansatz denkbar als der heutige Stand.
   Welche Richtung soll es sein?
4. **Fork.** Ein GitHub-Fork von `KDE/kdevelop` konnte in dieser Session nicht angelegt werden
   (keine Schreibrechte auf die Upstream-Repos). Das Submodul zeigt auf den Upstream, fixiert auf
   Commit `e09ea0cf`. Soll stattdessen dein eigener Fork hinein?
5. **„BareDown“.** Ich habe das nicht zugeordnet. Ist Markdown gemeint oder eine eigene Syntax?
