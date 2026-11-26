"""OtherSettings: settings created in code, ported from the Java library of the same name.

A setting is a SettingProvider (its value, and the SettingsTyp that says how it is shown and which values it takes).
The settings are a Settings object: PreStoredSettings keeps the values in memory, OverrideDynamicSettings reads them
from a source and lets a set value override the read one. The types are in ``typ``; the checks in ``helper``.
"""

from .abstracts import OverrideDynamicSettings, PreSupportDynamicWriteableSettings, PreSupportWriteableSettings
from .exceptions import SettingException, UnsupportedSettingValueException, WrongSettingsDataException
from .interfaces import DynamicSettings, DynamicWriteableSettings, Settings, WriteableSettings
from .providers import (BooleanCheckboxProvider, NumberInputProvider, SettingProvider, StringLineProvider,
                        StringListProvider)
from .settings import EmptySettings, PreStoredSettings
from .typ import OutputTyp, SettingsOutput, SettingsTyp

__all__ = [
    "BooleanCheckboxProvider", "DynamicSettings", "DynamicWriteableSettings", "EmptySettings",
    "NumberInputProvider", "OutputTyp", "OverrideDynamicSettings", "PreStoredSettings",
    "PreSupportDynamicWriteableSettings", "PreSupportWriteableSettings", "SettingException", "SettingProvider",
    "Settings", "SettingsOutput", "SettingsTyp", "StringLineProvider", "StringListProvider",
    "UnsupportedSettingValueException", "WrongSettingsDataException", "WriteableSettings",
]
