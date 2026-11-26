"""Setting providers: a value with the type it must keep (the Java package ``model.provider``)."""

from __future__ import annotations

from typing import Any, Generic, List, TypeVar

from .exceptions import WrongSettingsDataException
from .helper import instance_of_settings_typ
from .typ import SettingsTyp

D = TypeVar("D")


class SettingProvider(Generic[D]):
    """Holds the data of one setting. Data that does not fit the SettingsTyp is refused.

    Note: as in the Java version, an empty list fits no LIST type, so it is refused.
    """

    def __init__(self, default_data: D, typ: SettingsTyp) -> None:
        self.typ = typ
        self._data: Any = None
        self.set_data(default_data)

    @property
    def data(self) -> D:
        return self._data

    def set_data(self, data: D) -> None:
        if not instance_of_settings_typ(data, self.typ):
            raise WrongSettingsDataException(f"data is not compatible with the SettingsTyp {self.typ.name}")
        self._data = data


class BooleanCheckboxProvider(SettingProvider[bool]):
    """A checkbox: a boolean."""

    def __init__(self, default_data: bool) -> None:
        super().__init__(default_data, SettingsTyp.CHECKBOX)


class NumberInputProvider(SettingProvider[float]):
    """A number input: an int or a float."""

    def __init__(self, default_data: float) -> None:
        super().__init__(default_data, SettingsTyp.INPUT_NUMBER)


class StringLineProvider(SettingProvider[str]):
    """A line of text."""

    def __init__(self, default_data: str) -> None:
        super().__init__(default_data, SettingsTyp.TEXT_LINE)


class StringListProvider(SettingProvider[List[str]]):
    """A list of texts."""

    def __init__(self, default_data: List[str]) -> None:
        super().__init__(default_data, SettingsTyp.LIST)
