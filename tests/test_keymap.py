import unittest

from ogmkdev import keymap as K


class KeymapTests(unittest.TestCase):
    def test_canonical_form(self):
        self.assertEqual(K.canonical("<Primary>S"), "<Control>s")
        self.assertEqual(K.canonical("<Shift><Control>F"), "<Control><Shift>f")
        self.assertEqual(K.canonical("<Alt><Control>b"), "<Control><Alt>b")
        self.assertEqual(K.canonical("F9"), "F9")
        self.assertEqual(K.canonical("<Control>space"), "<Control>space")
        self.assertIsNone(K.canonical("none"))
        self.assertIsNone(K.canonical(""))

    def test_overrides_and_removal(self):
        defaults = {"save_current": "<Control>s", "find": "<Control>f"}
        bindings = K.resolve(defaults, {"ogmkdev_key_find": "none",
                                        "ogmkdev_key_save_current": "<Primary><Shift>s"})
        self.assertEqual(bindings, {"save_current": "<Control><Shift>s"})

    def test_reverse_lookup_and_clashes(self):
        bindings = {"a": "<Control>s", "b": "<Control>s", "c": "F9"}
        self.assertEqual(K.by_accelerator({"a": "F9"}), {"F9": "a"})
        self.assertEqual(K.clashes(bindings), [("<Control>s", ["a", "b"])])


if __name__ == "__main__":
    unittest.main()
