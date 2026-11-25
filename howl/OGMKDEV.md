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

## Known gaps

- The Language Server Protocol parts of Howl are still there; oGMKDev does not use them.
- Specs for the removed features are removed or fail (see the commit that introduced this directory).
