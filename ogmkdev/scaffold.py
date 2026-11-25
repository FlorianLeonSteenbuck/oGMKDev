"""Files that a new component or class consists of, from the built-in templates.

A component is a set of files: the framework's main file, and for Angular its template and style, for
React a CSS module. :func:`component_files` expands the templates with the name in the casing each
file needs (PascalCase for classes and components, kebab-case for tags, selectors and file names).
"""

from __future__ import annotations

import re
from typing import List, Tuple

from . import templates

FILE_NAME_WORD = re.compile(r"[A-Za-z0-9]+")


def words(name: str) -> List[str]:
    """The words of a name: 'cart item', 'cart-item' and 'CartItem' all give ['cart', 'item']."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [word.lower() for word in FILE_NAME_WORD.findall(spaced)]


def pascal(name: str) -> str:
    return "".join(word.capitalize() for word in words(name))


def kebab(name: str) -> str:
    return "-".join(words(name))


def _template(language: str, trigger: str) -> templates.Template:
    for template in templates.BUILTIN_TEMPLATES:
        if template.language == language and template.trigger == trigger:
            return template
    raise KeyError(f"no built-in template {trigger!r} for {language!r}")


def _expanded(language: str, trigger: str, values) -> Tuple[str, int]:
    expansion = templates.expand(_template(language, trigger), values)
    return expansion.text, expansion.cursor


# framework -> (file name, language, trigger, values) for each file of a component
FRAMEWORKS = ("react", "vue", "svelte", "angular", "lit")


def component_files(framework: str, name: str) -> List[Tuple[str, str, int]]:
    """The files of a component: (file name, text, cursor offset). The cursor is at ``$0``."""
    if framework not in FRAMEWORKS:
        raise ValueError(f"unknown framework {framework!r}")
    if not words(name):
        raise ValueError("a component needs a name")
    component, slug = pascal(name), kebab(name)
    if framework == "react":
        text, cursor = _expanded("tsx", "rfcp", {"name": component})
        return [(f"{component}.tsx", text, cursor),
                (f"{component}.module.css", ".root {\n}\n", len(".root {\n")),]
    if framework == "vue":
        text, cursor = _expanded("vue", "sfc", {"name": slug})
        return [(f"{slug}.vue", text, cursor)]
    if framework == "svelte":
        text, cursor = _expanded("svelte", "svelte", {"name": component})
        return [(f"{component}.svelte", text, cursor)]
    if framework == "angular":
        text, cursor = _expanded("typescript", "ng", {"selector": slug, "class": component})
        html_text, html_cursor = _expanded("html", "ngtpl", {})
        return [(f"{slug}.component.ts", text, cursor),
                (f"{slug}.component.html", html_text, html_cursor),
                (f"{slug}.component.css", "", 0)]
    text, cursor = _expanded("typescript", "lit", {"tag": slug, "class": component})
    return [(f"{slug}.ts", text, cursor)]
