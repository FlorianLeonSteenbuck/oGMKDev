import unittest

from ogmkdev import theme


class ThemeTests(unittest.TestCase):
    def test_every_palette_defines_all_colors_used_by_tags(self):
        needed = set()
        for mode in theme.MODES:
            base = theme.BASE[mode]
            needed |= set(base)
        for mode in theme.MODES:
            for scheme in theme.SCHEMES:
                colors = theme.palette(mode, scheme)
                self.assertEqual(set(colors), needed, (mode, scheme))
                for props in theme.tag_properties(colors).values():
                    for value in props.values():
                        if isinstance(value, str) and value.startswith("#"):
                            self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$")

    def test_text_is_readable_in_every_mode_and_scheme(self):
        for mode in theme.MODES:
            for scheme in theme.SCHEMES:
                colors = theme.palette(mode, scheme)
                background = colors["background"]
                for key in ("foreground", "keyword", "string", "number", "regexp", "operator",
                            "engine", "heading", "marker", "bullet", "ordered", "link", "code",
                            "code_inline", "quote", "rule", "fence"):
                    ratio = theme.contrast_ratio(colors[key], background)
                    self.assertGreaterEqual(ratio, 4.5, f"{mode}/{scheme} {key}: {ratio:.2f}")
                ratio = theme.contrast_ratio(colors["comment"], background)
                self.assertGreaterEqual(ratio, 4.5, f"{mode}/{scheme} comment: {ratio:.2f}")
                self.assertGreaterEqual(theme.contrast_ratio(colors["foreground"], colors["gutter_background"]), 4.5)
                self.assertGreaterEqual(theme.contrast_ratio(colors["chrome_text"], colors["chrome"]), 4.5,
                                        f"{mode}/{scheme} chrome")

    def test_dark_mode_is_dark_and_light_mode_is_light(self):
        self.assertLess(theme.luminance(theme.palette("dark")["background"]), 0.05)
        self.assertGreater(theme.luminance(theme.palette("light")["background"]), 0.9)

    def test_blend_keeps_jetbrains_structure_with_purple_accent(self):
        blend = theme.palette("light", "blend")
        self.assertEqual(blend["keyword"], "#7A2EC0")
        self.assertEqual(blend["string"], theme.BASE["light"]["string"])
        eclipse = theme.palette("light", "eclipse")
        jetbrains = theme.palette("light", "jetbrains")
        self.assertEqual(eclipse["keyword"], "#7F0055")
        self.assertEqual(jetbrains["keyword"], "#0033B3")
        self.assertNotEqual(blend["keyword"], jetbrains["keyword"])

    def test_unknown_mode_or_scheme_is_rejected(self):
        with self.assertRaises(ValueError):
            theme.palette("sepia")
        with self.assertRaises(ValueError):
            theme.palette("light", "vim")

    def test_css_contains_the_text_and_gutter_colors(self):
        css = theme.css(theme.palette("dark"))
        self.assertIn("background-color: #2B2B2D", css)
        self.assertIn("textview border", css)
        self.assertIn("background-color: #3C3F41", css)


if __name__ == "__main__":
    unittest.main()
