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


def _tree():
    """A class with a supertype on the left and a subtype on the right, as the hierarchy gives them."""
    return {"name": "App\\Circle", "symbol": None,
            "up": [{"name": "App\\Shape", "symbol": None, "children": []}],
            "down": [{"name": "App\\Square", "symbol": None, "children": []}]}


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.boxes, self.edges, _size = diagram.layout(_tree())
        self.by_name = {box.name: box for box in self.boxes}

    def test_every_route_is_orthogonal_and_joins_the_two_sides(self):
        for edge in self.edges:
            points = diagram.route(edge, self.boxes)
            child, parent = self.by_name[edge.child], self.by_name[edge.parent]
            self.assertEqual(points[0], (child.x, child.y + child.height / 2))
            self.assertEqual(points[-1], (parent.x + parent.width, parent.y + parent.height / 2))
            for start, end in zip(points, points[1:]):
                self.assertTrue(start[0] == end[0] or start[1] == end[1], f"a diagonal segment {start} {end}")

    def test_the_route_crosses_the_gap_between_the_columns(self):
        edge = next(e for e in self.edges if e.parent == "App\\Shape")
        points = diagram.route(edge, self.boxes)
        parent = self.by_name["App\\Shape"]
        child = self.by_name["App\\Circle"]
        self.assertGreater(points[1][0], parent.x + parent.width)
        self.assertLess(points[1][0], child.x)

    def test_a_route_with_a_missing_box_is_empty(self):
        self.assertEqual(diagram.route(diagram.Edge("App\\Nope", "App\\Shape"), self.boxes), [])

    def test_the_arrow_head_touches_the_superclass_and_points_back_to_the_subclass(self):
        parent = self.by_name["App\\Shape"]
        head = diagram.arrow_head(parent)
        self.assertEqual(head[0], (parent.x + parent.width, parent.y + parent.height / 2))
        self.assertEqual(len(head), 3)
        self.assertTrue(all(point[0] > head[0][0] for point in head[1:]))


class ZoomTests(unittest.TestCase):
    def test_the_zoom_is_kept_within_its_range(self):
        self.assertEqual(diagram.clamp_zoom(0.1), diagram.ZOOM_MIN)
        self.assertEqual(diagram.clamp_zoom(5), diagram.ZOOM_MAX)
        self.assertEqual(diagram.clamp_zoom(1.2), 1.2)

    def test_the_drawing_grows_with_the_zoom_and_keeps_the_margin(self):
        self.assertEqual(diagram.content_size((100, 50), 2.0), (200 + 2 * diagram.MARGIN, 100 + 2 * diagram.MARGIN))
        self.assertEqual(diagram.content_size((100, 50), 1.0), (100 + 2 * diagram.MARGIN, 50 + 2 * diagram.MARGIN))


if __name__ == "__main__":
    unittest.main()
