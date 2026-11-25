"""Colours of the frame and of Howl's editor, both from the palettes in ogmkdev/theme.py.

The frame gets GTK 4 CSS for its own chrome; Howl gets a Howl theme file (CSS with the editor's
style names) that is registered and selected in the editor (see HOWL_EMBED_THEME in application.moon).
"""

from __future__ import annotations

import os
from typing import Dict

from .. import theme as palettes

# Howl style names and the palette entries they take (style name, palette key)
HOWL_STYLES = (
    ("default", "foreground"), ("comment", "comment"), ("keyword", "keyword"), ("string", "string"),
    ("number", "number"), ("operator", "operator"), ("regex", "regexp"), ("variable", "variable"),
    ("key", "attribute"), ("function", "heading"), ("type", "engine"), ("member", "attribute"),
    # BareDown (howl/bundles/baredown): the block markers and the inline spans
    ("heading", "heading"), ("marker", "marker"), ("bullet", "bullet"), ("ordered", "ordered"),
    ("quote", "quote"), ("rule", "rule"), ("fence", "fence"), ("code", "code"), ("link", "link"),
    ("bold", "foreground"), ("italic", "foreground"),
)
# The text properties of a style, in Howl's theme keys (font-weight, font-style, text-decoration)
HOWL_STYLE_FONTS = {
    "heading": "font-weight: bold;", "marker": "font-weight: bold;", "bold": "font-weight: bold;",
    "italic": "font-style: italic;", "quote": "font-style: italic;", "link": "text-decoration: underline;",
}


def frame_css(mode: str, scheme: str) -> str:
    colors = palettes.palette(mode, scheme)
    return palettes.css(colors) + "\n" + "\n".join([
        f".ogmkdev-frame .ogmkdev-statusbar {{ background-color: {colors['chrome']}; "
        f"color: {colors['chrome_text']}; padding: 3px 8px; }}",
        f".ogmkdev-frame .ogmkdev-toolbar {{ background-color: {colors['chrome']}; padding: 2px 4px; }}",
        f".ogmkdev-frame .ogmkdev-statusbar label {{ color: {colors['chrome_text']}; }}",
        "",
    ])


def howl_css(mode: str, scheme: str) -> str:
    colors = palettes.palette(mode, scheme)
    variables = "\n".join(f"  --{key.replace('_', '-')}: {value};" for key, value in colors.items())
    rules = [
        ":root {", variables, "}",
        f"window {{ background-color: {colors['background']}; }}",
        f".content-box {{ background-color: {colors['background']}; }}",
        f".gutter {{ background-color: {colors['gutter_background']}; color: {colors['gutter_foreground']}; }}",
        f".indicator {{ background-color: {colors['chrome']}; color: {colors['chrome_text']}; }}",
        f"flair.current_line {{  shape: rectangle; background-color: {colors['current_line']}; }}",
        # thin scrollbar in the text colour, no bright track
        # same selectors as Howl's own themes, so they win over the default scrollbar
        f"scrollbar range trough {{ background-color: transparent; }}",
        f"scrollbar range trough slider {{ min-width: 6px; min-height: 6px; border-radius: 3px; "
        f"background-color: alpha({colors['foreground']}, 0.22); }}",
        f"scrollbar range {{ background-color: transparent; }}",
        f"flair.search {{  shape: rectangle; background-color: {colors['selection']}; }}",
        # the edge line (eclipse-style margin) at the column of the file's max_line_length
        f"flair.edge_line {{ shape: pipe; border-color: {colors['gutter_foreground']}; width: 1px; }}",
        f"flair.list-selection {{  shape: rectangle; background-color: {colors['selection']}; }}",
        # the editor is the editing surface only: no title bar, no processes, activity or inspection
        # indicators; the cursor position (footer) stays
        # GTK 4 CSS has no display property: the extra indicators are made empty and transparent
        ".indicator.processes, .indicator.activity, .indicator.inspections {"
        " min-width: 0; min-height: 0; margin: 0; padding: 0; opacity: 0; }",
    ]
    for style, key in HOWL_STYLES:
        fonts = f" {HOWL_STYLE_FONTS[style]}" if style in HOWL_STYLE_FONTS else ""
        rules.append(f"style.{style} {{ color: {colors[key]};{fonts} }}")
    return "\n".join(rules) + "\n"


def write_howl_theme(mode: str, scheme: str, folder: str) -> str:
    """Writes the Howl theme file for mode and scheme into ``folder`` and returns its path."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"ogmkdev-{mode}-{scheme}.css")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(howl_css(mode, scheme))
    return path


def theme_name(mode: str, scheme: str) -> str:
    return f"oGMKDev {mode.capitalize()} {scheme.capitalize()}"


def palette_for(mode: str, scheme: str) -> Dict[str, str]:
    return palettes.palette(mode, scheme)


# Colours of the folder roles in the tree (ogmkdev/workspace.py): test, source, build, artifacts, assets
ROLE_COLOURS = {
    "light": {"source": "#0969da", "test": "#1a7f37", "build": "#9a6700", "artifacts": "#8250df",
              "assets": "#bf3989"},
    "dark": {"source": "#58a6ff", "test": "#3fb950", "build": "#d29922", "artifacts": "#a371f7",
             "assets": "#f778ba"},
}


def role_colour(mode, role):
    """The colour of a folder role in light or dark mode, None when the role has none."""
    return ROLE_COLOURS.get(mode, ROLE_COLOURS["light"]).get(role)
