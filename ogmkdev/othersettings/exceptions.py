"""Exceptions of the settings model (the Java package ``exceptions``)."""


class SettingException(Exception):
    """Base class of the settings errors."""


class UnsupportedSettingValueException(SettingException):
    """A value of a type the settings do not store (neither text, number nor boolean)."""


class WrongSettingsDataException(SettingException):
    """Data that does not fit the type of its setting, or a provider that cannot take it."""
