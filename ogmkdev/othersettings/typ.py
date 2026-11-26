"""The types of a setting (the Java package ``typ``).

A SettingsTyp names the kind of input a setting has (a checkbox, a text line, a number...) and the values it may hold.
The Java version tests a value with ``Class.isInstance``; here each output has a predicate instead. Python's ``bool``
is an ``int``, so the number and integer predicates leave booleans out, as Java's ``Number`` does for ``Boolean``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Tuple

from .interfaces import Settings


class OutputTyp(Enum):
    """Whether an output holds one value or a list of values (the Java ``SettingsOutput.Typ``)."""

    SINGLE = "single"
    LIST = "list"


class SettingsOutput:
    """One value type a SettingsTyp accepts: ``accepts`` tells whether a value (or, for a LIST, one entry) fits."""

    def __init__(self, accepts: Callable[[Any], bool], typ: OutputTyp = OutputTyp.SINGLE) -> None:
        self.accepts = accepts
        self.typ = typ


def _is_settings(value: Any) -> bool:
    return isinstance(value, Settings)


def _is_string(value: Any) -> bool:
    return isinstance(value, str)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_double(value: Any) -> bool:
    return isinstance(value, float)


def _is_boolean(value: Any) -> bool:
    return isinstance(value, bool)


class SettingsTyp(Enum):
    """The kinds of setting. Each one lists the values it accepts (``valid_outputs``)."""

    SWITCH_SETTINGS = (SettingsOutput(_is_settings),)
    MULTI_SETTINGS = (SettingsOutput(_is_settings, OutputTyp.LIST),)
    TEXT_LINE = (SettingsOutput(_is_string),)
    TEXT_AREA = (SettingsOutput(_is_string),)
    INPUT_NUMBER = (SettingsOutput(_is_number),)
    INPUT_INT = (SettingsOutput(_is_integer),)
    INPUT_DOUBLE = (SettingsOutput(_is_double),)
    SELECT = (SettingsOutput(_is_string), SettingsOutput(_is_integer))
    CHECKBOXES = (SettingsOutput(_is_string, OutputTyp.LIST), SettingsOutput(_is_integer, OutputTyp.LIST))
    LIST = (SettingsOutput(_is_string, OutputTyp.LIST),)
    CHECKBOX = (SettingsOutput(_is_boolean),)

    @property
    def valid_outputs(self) -> Tuple[SettingsOutput, ...]:
        return self.value
