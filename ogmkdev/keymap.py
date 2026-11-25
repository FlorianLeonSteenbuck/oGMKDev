"""Keyboard shortcuts: default bindings from the action table, overridable in EditorConfig.

A binding is an accelerator such as ``<Control><Shift>f`` or ``F9``. Override one action with
``ogmkdev_key_<method> = <accelerator>`` (global or project scope); ``none`` removes the shortcut.
Accelerators are compared in canonical form, so ``<Primary>S``, ``<Control>s`` and ``<Shift><Control>S``
are normalised. Each key combination runs one action; a clash is reported by :func:`clashes`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Mapping, Optional, Tuple

KEY_PREFIX = "ogmkdev_key_"
_MODIFIERS = {"control": "Control", "primary": "Control", "ctrl": "Control", "shift": "Shift",
              "alt": "Alt", "mod1": "Alt"}
_ORDER = ("Control", "Shift", "Alt")
_TOKEN = re.compile(r"<([A-Za-z0-9_]+)>")


def canonical(accelerator: str) -> Optional[str]:
    """Canonical text of an accelerator, or ``None`` for empty and ``none``."""
    text = accelerator.strip()
    if not text or text.lower() == "none":
        return None
    mods = set()
    rest = text
    while True:
        match = _TOKEN.match(rest)
        if not match:
            break
        name = match.group(1).lower()
        if name not in _MODIFIERS:
            break
        mods.add(_MODIFIERS[name])
        rest = rest[match.end():]
    if not rest:
        return None
    key = rest.lower() if len(rest) == 1 else rest
    return "".join(f"<{m}>" for m in _ORDER if m in mods) + key


def resolve(defaults: Mapping[str, str], properties: Mapping[str, str]) -> Dict[str, str]:
    """Method name to canonical accelerator, with the EditorConfig overrides applied."""
    bindings: Dict[str, str] = {}
    for method, accelerator in defaults.items():
        override = properties.get(KEY_PREFIX + method)
        chosen = accelerator if override is None else override
        text = canonical(chosen)
        if text is not None:
            bindings[method] = text
    return bindings


def by_accelerator(bindings: Mapping[str, str]) -> Dict[str, str]:
    return {accelerator: method for method, accelerator in bindings.items()}


def clashes(bindings: Mapping[str, str]) -> List[Tuple[str, List[str]]]:
    """Accelerators bound to more than one action."""
    seen: Dict[str, List[str]] = {}
    for method, accelerator in bindings.items():
        seen.setdefault(accelerator, []).append(method)
    return [(accelerator, methods) for accelerator, methods in seen.items() if len(methods) > 1]
