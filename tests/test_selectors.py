"""CSS selectors and XPath expressions for elements: the four forms and their invariants."""

from ogmkdev import markup, selectors

SVG = ('<svg>\n  <defs>\n    <linearGradient id="grad"><stop offset="0"/></linearGradient>\n  </defs>\n'
       '  <rect id="box"/>\n  <use href="#box"/>\n</svg>\n')
LIST = "<ul>\n<li>a</li>\n<li>b</li>\n<li>c</li>\n</ul>"
PAGE = ('<html><body>\n<div id="main" class="page">\n<p class="item">one</p>\n'
        '<p class="item">two <b>bold</b></p>\n<section><p class="item">three</p></section>\n</div>\n'
        '<div class="page"><p>four</p></div>\n</body></html>')


def elements_of(text, html=False):
    found, error = markup.collect(text, html=html)
    assert error is None
    return found


def test_rect_forms():
    found = elements_of(SVG)
    rect = next(e.index for e in found if e.tag == "rect")
    result = selectors.selectors(found, rect)
    assert result["css"] == {"unique": "#box", "explicit": "svg > rect:nth-child(2)", "implicit": "#box",
                             "full": "svg > rect#box:nth-child(2)"}
    assert result["xpath"] == {"unique": "//rect[@id='box']", "explicit": "/svg/rect[1]",
                               "implicit": "//rect[@id='box']", "full": "/svg/rect[@id='box'][1]"}


def test_gradient_forms():
    found = elements_of(SVG)
    grad = next(e.index for e in found if e.tag == "linearGradient")
    css = selectors.variants(found, grad, "css")
    assert css["explicit"] == "svg > defs:nth-child(1) > linearGradient:nth-child(1)"
    assert css["full"] == "svg > defs:nth-child(1) > linearGradient#grad:nth-child(1)"
    assert selectors.variants(found, grad, "xpath")["explicit"] == "/svg/defs[1]/linearGradient[1]"


def test_unique_form_needs_positions_when_nothing_else_tells_apart():
    found = elements_of(LIST, html=True)
    second = [e.index for e in found if e.tag == "li"][1]
    css = selectors.variants(found, second, "css")
    xpath = selectors.variants(found, second, "xpath")
    assert css["unique"] == "li:nth-child(2)"
    assert xpath["unique"] == "//li[2]"
    assert css["explicit"] == "ul > li:nth-child(2)"
    assert xpath["full"] == "/ul/li[2]"


def test_every_element_has_forms_that_select_exactly_it():
    for text, html in ((SVG, False), (LIST, True), (PAGE, True)):
        found = elements_of(text, html=html)
        for element in found:
            path = selectors.chain(found, element.index)
            for flavour in ("css", "xpath"):
                unique = selectors._unique(found, path, flavour)
                full = selectors._full_steps(path, flavour)
                explicit = selectors._explicit_steps(path, flavour)
                assert selectors.matching(found, unique, flavour) == [element.index], (element.tag, flavour)
                assert selectors.matching(found, full, flavour) == [element.index], (element.tag, flavour)
                assert selectors.matching(found, explicit, flavour) == [element.index], (element.tag, flavour)


def test_implicit_form_uses_ids_and_classes_as_anchors():
    found = elements_of(PAGE, html=True)
    third = next(e for e in found if e.tag == "p" and e.classes == ("item",) and e.id == "")
    assert selectors.variants(found, third.index, "css")["implicit"] == "#main.page .item"
    assert selectors.variants(found, third.index, "xpath")["implicit"].startswith("//div[@id='main']")


def test_element_under_the_cursor():
    found = elements_of(PAGE, html=True)
    line = PAGE.split("\n")[3]  # the line 4: <p class="item">two <b>bold</b></p>
    bold = markup.element_at(found, PAGE, 4, line.index("bold") + 2)
    assert bold is not None and bold.tag == "b"
    start_tag = markup.element_at(found, PAGE, 4, 2)
    assert start_tag is not None and start_tag.tag == "p"
    assert markup.element_at(found, PAGE, 1, 1).tag == "html"


def test_menu_items_copy_texts():
    found = elements_of(SVG)
    rect = next(e.index for e in found if e.tag == "rect")
    items = dict(selectors.menu_items(found, rect, "logo.svg:5:3"))
    assert items["Copy id:  box"] == "box"
    assert items["Copy tag:  rect"] == "rect"
    assert items["Copy location:  logo.svg:5:3"] == "logo.svg:5:3"
    assert "#box" in items.values()
