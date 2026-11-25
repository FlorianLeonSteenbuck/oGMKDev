"""The menu bar of the frame: short and clean. Only entries that work are listed.

Each entry is (label, action name, accelerator, target). A target is either the name of a Window
method, or "howl:<command>" for a Howl command that runs in the editor that has the focus.
The Howl editor takes its own keys first, so accelerators are only given where Howl does not use them.
"""

MENUS = (
    ("File", (
        ("New Editor", "new-editor", "", "add_editor"),
        ("Open...", "open", "", "open_dialog"),
        ("Quick Open...", "quick-open", "<Control>p", "quick_open"),
        ("Save", "save", "", "howl:save"),
        ("Save As...", "save-as", "", "howl:save-as"),
        ("Close Tab", "close-tab", "", "howl:buffer-close"),
        ("Quit", "quit", "<Control>q", "quit_frame"),
    )),
    ("Edit", (
        ("Undo", "undo", "", "howl:editor-undo"),
        ("Redo", "redo", "", "howl:editor-redo"),
        ("Find...", "find", "", "howl:buffer-search-forward"),
        ("Search Everywhere...", "search-everywhere", "<Control><Shift>a", "search_everywhere"),
    )),
    ("View", (
        ("Split Right", "split-right", "", "split_right"),
        ("Close Pane", "close-pane", "", "close_active_pane"),
    )),
    ("Project", (
        ("Show Git Changes", "show-git", "<Control><Alt>g", "show_git"),
        ("Show TODOs", "show-todos", "<Control><Alt>t", "show_todos"),
    )),
    ("Run", (
        ("Run Configuration", "run-configuration", "", "run_selected"),
        ("Stop Process", "stop-process", "", "stop_process"),
    )),
    ("Help", (
        ("About", "about", "", "show_about"),
    )),
)

# Entries that are not listed; kept for the status line when a method is missing
PENDING = {
    "split_right": "split right", "close_active_pane": "close pane",
    "search_everywhere": "search everywhere", "quick_open": "quick open",
}
