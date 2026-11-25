"""Class diagram geometry: boxes and inheritance edges laid out from a hierarchy tree.

The layout is pure data (no GUI). Supertypes go to the left, subtypes to the right, one column per
inheritance level; the selected class sits in the middle. The GUI draws the result (ui/panels.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Box:
    name: str
    kind: str
    x: float
    y: float
    width: float
    height: float
    file: str = ""
    line: int = 0
    column: int = 0
    root: bool = False
    grid_column: int = 0     # inheritance level, starting at 0 for the leftmost column
    grid_row: int = 0


@dataclass(frozen=True)
class Edge:
    child: str     # the subclass or implementing type
    parent: str    # the supertype it extends or implements


def layout(tree: dict, box_width: float = 200.0, box_height: float = 34.0,
           gap_x: float = 70.0, gap_y: float = 14.0) -> Tuple[List[Box], List[Edge], Tuple[float, float]]:
    columns: Dict[int, List[Tuple[str, Optional[object], str]]] = {0: [(tree["name"], tree.get("symbol"), "root")]}
    edges: List[Edge] = []

    def visit_up(nodes, level, parent):
        for node in nodes:
            entry = (node["name"], node.get("symbol"), "up")
            columns.setdefault(level, []).append(entry)
            edges.append(Edge(child=parent, parent=node["name"]))
            visit_up(node.get("children", []), level - 1, node["name"])

    def visit_down(nodes, level, parent):
        for node in nodes:
            entry = (node["name"], node.get("symbol"), "down")
            columns.setdefault(level, []).append(entry)
            edges.append(Edge(child=node["name"], parent=parent))
            visit_down(node.get("children", []), level + 1, node["name"])

    visit_up(tree.get("up", []), -1, tree["name"])
    visit_down(tree.get("down", []), 1, tree["name"])

    levels = sorted(columns)
    height_needed = max(len(columns[level]) for level in levels) * (box_height + gap_y)
    boxes: List[Box] = []
    seen = set()
    for level in levels:
        x = (level - min(levels)) * (box_width + gap_x)
        items = columns[level]
        top = (height_needed - len(items) * (box_height + gap_y)) / 2
        for index, (name, symbol, _side) in enumerate(items):
            if (name.lower(), level) in seen:
                continue
            seen.add((name.lower(), level))
            kind = symbol.kind if symbol is not None else "external"
            file = symbol.file if symbol is not None else ""
            line = symbol.line if symbol is not None else 0
            column = symbol.column if symbol is not None else 0
            boxes.append(Box(name, kind, x, top + index * (box_height + gap_y), box_width, box_height,
                             file, line, column, root=(level == 0),
                             grid_column=level - min(levels), grid_row=index))
    width = (max(levels) - min(levels) + 1) * (box_width + gap_x) - gap_x
    return boxes, edges, (max(width, box_width), max(height_needed - gap_y, box_height))


def box_at(boxes: List[Box], x: float, y: float) -> Optional[Box]:
    for box in boxes:
        if box.x <= x <= box.x + box.width and box.y <= y <= box.y + box.height:
            return box
    return None


ZOOM_MIN = 0.5
ZOOM_MAX = 2.0
ZOOM_STEP = 0.1
MARGIN = 12.0       # the space around the boxes in the drawing, in unzoomed units


def clamp_zoom(zoom: float) -> float:
    """The zoom factor within the range the diagram offers, rounded to a thousandth."""
    return round(min(ZOOM_MAX, max(ZOOM_MIN, zoom)), 3)


def route(edge: Edge, boxes: List[Box]) -> List[Tuple[float, float]]:
    """The orthogonal line of an inheritance edge: out of the left side of the subclass, across the gap
    between the columns, and into the right side of the superclass. The subclass is always the right-hand
    box. Empty when one of the boxes is not in the diagram."""
    by_name = {box.name: box for box in boxes}
    child, parent = by_name.get(edge.child), by_name.get(edge.parent)
    if child is None or parent is None:
        return []
    start = (child.x, child.y + child.height / 2)
    end = (parent.x + parent.width, parent.y + parent.height / 2)
    middle = (start[0] + end[0]) / 2
    return [start, (middle, start[1]), (middle, end[1]), end]


def arrow_head(parent: Box, size: float = 10.0) -> List[Tuple[float, float]]:
    """The hollow triangle of an inheritance arrow: its tip touches the right side of the superclass."""
    tip = (parent.x + parent.width, parent.y + parent.height / 2)
    return [tip, (tip[0] + size, tip[1] - size * 0.6), (tip[0] + size, tip[1] + size * 0.6)]


def content_size(layout_size: Tuple[float, float], zoom: float) -> Tuple[float, float]:
    """The size of the drawing at a zoom factor, with the margin around the boxes."""
    width, height = layout_size
    return width * zoom + 2 * MARGIN, height * zoom + 2 * MARGIN
