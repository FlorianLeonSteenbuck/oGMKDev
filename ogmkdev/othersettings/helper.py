"""Checks of a value against a SettingsTyp (the Java class ``helper.SettingsHelper``). The checks answer with a bool and
raise nothing."""

from __future__ import annotations

from typing import Any, List

from .typ import OutputTyp, SettingsTyp


def _is_unsupported_single(instance: Any) -> bool:
    # a Java Collection or Map: the Python containers that are no single value (a list is a list, see below)
    return isinstance(instance, (tuple, set, frozenset, dict))


def _list_fits(instance: List[Any], typ: SettingsTyp) -> bool:
    for accepts, kind in typ.valid_outputs:
        if kind is OutputTyp.LIST and any(accepts(entry) for entry in instance):
            return True
        if kind is OutputTyp.PAIR_LIST and all(accepts(entry) for entry in instance):
            return True
    return False


def instance_of_settings_typ(instance: Any, typ: SettingsTyp) -> bool:
    """Whether ``instance`` is a value the SettingsTyp accepts: a single value, or a list (see _list_fits)."""
    if isinstance(instance, list):
        return _list_fits(instance, typ)
    if _is_unsupported_single(instance):
        return False
    for accepts, kind in typ.valid_outputs:
        if kind is OutputTyp.SINGLE and accepts(instance):
            return True
    return False


def dispatch_set(settings: Any, id: str, setting_value: Any) -> None:
    """Passes a value to the setter of its type: boolean, text or number (a boolean is checked first: in Python it is
    also a number). Raises UnsupportedSettingValueException for anything else, as the Java version does."""
    from .exceptions import UnsupportedSettingValueException

    if isinstance(setting_value, bool):
        settings.set_boolean(id, setting_value)
    elif isinstance(setting_value, str):
        settings.set_string(id, setting_value)
    elif isinstance(setting_value, (int, float)):
        settings.set_number(id, setting_value)
    else:
        raise UnsupportedSettingValueException(f"{type(setting_value).__name__} is unsupported")
