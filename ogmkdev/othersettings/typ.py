"""The types of a setting (the Java package ``typ``), extended by the types the dialogs need: a colour and a list of
pairs such as the TODO keywords ("TODO:3").

A SettingsTyp names the kind of input a setting has and the values it may hold. The Java version tests a value with
``Class.isInstance``; here each output is a predicate. Python's ``bool`` is an ``int``, so the number and integer
predicates leave booleans out. A PAIR_LIST is a list whose entries must all be pairs; an empty one fits.

A SettingsOutput is plain data, a tuple of its predicate and its OutputTyp: no class with attributes is needed.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Callable, List, Tuple

from .interfaces import Settings

Pair = Tuple[str, int]  # a keyword and its priority, as in "TODO:3"
Pairs = List[Pair]
COLOUR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")


class OutputTyp(Enum):
    """What an output holds: one value, a list where one entry is enough, or a list where every entry must fit."""

    SINGLE = "single"
    LIST = "list"
    PAIR_LIST = "pair_list"


SettingsOutput = Tuple[Callable[[Any], bool], OutputTyp]


def output(accepts: Callable[[Any], bool], typ: OutputTyp = OutputTyp.SINGLE) -> SettingsOutput:
    """One value type of a SettingsTyp: the predicate that tells whether a value (or a list entry) fits, and its kind."""
    return (accepts, typ)


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


def _is_colour(value: Any) -> bool:
    return isinstance(value, str) and COLOUR_PATTERN.fullmatch(value) is not None


def _is_pair(value: Any) -> bool:
    return (isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str)
            and isinstance(value[1], int) and not isinstance(value[1], bool))


class SettingsTyp(Enum):
    """The kinds of setting. Each one lists the values it accepts (``valid_outputs``)."""

    SWITCH_SETTINGS = (output(_is_settings),)
    MULTI_SETTINGS = (output(_is_settings, OutputTyp.LIST),)
    TEXT_LINE = (output(_is_string),)
    TEXT_AREA = (output(_is_string),)
    INPUT_NUMBER = (output(_is_number),)
    INPUT_INT = (output(_is_integer),)
    INPUT_DOUBLE = (output(_is_double),)
    SELECT = (output(_is_string), output(_is_integer))
    CHECKBOXES = (output(_is_string, OutputTyp.LIST), output(_is_integer, OutputTyp.LIST))
    LIST = (output(_is_string, OutputTyp.LIST),)
    CHECKBOX = (output(_is_boolean),)
    COLOR = (output(_is_colour),)
    PAIRS = (output(_is_pair, OutputTyp.PAIR_LIST),)

    @property
    def valid_outputs(self) -> Tuple[SettingsOutput, ...]:
        return self.value
