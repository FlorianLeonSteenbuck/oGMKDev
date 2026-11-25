# Howl in oGMKDev

This directory is a copy of the Howl editor source (https://github.com/howl-editor/howl, commit
`3fc0227`, MIT license, see `LICENSE.md`) with the changes below. The oGMKDev editor window is this
Howl window: one editor view per instance, started with the files on the command line. Build it with
`packaging/build-howl.sh`.

## What oGMKDev changes compared to upstream

- **One instance per start, files handed over.** Starting `howl file` while Howl already runs hands the
  file to the running instance (`lib/howl/application.moon`, `lib/howl/init.lua`). `--new-instance` starts
  a separate instance, which opens its own window. `file:line` and `file:line:col` work as upstream.
- **No project management.** `lib/howl/project.moon` is reduced to the folder that contains a file (the
  home folder for files without one). There are no open projects, project roots, environment files or
  project commands. The commands `project-open`, `project-switch-buffer`, `project-exec`,
  `project-build`, `project-file-search` and `project-file-search-list` are removed, and so are their keys.
- **No splits and no window commands.** The `view-*` commands (left, right, up, down, wraparound,
  or-create, new, close, next) and `window-toggle-fullscreen` / `window-toggle-maximized` are removed,
  together with their keys (`lib/howl/commands/ui_commands.moon`, `lib/howl/keymap.moon`).
- **No command line.** The `alt_x` / `ctrl_meta_x` key that opened the command entry is removed. The
  command panel is only shown while an interaction runs (search, prompts); it is not shown when idle.
- **No status line.** The bottom status line (`Howl ready.`, cursor position) is not added to the window
  (`lib/howl/ui/window.moon`).
- Goto definition and goto reference fall back to a message instead of the removed project search
  (`lib/howl/commands/edit_commands.moon`).

## Bundle `ogmkdev` (bundles/ogmkdev)

- **TODOs in comments.** Words from `ogmkdev_todo_keywords` (default `FIXME:1,XXX:2,HACK:2,TODO:3,NOTE:5`,
  the number is the priority, 1 the most urgent) are highlighted when they are inside a comment, using the
  lexer's comment style. Each priority has its own colour; `ogmkdev_todo_highlight = off` turns the
  highlight off. The highlight is computed when a file is opened.
- **TODO overview.** Ctrl+Alt+T lists the TODOs of all open buffers, sorted by priority, file and line;
  Enter jumps to the line.
- **Custom highlighting.** `ogmkdev_highlights` in the Howl configuration takes `text=#colour` pairs
  separated by `;`, e.g. `console.log=#ffb86c;DEPRECATED=#ff5555`. Every occurrence of the text is
  highlighted in every buffer, when the file is opened. The text is matched literally, not as a regex.

## Known gaps

- The Language Server Protocol parts of Howl are still there; oGMKDev does not use them.
- The TODO and custom highlights are computed when a file is opened; they do not follow edits yet.
- The TODO overview covers the open buffers only, not the files of a folder.
- Multi-cursor selection is not built yet.
