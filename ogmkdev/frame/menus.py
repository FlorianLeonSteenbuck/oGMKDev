"""The menu bar of the frame. Each entry is (label, action name, accelerator, target): a target is
the name of a Window method, or "howl:<command>" for a Howl command in the focused editor."""

MENUS = (
    ("File", (
        ("New Editor", "new-editor", "", "add_editor"),
        ("New File from Template...", "new-file-template", "", "new_file_from_template"),
        ("New Class...", "new-class", "", "new_class"),
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
        ("Fold or Unfold Block", "toggle-fold", "<Control>period", "howl:fold-toggle"),
        ("Search Everywhere...", "search-everywhere", "<Control><Shift>a", "search_everywhere"),
        ("Generate Doc Comment", "generate-doc", "<Control><Alt>d", "generate_doc_comment"),
    )),
    ("View", (
        ("Split Right", "split-right", "", "split_right"),
        ("Split Down", "split-down", "", "split_down"),
        ("Split into Four", "split-four", "", "split_four"),
        ("Split into Six", "split-six", "", "split_six"),
        ("Close Pane", "close-pane", "", "close_active_pane"),
    )),
    ("Tools", (
        ("Search in Files...", "search-in-files", "<Control><Shift>f", "focus_find"),
        ("Go to Definition...", "go-to-definition", "", "go_to_definition"),
        ("Find Implementations", "find-implementations", "", "find_implementations"),
        ("Show Type Hierarchy", "show-hierarchy", "", "show_hierarchy"),
        ("Show Structure", "show-structure", "<Control><Alt>s", "show_structure"),
        ("New React Component...", "new-react", "", "new_react_component"),
        ("New Vue Component...", "new-vue", "", "new_vue_component"),
        ("New Svelte Component...", "new-svelte", "", "new_svelte_component"),
        ("New Angular Component...", "new-angular", "", "new_angular_component"),
        ("New Lit Component...", "new-lit", "", "new_lit_component"),
        ("Inspect Folder", "inspect-folder", "", "inspect_folder"),
        ("Refresh Index", "refresh-index", "", "refresh_index"),
        ("Clear Index and Rebuild", "clear-index", "", "clear_index"),
        ("Show Git Changes", "show-git", "<Control><Alt>g", "show_git"),
        ("Show Current File in Files", "reveal-file", "", "reveal_current_file"),
        ("Show TODOs", "show-todos", "<Control><Alt>t", "show_todos"),
        ("Export Documentation (HTML)...", "export-docs", "", "export_documentation"),
    )),
    ("Settings", (
        ("Preferences...", "preferences", "", "open_global_settings"),
        ("Error Hinting...", "error-hinting", "", "open_diagnostic_settings"),
    )),
    ("Run", (
        ("Run Configuration", "run-configuration", "", "run_selected"),
        ("Stop Process", "stop-process", "", "stop_process"),
        ("Toggle Breakpoint", "toggle-breakpoint", "F9", "howl:breakpoint-toggle"),
    )),
    ("Help", (
        ("About", "about", "", "show_about"),
    )),
)

# The right-click menu of the editor area, in groups (None separates them). It is a popover of the
# window, so it lies over the Howl editors and the rest of the frame.
CONTEXT_MENU = (
    ("Cut", "ctx-cut", "howl:editor-cut"),
    ("Copy", "ctx-copy", "howl:editor-copy"),
    ("Paste", "ctx-paste", "howl:editor-paste"),
    ("Select All", "ctx-select-all", "howl:editor-select-all"),
    None,
    ("Go to Definition", "ctx-definition", "howl:word-definition"),
    ("Toggle Breakpoint", "ctx-breakpoint", "howl:breakpoint-toggle"),
    ("Fold or Unfold Block", "ctx-fold", "howl:fold-toggle"),
    None,
    ("Show Current File in Files", "ctx-reveal", "reveal_current_file"),
)

# Entries that are not wired yet (their status line says so)
PENDING = {
    "debug_selected": "debugger", "step_over": "debugger step", "step_into": "debugger step",
    "step_out": "debugger step",
}
