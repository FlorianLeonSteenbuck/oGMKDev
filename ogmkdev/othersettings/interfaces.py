"""The settings interfaces (the Java package ``model.settings.interfaces``).

A Python port of OtherSettings. The methods keep the names of the Java version in snake case:
``getString`` is ``get_string``, ``setNumber`` is ``set_number``. ``refresh`` raises ``OSError`` where the Java
version declared ``IOException``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

from ..outcome import Failure


class Settings(ABC):
    """Read access to a set of settings, each one identified by a string id."""

    @abstractmethod
    def get_id(self) -> int:
        """The number of this set of settings (-1 when it has none)."""

    @abstractmethod
    def get_mandatories(self) -> List[str]:
        """The ids that must have a value."""

    @abstractmethod
    def get_setting_providers(self) -> Dict[str, "SettingProvider"]:  # noqa: F821 - a forward reference
        """The providers by id: what each setting is and what it holds."""

    @abstractmethod
    def has(self, id: str) -> bool:
        """Whether a setting with this id exists."""

    @abstractmethod
    def get(self, id: str) -> Union[Any, Failure]:
        """The value of a setting, whatever its type; a Failure with the reason when there is no such setting."""

    @abstractmethod
    def get_string(self, id: str) -> Union[str, Failure]:
        """The value of a setting as text, or the reason it has none."""

    @abstractmethod
    def get_number(self, id: str) -> Union[float, Failure]:
        """The value of a setting as a number, or the reason it has none."""

    @abstractmethod
    def get_boolean(self, id: str) -> Union[bool, Failure]:
        """The value of a setting as a boolean, or the reason it has none."""


class WriteableSettings(Settings, ABC):
    """Settings whose values can be changed."""

    @abstractmethod
    def set(self, id: str, setting_value: Any) -> None:
        """Sets a value; the type of the value picks the setter. Raises UnsupportedSettingValueException."""

    @abstractmethod
    def set_string(self, id: str, setting_value: str) -> None:
        """Sets a text value."""

    @abstractmethod
    def set_number(self, id: str, setting_value: float) -> None:
        """Sets a number value."""

    @abstractmethod
    def set_boolean(self, id: str, setting_value: bool) -> None:
        """Sets a boolean value."""


class DynamicSettings(Settings, ABC):
    """Settings that are read from somewhere else and can be read again."""

    @abstractmethod
    def refresh(self) -> None:
        """Reads the values again. Raises OSError when the source cannot be read."""


class DynamicWriteableSettings(WriteableSettings, ABC):
    """Writeable settings that can be read again."""

    @abstractmethod
    def refresh(self) -> None:
        """Reads the values again. Raises OSError when the source cannot be read."""
