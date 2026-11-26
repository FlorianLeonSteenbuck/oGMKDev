"""Settings that hold their values in memory (the Java package ``model.settings``, classes EmptySettings and
PreStoredSettings)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .exceptions import WrongSettingsDataException
from .helper import dispatch_set
from .interfaces import Settings, WriteableSettings
from .providers import SettingProvider


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

    def get(self, id: str) -> Any:
        return None

    def get_string(self, id: str) -> Optional[str]:
        return None

    def get_number(self, id: str) -> Optional[float]:
        return None

    def get_boolean(self, id: str) -> Optional[bool]:
        return None


class PreStoredSettings(WriteableSettings):
    """Settings whose providers are given up front and kept in memory.

    As in the Java version, a setter ignores a value of the wrong type for its setting: the old value stays.
    An unknown id raises KeyError.
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

    def get(self, id: str) -> Any:
        return self.providers[id].data

    def get_string(self, id: str) -> Optional[str]:
        return self.providers[id].data

    def get_number(self, id: str) -> Optional[float]:
        return self.providers[id].data

    def get_boolean(self, id: str) -> Optional[bool]:
        return self.providers[id].data
