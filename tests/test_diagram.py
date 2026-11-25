"""The layout of the class diagram (ogmkdev/diagram.py), without a display: the supertypes stand left of the
class, the subtypes right of it, and the boxes and edges are found at their positions."""

import unittest

from ogmkdev import diagram
from ogmkdev.index import Symbol


class DiagramLayoutTests(unittest.TestCase):
    def test_layout_puts_supertypes_left_and_subtypes_right(self):
        class_symbol = Symbol("App\\Circle", "class", "/p/Circle.php", 5, 1)
        tree = {"name": "App\\Circle", "symbol": class_symbol,
                "up": [{"name": "App\\Shape", "symbol": None, "children": []}],
                "down": [{"name": "App\\Square", "symbol": Symbol("App\\Square", "class", "/p/Square.php", 3, 1),
                          "children": []}]}
        boxes, edges, (width, height) = diagram.layout(tree)
        by_name = {b.name: b for b in boxes}
        self.assertLess(by_name["App\\Shape"].x, by_name["App\\Circle"].x)
        self.assertLess(by_name["App\\Circle"].x, by_name["App\\Square"].x)
        self.assertEqual(by_name["App\\Shape"].kind, "external")
        self.assertIn(diagram.Edge("App\\Circle", "App\\Shape"), edges)
        self.assertIn(diagram.Edge("App\\Square", "App\\Circle"), edges)
        self.assertIsNotNone(diagram.box_at(boxes, by_name["App\\Circle"].x + 1, by_name["App\\Circle"].y + 1))


if __name__ == "__main__":
    unittest.main()
