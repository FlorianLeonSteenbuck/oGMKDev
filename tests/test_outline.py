"""The outline of a JavaScript or TypeScript file (ogmkdev/outline.py): the declarations, their members, and the
line and column of each name. Pure Python, no display needed."""

import unittest

from ogmkdev import outline as O

JS = """import x from 'y';
export class Animal extends Base {
  name = 'a';
  static count = 0;
  constructor(n) { super(); this.n = n; }
  get size() { return 1; }
  #secret = 2;
  speak() { return 1; }
}
export function greet(who) { return who; }
const shout = (text) => text.toUpperCase();
let total = 0;
const make = function () {};
export default class extends Base {}
"""

TS = """export interface Shape extends Base<T> { area(): number; readonly name: string }
type Pair<T> = [T, T];
export enum Color { Red, Green = 2 }
namespace Geo { export const origin = 0; export function dist() {} }
abstract class Circle<T> implements Shape {
  private radius: number = 1;
  constructor(public label: string) { super(); }
  abstract area(): number;
  static #count = 0;
}
declare function fetchIt(url: string): void;
"""


def _labels(items):
    return [(item.kind, item.label) for item in items]


class JavaScriptOutlineTest(unittest.TestCase):
    def setUp(self):
        self.items, self.error = O.script_outline(JS)

    def test_the_declarations_are_listed_in_file_order(self):
        self.assertIsNone(self.error)
        self.assertEqual(_labels(self.items), [
            ("class", "class Animal"),
            ("function", "function greet"),
            ("function", "const shout"),
            ("variable", "let total"),
            ("function", "const make"),
            ("class", "class"),
        ])

    def test_the_members_of_a_class_are_its_children(self):
        members = self.items[0].children
        self.assertEqual(_labels(members), [
            ("field", "name"),
            ("field", "static count"),
            ("method", "constructor()"),
            ("accessor", "get size"),
            ("field", "#secret"),
            ("method", "speak()"),
        ])

    def test_each_item_has_the_line_and_column_of_its_name(self):
        animal, greet, shout = self.items[0], self.items[1], self.items[2]
        self.assertEqual((animal.line, animal.column), (2, 14))
        self.assertEqual((greet.line, greet.column), (10, 17))
        self.assertEqual((shout.line, shout.column), (11, 7))
        self.assertEqual((animal.children[5].line, animal.children[5].column), (8, 3))

    def test_an_anonymous_class_takes_no_name_from_its_superclass(self):
        self.assertEqual(self.items[-1].label, "class")
        self.assertEqual(self.items[-1].children, [])


class TypeScriptOutlineTest(unittest.TestCase):
    def setUp(self):
        self.items, self.error = O.script_outline(TS, typed=True)

    def test_the_typescript_declarations_are_listed(self):
        self.assertIsNone(self.error)
        self.assertEqual(_labels(self.items), [
            ("interface", "interface Shape"),
            ("type", "type Pair"),
            ("enum", "enum Color"),
            ("namespace", "namespace Geo"),
            ("class", "abstract class Circle"),
            ("function", "function fetchIt"),
        ])

    def test_interface_members_enum_members_and_namespace_declarations_are_children(self):
        shape, color, geo = self.items[0], self.items[2], self.items[3]
        self.assertEqual(_labels(shape.children), [("member", "area()"), ("member", "name")])
        self.assertEqual(_labels(color.children), [("member", "Red"), ("member", "Green")])
        self.assertEqual(_labels(geo.children), [("variable", "const origin"), ("function", "function dist")])

    def test_modifiers_are_shown_in_the_label(self):
        circle = self.items[4]
        self.assertEqual(_labels(circle.children), [
            ("field", "private radius"),
            ("method", "constructor()"),
            ("method", "abstract area()"),
            ("field", "static #count"),
        ])


class OutlineErrorsTest(unittest.TestCase):
    def test_a_syntax_error_gives_no_outline_but_the_message_with_its_line(self):
        items, error = O.script_outline("class A {\n  broken(\n}\n")
        self.assertEqual(items, [])
        self.assertTrue(error.startswith("syntax error at line 3:"), error)

    def test_columns_count_characters_not_bytes(self):
        items, error = O.script_outline("const ä = 1; function ö() {}")
        self.assertIsNone(error)
        self.assertEqual([(item.label, item.column) for item in items],
                         [("const ä", 7), ("function ö", 23)])

    def test_count_includes_the_children(self):
        items, _ = O.script_outline(JS)
        self.assertEqual(O.count(items), 12)


if __name__ == "__main__":
    unittest.main()
