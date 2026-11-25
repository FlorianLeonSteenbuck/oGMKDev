"""JSON, XML/SVG, HTML and CSS-family checks, id declarations and the element structure."""

from ogmkdev import diagnostics, languages, markup


def codes(path, text):
    return [(d.code, d.severity, d.line) for d in diagnostics.analyze(text, languages.detect(path, {}))]


def test_json_syntax_error_has_position():
    # the wording of the json module differs between Python versions; the line and the prefix do not
    problems = markup.json_problems('{\n  "a": 1,\n}')
    assert problems and problems[0][0] in (2, 3) and problems[0][2].startswith("JSON syntax error")


def test_empty_json_and_bom_are_fine():
    assert markup.json_problems("") == []
    assert markup.json_problems('﻿{"a": 1}') == []


def test_xml_mismatched_tag():
    problems = markup.xml_problems("<a>\n  <b></a>")
    assert problems and problems[0][0] == 2 and "mismatched tag" in problems[0][2]


def test_svg_ids_and_duplicates():
    svg = '<svg>\n  <rect id="box"/>\n  <use href="#box"/>\n  <g id="box"/>\n</svg>'
    assert [(name, line, tag) for name, line, _c, tag in markup.id_positions(svg)] == [
        ("box", 2, "rect"), ("box", 4, "g")]
    assert markup.duplicate_id_problems(svg) == [(4, 10, "duplicate id 'box' (first at line 2)")]
    assert ("duplicate-id", "warning", 4) in codes("icon.svg", svg)


def test_data_id_is_not_an_id():
    assert markup.id_positions('<div data-id="x" grid-id="y"/>') == []


def test_css_braces():
    assert markup.braces_problems(".a { color: red; } }") == [(1, 20, "unexpected '}'")]
    assert markup.braces_problems(".a { x: '}' } /* { */") == []
    assert markup.braces_problems(".a {\n  b: c;") == [(1, 4, "'{' is never closed")]


def test_scss_line_comments_are_skipped_and_sass_has_no_braces():
    assert markup.braces_problems("// {\n.a { b: c }", line_comments=True) == []
    assert codes("style.sass", ".a\n  color: red\n") == []


def test_elements_of_xml_and_html():
    nodes, error = markup.elements('<root id="r">\n  <item class="x y"/>\n</root>')
    assert error is None
    assert [(n["depth"], markup.label(n)) for n in nodes] == [(0, "root#r"), (1, "item.x.y")]
    html, error = markup.elements('<div id="top"><p>hi<br></p></div>', html=True)
    assert error is None
    assert [(n["depth"], n["tag"]) for n in html] == [(0, "div"), (1, "p"), (2, "br")]


def test_language_detection_of_the_new_formats():
    assert [languages.detect(p, {}).language for p in
            ("a.iml", "b.xsd", "c.xslt", "d.svg", "e.scss", "f.sass", "g.less", "h.json")] == [
        "xml", "xsd", "xslt", "svg", "scss", "sass", "less", "json"]


def test_xslt_document_call_and_imports_are_references():
    line = '<xsl:copy-of select="document(\'data/items.xml\')//item"/> <xsl:import href="common.xsl"/>'
    assert markup.reference_at(line, line.index("items") + 1) == "data/items.xml"
    assert markup.reference_at(line, line.index("common") + 1) == "common.xsl"
    assert markup.reference_at(line, line.index("select") + 1) is None


def test_reference_under_the_cursor():
    line = '  <use xlink:href="#box"/> <xsl:import href="common.xsl"/> <img src="logo.png"/>'
    assert markup.reference_at(line, line.index("#box") + 2) == "#box"
    assert markup.reference_at(line, line.index("common") + 1) == "common.xsl"
    assert markup.reference_at(line, line.index("logo") + 1) == "logo.png"
    assert markup.reference_at(line, line.index("href") + 1) is None  # on the attribute name, not the value
    assert markup.reference_at('@import "base.css";', 12) == "base.css"
    assert markup.reference_at('background: url("img/a.png")', 20) == "img/a.png"


def test_xsd_and_xslt_declarations_are_indexed_by_name():
    from ogmkdev import index
    schema = ('<?xml version="1.0"?>\n<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
              '  <xs:complexType name="Address">\n    <xs:sequence/>\n  </xs:complexType>\n'
              '  <xs:element name="cart" type="Address"/>\n</xs:schema>')
    found = [(s.name, s.kind, s.line) for s in index.extract("shop.xsd", schema)]
    assert ("Address", "declaration", 3) in found and ("cart", "declaration", 6) in found
    sheet = ('<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform">\n'
             '  <xsl:template name="price"/>\n</xsl:stylesheet>')
    assert [(s.name, s.kind) for s in index.extract("print.xsl", sheet)] == [("price", "declaration")]


def test_xsd_and_xslt_have_generation_templates():
    from ogmkdev import templates
    xsd = {t.trigger for t in templates.registry_for("xsd", None, {}).templates}
    xslt = {t.trigger for t in templates.registry_for("xslt", None, {}).templates}
    assert {"schema", "element", "complex", "import"} <= xsd
    assert {"stylesheet", "template", "call", "import", "include"} <= xslt
