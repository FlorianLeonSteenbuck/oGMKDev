"""Colors for the editor: light and dark modes and three color schemes.

* ``blend`` (default) keeps the structure of JetBrains' default colors and adds Eclipse's purple
  for keywords, markers and accents. Backgrounds carry a slight violet tint.
* ``jetbrains`` and ``eclipse`` replace the syntax colors with those of the two IDEs.

The palettes are plain data. :func:`tag_properties` turns a palette into text-tag properties,
:func:`css` into widget colors, and :func:`contrast_ratio` lets the tests check readability.
"""

from __future__ import annotations

from typing import Dict

MODES = ("light", "dark")
SCHEMES = ("blend", "jetbrains", "eclipse")

BASE: Dict[str, Dict[str, str]] = {
    "light": {
        "background": "#FFFFFF", "foreground": "#1E1B26",
        "chrome": "#F4F3F6", "chrome_text": "#1E1B26", "chrome_border": "#D6D2DE",
        "gutter_background": "#F7F5FA", "gutter_foreground": "#8E86A0",
        "current_line": "#F5F0FC", "selection": "#DCCBF2", "accent": "#7A2EC0",
        "error_background": "#FBD5DA",
        "keyword": "#7A2EC0", "string": "#067D17", "comment": "#6B7280", "number": "#1750EB",
        "regexp": "#B3267A", "operator": "#1E1B26", "engine": "#0E6F86", "heading": "#1750EB",
        "marker": "#7A2EC0", "bullet": "#7A2EC0", "ordered": "#7A2EC0", "quote": "#5B6470",
        "rule": "#6B7280", "fence": "#6B7280", "code": "#0F766E", "code_background": "#F3F1F8",
        "code_inline": "#0F766E", "link": "#1750EB",
        "breakpoint": "#E53935", "execution": "#FFE27A",
    },
    "dark": {
        "background": "#2B2B2D", "foreground": "#BCBEC4",
        "chrome": "#3C3F41", "chrome_text": "#BCBEC4", "chrome_border": "#515457",
        "gutter_background": "#313335", "gutter_foreground": "#6F737A",
        "current_line": "#323236", "selection": "#3D3152", "accent": "#B983E0",
        "error_background": "#4A2226",
        "keyword": "#B983E0", "string": "#6AAB73", "comment": "#9499A2", "number": "#6897BB",
        "regexp": "#E07A8F", "operator": "#BCBEC4", "engine": "#4FC1C9", "heading": "#6897BB",
        "marker": "#B983E0", "bullet": "#B983E0", "ordered": "#B983E0", "quote": "#9AA0A8",
        "rule": "#9499A2", "fence": "#9499A2", "code": "#8FD0A0", "code_background": "#353338",
        "code_inline": "#8FD0A0", "link": "#6897BB",
        "breakpoint": "#E5534B", "execution": "#4B4424",
    },
}

OVERRIDES: Dict[str, Dict[str, Dict[str, str]]] = {
    "blend": {"light": {}, "dark": {}},
    "jetbrains": {
        "light": {"keyword": "#0033B3", "marker": "#0033B3", "bullet": "#0033B3", "ordered": "#0033B3",
                  "accent": "#0033B3", "comment": "#6F6F6F", "regexp": "#00627A", "engine": "#00627A",
                  "heading": "#1750EB"},
        "dark": {"keyword": "#CF8E6D", "marker": "#CF8E6D", "bullet": "#CF8E6D", "ordered": "#CF8E6D",
                 "accent": "#CF8E6D", "comment": "#9499A2", "number": "#2AACB8", "regexp": "#D19A66",
                 "engine": "#2AACB8", "heading": "#D19A66"},
    },
    "eclipse": {
        "light": {"keyword": "#7F0055", "marker": "#7F0055", "bullet": "#7F0055", "ordered": "#7F0055",
                  "accent": "#7F0055", "heading": "#7F0055", "string": "#2A00FF", "comment": "#3F7F5F",
                  "number": "#0000C0", "operator": "#000000"},
        "dark": {"keyword": "#C792EA", "marker": "#C792EA", "bullet": "#C792EA", "ordered": "#C792EA",
                 "accent": "#C792EA", "heading": "#C792EA", "string": "#CE9178", "comment": "#7EA66A",
                 "number": "#B5CEA8", "regexp": "#D7BA7D", "operator": "#D4D4D4", "engine": "#4EC9B0"},
    },
}


def palette(mode: str = "light", scheme: str = "blend") -> Dict[str, str]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if scheme not in SCHEMES:
        raise ValueError(f"unknown color scheme {scheme!r}")
    colors = dict(BASE[mode])
    colors.update(OVERRIDES[scheme][mode])
    return colors


def tag_properties(colors: Dict[str, str]) -> Dict[str, Dict[str, object]]:
    """Text-tag properties per highlight style (keys are GtkTextTag property names)."""
    return {
        "keyword": {"foreground": colors["keyword"], "weight": 700},
        "string": {"foreground": colors["string"]},
        "comment": {"foreground": colors["comment"], "style": "italic"},
        "number": {"foreground": colors["number"]},
        "regexp": {"foreground": colors["regexp"]},
        "operator": {"foreground": colors["operator"]},
        "engine": {"foreground": colors["engine"], "weight": 700},
        "error": {"background": colors["error_background"]},
        "heading": {"foreground": colors["heading"], "weight": 800},
        "marker": {"foreground": colors["marker"], "weight": 700},
        "bullet": {"foreground": colors["bullet"]},
        "ordered": {"foreground": colors["ordered"]},
        "quote": {"foreground": colors["quote"], "style": "italic"},
        "rule": {"foreground": colors["rule"]},
        "fence": {"foreground": colors["fence"]},
        "code": {"foreground": colors["code"], "background": colors["code_background"]},
        "code-inline": {"foreground": colors["code_inline"]},
        "bold": {"weight": 700},
        "italic": {"style": "italic"},
        "link": {"foreground": colors["link"], "underline": True},
        "current-line": {"background": colors["current_line"]},
    }


STYLE_NAMES = tuple(tag_properties(BASE["light"]).keys())


def css(colors: Dict[str, str]) -> str:
    """Widget colors: window chrome (menus, toolbar, tabs, panels) and the text areas."""
    chrome = f"background-color: {colors['chrome']}; color: {colors['chrome_text']}; border-color: {colors['chrome_border']};"
    field = f"background-color: {colors['background']}; color: {colors['foreground']};"
    selected = f"background-color: {colors['selection']}; color: {colors['foreground']};"
    return "\n".join([
        "window, .background, dialog, popover, popover contents, menu, menubar, menuitem, toolbar, "
        "notebook > header, notebook > header > tabs > tab, statusbar, paned > separator, "
        "button, label, box { " + chrome + " }",
        "button { background-image: none; }",
        "entry, searchentry, list, listbox, treeview, treeview.view { " + field + " }",
        "row:selected, treeview.view:selected, menu menuitem:hover, menubar > menuitem:hover { " + selected + " }",
        f"textview text {{ {field} }}",
        f"textview border {{ background-color: {colors['gutter_background']}; "
        f"color: {colors['gutter_foreground']}; }}",
        "",
    ])


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colors (1.0 to 21.0)."""
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)
