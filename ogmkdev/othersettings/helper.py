"""Checks of a value against a SettingsTyp (the Java class ``helper.SettingsHelper``)."""

from __future__ import annotations

from typing import Any

from .typ import OutputTyp, SettingsTyp


def _is_unsupported_single(instance: Any) -> bool:
    # a Java Collection or Map: the Python containers that are no single value
    return isinstance(instance, (tuple, set, frozenset, dict))


def _list_fits(instance: list, typ: SettingsTyp) -> bool:
    # a list fits when one of its entries is a value of a LIST output (an empty list fits nothing)
    for output in typ.valid_outputs:
        if output.typ is not OutputTyp.LIST:
            continue
        for entry in instance:
            if output.accepts(entry):
                return True
    return False


def instance_of_settings_typ(instance: Any, typ: SettingsTyp) -> bool:
    """Whether ``instance`` is a value the SettingsTyp accepts: a single value, or a list (see _list_fits)."""
    if isinstance(instance, list):
        return _list_fits(instance, typ)
    if _is_unsupported_single(instance):
        return False
    for output in typ.valid_outputs:
        if output.typ is OutputTyp.LIST:
            continue
        if output.accepts(instance):
            return True
    return False


def dispatch_set(settings: Any, id: str, setting_value: Any) -> None:
    """Passes a value to the setter of its type: text, boolean or number. Raises UnsupportedSettingValueException
    for anything else. (A boolean is checked first: in Python it is also a number.)"""
    from .exceptions import UnsupportedSettingValueException

    if isinstance(setting_value, bool):
        settings.set_boolean(id, setting_value)
    elif isinstance(setting_value, str):
        settings.set_string(id, setting_value)
    elif isinstance(setting_value, (int, float)):
        settings.set_number(id, setting_value)
    else:
        raise UnsupportedSettingValueException(f"{type(setting_value).__name__} is unsupported")
