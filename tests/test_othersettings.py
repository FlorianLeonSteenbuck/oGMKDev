"""The Python port of OtherSettings: the type checks, the providers, the settings that keep their values, and the
override of read settings. The Java library has no tests of its own; these follow its code."""

import unittest

from ogmkdev.othersettings import (BooleanCheckboxProvider, EmptySettings, NumberInputProvider,
                                   OverrideDynamicSettings, PreStoredSettings, Settings, SettingsTyp,
                                   StringLineProvider, StringListProvider, UnsupportedSettingValueException,
                                   WrongSettingsDataException, WriteableSettings)
from ogmkdev.othersettings.helper import instance_of_settings_typ


class TypeCheckTests(unittest.TestCase):
    def test_single_values_fit_their_types(self):
        self.assertTrue(instance_of_settings_typ("text", SettingsTyp.TEXT_LINE))
        self.assertTrue(instance_of_settings_typ(3, SettingsTyp.INPUT_NUMBER))
        self.assertTrue(instance_of_settings_typ(2.5, SettingsTyp.INPUT_NUMBER))
        self.assertTrue(instance_of_settings_typ(True, SettingsTyp.CHECKBOX))

    def test_a_boolean_is_no_number(self):
        self.assertFalse(instance_of_settings_typ(True, SettingsTyp.INPUT_NUMBER))
        self.assertFalse(instance_of_settings_typ(True, SettingsTyp.INPUT_INT))
        self.assertFalse(instance_of_settings_typ(1, SettingsTyp.CHECKBOX))

    def test_integer_and_double_are_told_apart(self):
        self.assertTrue(instance_of_settings_typ(4, SettingsTyp.INPUT_INT))
        self.assertFalse(instance_of_settings_typ(4.0, SettingsTyp.INPUT_INT))
        self.assertTrue(instance_of_settings_typ(4.0, SettingsTyp.INPUT_DOUBLE))
        self.assertFalse(instance_of_settings_typ(4, SettingsTyp.INPUT_DOUBLE))

    def test_select_takes_a_text_or_an_integer(self):
        self.assertTrue(instance_of_settings_typ("dark", SettingsTyp.SELECT))
        self.assertTrue(instance_of_settings_typ(2, SettingsTyp.SELECT))
        self.assertFalse(instance_of_settings_typ(2.5, SettingsTyp.SELECT))

    def test_a_list_fits_when_one_entry_fits(self):
        self.assertTrue(instance_of_settings_typ(["a", "b"], SettingsTyp.LIST))
        self.assertFalse(instance_of_settings_typ([1, 2], SettingsTyp.LIST))
        self.assertTrue(instance_of_settings_typ([1, 2], SettingsTyp.CHECKBOXES))

    def test_an_empty_list_fits_nothing(self):
        self.assertFalse(instance_of_settings_typ([], SettingsTyp.LIST))

    def test_a_single_value_is_no_list_and_a_container_is_no_single_value(self):
        self.assertFalse(instance_of_settings_typ("a", SettingsTyp.LIST))
        self.assertFalse(instance_of_settings_typ({"a": 1}, SettingsTyp.TEXT_LINE))
        self.assertFalse(instance_of_settings_typ(("a",), SettingsTyp.TEXT_LINE))
        self.assertFalse(instance_of_settings_typ(None, SettingsTyp.TEXT_LINE))


class ProviderTests(unittest.TestCase):
    def test_a_provider_keeps_its_data_and_refuses_another_type(self):
        provider = BooleanCheckboxProvider(True)
        self.assertTrue(provider.data)
        with self.assertRaises(WrongSettingsDataException):
            provider.set_data("yes")
        self.assertTrue(provider.data)

    def test_a_default_of_the_wrong_type_is_refused(self):
        with self.assertRaises(WrongSettingsDataException):
            NumberInputProvider("ten")
        with self.assertRaises(WrongSettingsDataException):
            StringLineProvider(None)

    def test_an_empty_list_is_refused_as_in_the_java_version(self):
        with self.assertRaises(WrongSettingsDataException):
            StringListProvider([])
        self.assertEqual(StringListProvider(["a"]).data, ["a"])


class PreStoredSettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings = PreStoredSettings({
            "name": StringLineProvider("ogmkdev"),
            "size": NumberInputProvider(12),
            "wrap": BooleanCheckboxProvider(False),
        })

    def test_values_are_read_by_their_type(self):
        self.assertTrue(self.settings.has("name"))
        self.assertFalse(self.settings.has("missing"))
        self.assertEqual(self.settings.get_string("name"), "ogmkdev")
        self.assertEqual(self.settings.get_number("size"), 12)
        self.assertFalse(self.settings.get_boolean("wrap"))
        self.assertEqual(self.settings.get("name"), "ogmkdev")

    def test_set_passes_a_value_to_the_setter_of_its_type(self):
        self.settings.set("name", "other")
        self.settings.set("size", 3.5)
        self.settings.set("wrap", True)
        self.assertEqual((self.settings.get_string("name"), self.settings.get_number("size"),
                          self.settings.get_boolean("wrap")), ("other", 3.5, True))

    def test_a_value_of_the_wrong_type_is_ignored(self):
        self.settings.set_number("name", 5)
        self.assertEqual(self.settings.get_string("name"), "ogmkdev")

    def test_a_value_of_an_unsupported_type_is_refused(self):
        with self.assertRaises(UnsupportedSettingValueException):
            self.settings.set("name", ["a"])
        with self.assertRaises(UnsupportedSettingValueException):
            self.settings.set("name", None)

    def test_it_is_writeable_with_no_mandatories_and_id_minus_one(self):
        self.assertIsInstance(self.settings, WriteableSettings)
        self.assertEqual(self.settings.get_id(), -1)
        self.assertEqual(self.settings.get_mandatories(), [])
        self.assertEqual(set(self.settings.get_setting_providers()), {"name", "size", "wrap"})


class FakeFileSettings(OverrideDynamicSettings):
    """Reads its values from a dict that stands in for a file."""

    def __init__(self, values):
        super().__init__()
        self.values = values
        self.refreshed = 0

    def get_id(self):
        return 7  # a concrete subclass names its own id; the abstract base leaves it open, as in Java

    def refresh(self):
        self.refreshed += 1
        self.live_providers = {key: _provider_for(value) for key, value in self.values.items()}
        self.need_update_cache = True


def _provider_for(value):
    if isinstance(value, bool):
        return BooleanCheckboxProvider(value)
    if isinstance(value, str):
        return StringLineProvider(value)
    return NumberInputProvider(value)


class OverrideSettingsTests(unittest.TestCase):
    def setUp(self):
        self.settings = FakeFileSettings({"theme": "light", "tabs": 4, "dark": False})
        self.settings.refresh()

    def test_read_values_come_from_the_source(self):
        self.assertEqual(self.settings.get_string("theme"), "light")
        self.assertEqual(self.settings.get_number("tabs"), 4)
        self.assertFalse(self.settings.get_boolean("dark"))
        self.assertTrue(self.settings.has("tabs"))

    def test_an_override_wins_and_can_add_a_setting(self):
        self.settings.set_string("theme", "dark")
        self.assertEqual(self.settings.get_string("theme"), "dark")
        self.settings.set_boolean("new_flag", True)
        self.assertTrue(self.settings.get_boolean("new_flag"))
        self.assertTrue(self.settings.has("new_flag"))

    def test_an_override_of_the_wrong_type_is_refused_and_not_kept(self):
        with self.assertRaises(WrongSettingsDataException):
            self.settings.set_number("theme", 3)
        self.assertEqual(self.settings.get_string("theme"), "light")

    def test_set_passes_the_value_to_the_setter_of_its_type(self):
        self.settings.set("tabs", 8)
        self.assertEqual(self.settings.get_number("tabs"), 8)
        with self.assertRaises(UnsupportedSettingValueException):
            self.settings.set("tabs", ["x"])

    def test_refresh_reads_the_source_again(self):
        self.settings.values["theme"] = "blue"
        self.settings.refresh()
        self.assertEqual(self.settings.refreshed, 2)
        self.assertEqual(self.settings.get_string("theme"), "blue")


class EmptySettingsTests(unittest.TestCase):
    def test_nothing_is_found(self):
        settings = EmptySettings()
        self.assertFalse(settings.has("x"))
        self.assertIsNone(settings.get("x"))
        self.assertIsNone(settings.get_string("x"))
        self.assertEqual(settings.get_setting_providers(), {})
        self.assertIsInstance(settings, Settings)
        self.assertNotIsInstance(settings, WriteableSettings)

    def test_the_interface_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            Settings()


if __name__ == "__main__":
    unittest.main()
