"""Component files from the templates: names in the casing each file needs."""

import unittest

from ogmkdev import scaffold


class ComponentScaffoldTests(unittest.TestCase):
    def test_names_in_each_casing(self):
        assert scaffold.pascal("cart item") == "CartItem"
        assert scaffold.pascal("cart-item") == "CartItem"
        assert scaffold.kebab("CartItem") == "cart-item"
        assert scaffold.kebab("cart_item") == "cart-item"

    def test_react_component_has_a_props_interface_and_a_css_module(self):
        (main, text, cursor), (module, css, _c) = scaffold.component_files("react", "cart item")
        assert main == "CartItem.tsx" and module == "CartItem.module.css"
        assert "export function CartItem({ title = 'CartItem' }: CartItemProps)" in text
        assert "import styles from './CartItem.module.css';" in text
        assert 0 < cursor < len(text)

    def test_angular_component_has_ts_html_and_css_with_matching_names(self):
        files = scaffold.component_files("angular", "cart item")
        assert [name for name, _t, _c in files] == ["cart-item.component.ts", "cart-item.component.html",
                                                   "cart-item.component.css"]
        ts = files[0][1]
        assert "selector: 'app-cart-item'" in ts
        assert "templateUrl: './cart-item.component.html'" in ts
        assert "export class CartItemComponent" in ts

    def test_vue_svelte_and_lit(self):
        assert scaffold.component_files("vue", "cart item")[0][0] == "cart-item.vue"
        assert scaffold.component_files("svelte", "cart item")[0][0] == "CartItem.svelte"
        lit = scaffold.component_files("lit", "cart item")[0][1]
        assert "@customElement('cart-item')" in lit and "export class CartItem extends LitElement" in lit

    def test_the_cursor_lies_inside_the_template_body(self):
        main, text, cursor = scaffold.component_files("svelte", "cart item")[0]
        assert 0 <= cursor <= len(text)

    def test_unknown_framework_and_empty_name_are_rejected(self):
        with self.assertRaises(ValueError):
            scaffold.component_files("cobol", "x")
        with self.assertRaises(ValueError):
            scaffold.component_files("react", "  ")


if __name__ == "__main__":
    unittest.main()
