"""Base classes for settings that read their values from somewhere (the Java package ``model.settings.abstracts``)."""

from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List, Optional

from .helper import dispatch_set
from .interfaces import DynamicWriteableSettings, WriteableSettings
from .providers import (BooleanCheckboxProvider, NumberInputProvider, SettingProvider, StringLineProvider)


class PreSupportWriteableSettings(WriteableSettings, ABC):
    """Writeable settings with ``set`` already written: it passes the value to the setter of its type."""

    def set(self, id: str, setting_value: Any) -> None:
        dispatch_set(self, id, setting_value)


class PreSupportDynamicWriteableSettings(DynamicWriteableSettings, ABC):
    """Dynamic writeable settings with ``set`` already written. ``refresh`` is left to the subclass."""

    def set(self, id: str, setting_value: Any) -> None:
        dispatch_set(self, id, setting_value)


class OverrideDynamicSettings(PreSupportDynamicWriteableSettings, ABC):
    """Settings read from a source, where a set value overrides the read one.

    The live providers come from the source (``refresh`` fills them in the subclass); the overrides are kept apart
    and merged in when the providers are asked for. As in the Java version, the merged map is the live map itself.
    """

    def __init__(self) -> None:
        self.live_providers: Dict[str, SettingProvider] = {}
        self.override_providers: Dict[str, SettingProvider] = {}
        self.need_update_cache = True
        self.cached_providers: Dict[str, SettingProvider] = {}

    def get_mandatories(self) -> List[str]:
        return []

    def get_setting_providers(self) -> Dict[str, SettingProvider]:
        if self.need_update_cache:
            self.cached_providers = self.live_providers
            for key, provider in self.override_providers.items():
                self.cached_providers[key] = provider
            self.need_update_cache = False
        return self.cached_providers

    def _override(self, id: str, provider_for_new: SettingProvider, value: Any) -> None:
        provider = provider_for_new
        if self.has(id):
            provider = self.get_setting_providers()[id]
            provider.set_data(value)  # raises WrongSettingsDataException when the type does not fit
        self.override_providers[id] = provider
        self.need_update_cache = True

    def set_string(self, id: str, setting_value: str) -> None:
        self._override(id, StringLineProvider(setting_value), setting_value)

    def set_number(self, id: str, setting_value: float) -> None:
        self._override(id, NumberInputProvider(setting_value), setting_value)

    def set_boolean(self, id: str, setting_value: bool) -> None:
        self._override(id, BooleanCheckboxProvider(setting_value), setting_value)

    def has(self, id: str) -> bool:
        return id in self.get_setting_providers()

    def get(self, id: str) -> Any:
        return self.get_setting_providers()[id].data

    def get_string(self, id: str) -> Optional[str]:
        return self.get_setting_providers()[id].data

    def get_number(self, id: str) -> Optional[float]:
        return self.get_setting_providers()[id].data

    def get_boolean(self, id: str) -> Optional[bool]:
        return self.get_setting_providers()[id].data
