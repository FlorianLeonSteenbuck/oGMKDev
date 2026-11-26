"""Settings that hold their values in memory (the Java package ``model.settings``: EmptySettings and
PreStoredSettings), with the typed setters of the colour and the pairs that answer with the value or a failure."""

from __future__ import annotations

from typing import Any, Dict, List, TypeVar, Union

from ..outcome import Failure, failed
from .exceptions import WrongSettingsDataException
from .helper import dispatch_set
from .interfaces import Settings, WriteableSettings
from .providers import SettingProvider
from .typ import Pairs

T = TypeVar("T")


class EmptySettings(Settings):
    """Settings without any setting: every lookup finds nothing."""

    def get_id(self) -> int:
        return -1

    def get_mandatories(self) -> List[str]:
        return []

    def get_setting_providers(self) -> Dict[str, SettingProvider]:
        return {}

    def has(self, id: str) -> bool:
        return False

    def get(self, id: str) -> Union[Any, Failure]:
        return failed(f"{id}: there is no such setting")

    def get_string(self, id: str) -> Union[str, Failure]:
        return failed(f"{id}: there is no such setting")

    def get_number(self, id: str) -> Union[float, Failure]:
        return failed(f"{id}: there is no such setting")

    def get_boolean(self, id: str) -> Union[bool, Failure]:
        return failed(f"{id}: there is no such setting")


class PreStoredSettings(WriteableSettings):
    """Settings whose providers are given up front and kept in memory.

    As in the Java version, a Java-style setter ignores a value of the wrong type for its setting. A lookup of an unknown
    id answers with a Failure. The setters ``set_color`` and ``set_pairs`` answer with the stored value, or with the reason
    (a Failure) they were refused; nothing is raised for them.
    """

    def __init__(self, providers: Dict[str, SettingProvider]) -> None:
        self.providers = providers

    def get_id(self) -> int:
        return -1

    def get_mandatories(self) -> List[str]:
        return []

    def get_setting_providers(self) -> Dict[str, SettingProvider]:
        return self.providers

    def has(self, id: str) -> bool:
        return id in self.providers

    def set(self, id: str, setting_value: Any) -> None:
        dispatch_set(self, id, setting_value)

    def _store(self, id: str, value: Any) -> None:
        provider = self.providers[id]
        try:
            provider.set_data(value)
        except WrongSettingsDataException:
            pass  # the value is of another type than the setting: it is ignored, as in the Java version
        self.providers[id] = provider

    def set_string(self, id: str, setting_value: str) -> None:
        self._store(id, setting_value)

    def set_number(self, id: str, setting_value: float) -> None:
        self._store(id, setting_value)

    def set_boolean(self, id: str, setting_value: bool) -> None:
        self._store(id, setting_value)

    def _offer(self, id: str, value: T) -> Union[T, Failure]:
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        return self.providers[id].offer(value)

    def set_color(self, id: str, setting_value: str) -> Union[str, Failure]:
        """Stores a colour as "#RRGGBB" and returns it, or returns why it was refused."""
        return self._offer(id, setting_value)

    def set_pairs(self, id: str, setting_value: Pairs) -> Union[Pairs, Failure]:
        """Stores a copy of the pairs and returns it, or returns why they were refused."""
        return self._offer(id, list(setting_value))

    def get(self, id: str) -> Union[Any, Failure]:
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        return self.providers[id].data

    def get_string(self, id: str) -> Union[str, Failure]:
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        return self.providers[id].data

    def get_number(self, id: str) -> Union[float, Failure]:
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        return self.providers[id].data

    def get_boolean(self, id: str) -> Union[bool, Failure]:
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        return self.providers[id].data

    def get_color(self, id: str) -> Union[str, Failure]:
        """The colour of a setting, or the reason it holds none."""
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        value = self.providers[id].data
        if isinstance(value, str):
            return value
        return failed(f"{id}: the setting does not hold a colour")

    def get_pairs(self, id: str) -> Union[Pairs, Failure]:
        """A copy of the pairs of a setting, or the reason it holds none."""
        if id not in self.providers:
            return failed(f"{id}: there is no such setting")
        value = self.providers[id].data
        if isinstance(value, list):
            return list(value)
        return failed(f"{id}: the setting does not hold pairs")
