"""Component files from the templates: names in the casing each file needs."""

import pytest

from ogmkdev import scaffold


def test_names_in_each_casing():
    assert scaffold.pascal("cart item") == "CartItem"
    assert scaffold.pascal("cart-item") == "CartItem"
    assert scaffold.kebab("CartItem") == "cart-item"
    assert scaffold.kebab("cart_item") == "cart-item"


def test_react_component_has_a_props_interface_and_a_css_module():
    (main, text, cursor), (module, css, _c) = scaffold.component_files("react", "cart item")
    assert main == "CartItem.tsx" and module == "CartItem.module.css"
    assert "export function CartItem({ title = 'CartItem' }: CartItemProps)" in text
    assert "import styles from './CartItem.module.css';" in text
    assert 0 < cursor < len(text)


def test_angular_component_has_ts_html_and_css_with_matching_names():
    files = scaffold.component_files("angular", "cart item")
    assert [name for name, _t, _c in files] == ["cart-item.component.ts", "cart-item.component.html",
                                               "cart-item.component.css"]
    ts = files[0][1]
    assert "selector: 'app-cart-item'" in ts
    assert "templateUrl: './cart-item.component.html'" in ts
    assert "export class CartItemComponent" in ts


def test_vue_svelte_and_lit():
    assert scaffold.component_files("vue", "cart item")[0][0] == "cart-item.vue"
    assert scaffold.component_files("svelte", "cart item")[0][0] == "CartItem.svelte"
    lit = scaffold.component_files("lit", "cart item")[0][1]
    assert "@customElement('cart-item')" in lit and "export class CartItem extends LitElement" in lit


def test_the_cursor_lies_inside_the_template_body():
    main, text, cursor = scaffold.component_files("svelte", "cart item")[0]
    assert 0 <= cursor <= len(text)


def test_unknown_framework_and_empty_name_are_rejected():
    with pytest.raises(ValueError):
        scaffold.component_files("cobol", "x")
    with pytest.raises(ValueError):
        scaffold.component_files("react", "  ")
