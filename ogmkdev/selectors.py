"""CSS selectors and XPath expressions that find one element of an XML, SVG or HTML document.

Four forms for each element, in CSS and in XPath:

* unique: the shortest form that matches exactly this element: its id, class or tag, with the nearest
  ancestors added when needed, and positions as the last resort;
* explicit: the path from the root with tags and positions (``svg > defs:nth-child(1)``, ``/svg/defs[1]``);
* implicit: the path of ids and classes with descendant steps (``#main .item``, ``//div[@id='main']//p``);
* full: the path from the root with tags, ids, classes and positions.

CSS positions are the place among all element siblings (``:nth-child``), XPath positions the place
among the siblings with the same tag (``[n]``). Every unique form is checked against the document with
the matcher of this module, so it selects exactly one element. The full form always does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .markup import Element


@dataclass(frozen=True)
class Step:
    tag: Optional[str]          # None: any element (CSS only)
    id: str = ""
    classes: Tuple[str, ...] = ()
    position: int = 0           # 0: no position
    child: bool = False         # True: a child of the previous step (the root for the first); else a descendant


def _position_of(element: Element, flavour: str) -> int:
    return element.child_position if flavour == "css" else element.type_position


def _position_step(element: Element, flavour: str) -> int:
    """The position a step needs: none for the root element."""
    return 0 if element.parent is None else _position_of(element, flavour)


def chain(elements: Sequence[Element], index: int) -> List[Element]:
    """The elements from the root down to the element with that index."""
    path: List[Element] = []
    current: Optional[int] = index
    while current is not None:
        path.append(elements[current])
        current = elements[current].parent
    return list(reversed(path))


def _attributes_match(element: Element, step: Step, flavour: str) -> bool:
    if step.tag is not None and element.tag != step.tag:
        return False
    if step.id and element.id != step.id:
        return False
    if any(name not in element.classes for name in step.classes):
        return False
    if step.position and _position_of(element, flavour) != step.position:
        return False
    return True


def _matches(elements: Sequence[Element], element: Element, steps: Sequence[Step], k: int, flavour: str) -> bool:
    step = steps[k]
    if not _attributes_match(element, step, flavour):
        return False
    if k == 0:
        return element.parent is None if step.child else True
    parent = element.parent
    if step.child:
        return parent is not None and _matches(elements, elements[parent], steps, k - 1, flavour)
    while parent is not None:
        if _matches(elements, elements[parent], steps, k - 1, flavour):
            return True
        parent = elements[parent].parent
    return False


def matching(elements: Sequence[Element], steps: Sequence[Step], flavour: str) -> List[int]:
    """The indexes of the elements that the steps select, in document order."""
    if not steps:
        return []
    last = len(steps) - 1
    return [element.index for element in elements if _matches(elements, element, steps, last, flavour)]


# ----------------------------------------------------------------------- step forms

def _full_steps(path: Sequence[Element], flavour: str) -> List[Step]:
    return [Step(tag=e.tag, id=e.id, classes=e.classes, position=_position_step(e, flavour), child=True)
            for e in path]


def _explicit_steps(path: Sequence[Element], flavour: str) -> List[Step]:
    return [Step(tag=e.tag, position=_position_step(e, flavour), child=True) for e in path]


def _implicit_steps(path: Sequence[Element], flavour: str) -> List[Step]:
    target = path[-1]
    steps: List[Step] = []
    for element in path:
        if element is not target and not (element.id or element.classes):
            continue
        keep_tag = flavour == "xpath" or (element is target and not (element.id or element.classes))
        steps.append(Step(tag=element.tag if keep_tag else None, id=element.id, classes=element.classes))
    return steps


def _unique_steps(path: Sequence[Element], depth: int, variant: str, flavour: str) -> List[Step]:
    included = path[len(path) - 1 - depth:]
    steps: List[Step] = []
    for element in included:
        tag: Optional[str] = element.tag
        if variant == "short" and flavour == "css" and (element.id or element.classes):
            tag = None
        position = _position_step(element, flavour) if variant == "positional" else 0
        steps.append(Step(tag=tag, id=element.id, classes=element.classes, position=position))
    return steps


def _unique(elements: Sequence[Element], path: Sequence[Element], flavour: str) -> List[Step]:
    target = path[-1]
    for depth in range(len(path)):
        for variant in ("short", "tagged", "positional"):
            steps = _unique_steps(path, depth, variant, flavour)
            if matching(elements, steps, flavour) == [target.index]:
                return steps
    return _full_steps(path, flavour)  # the full path selects exactly one element


# ----------------------------------------------------------------------- rendering

def _literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "'" + value.replace("'", "") + "'"


def render_css(steps: Sequence[Step]) -> str:
    text = ""
    for index, step in enumerate(steps):
        if index:
            text += " > " if step.child else " "
        name = step.tag or ""
        if not name and not (step.id or step.classes):
            name = "*"
        if step.id:
            name += "#" + step.id
        for class_name in step.classes:
            name += "." + class_name
        if step.position:
            name += f":nth-child({step.position})"
        text += name
    return text


def render_xpath(steps: Sequence[Step]) -> str:
    text = ""
    for step in steps:
        name = step.tag or "*"
        if step.id:
            name += f"[@id={_literal(step.id)}]"
        for class_name in step.classes:
            name += f"[contains(concat(' ', normalize-space(@class), ' '), {_literal(' ' + class_name + ' ')})]"
        if step.position:
            name += f"[{step.position}]"
        text += ("/" if step.child else "//") + name
    return text


# ----------------------------------------------------------------------- public

def variants(elements: Sequence[Element], index: int, flavour: str) -> Dict[str, str]:
    """The four forms of the selector (``css``) or the expression (``xpath``) for one element."""
    path = chain(elements, index)
    render = render_css if flavour == "css" else render_xpath
    return {
        "unique": render(_unique(elements, path, flavour)),
        "explicit": render(_explicit_steps(path, flavour)),
        "implicit": render(_implicit_steps(path, flavour)),
        "full": render(_full_steps(path, flavour)),
    }


def selectors(elements: Sequence[Element], index: int) -> Dict[str, Dict[str, str]]:
    """Both families: {"css": {...}, "xpath": {...}}."""
    return {"css": variants(elements, index, "css"), "xpath": variants(elements, index, "xpath")}


FORM_LABELS = (("unique", "unique"), ("explicit", "explicit"), ("implicit", "implicit"), ("full", "full"))


def menu_items(elements: Sequence[Element], index: int, location: str) -> List[Tuple[str, str]]:
    """(label, text) pairs for the context menu: the selectors, the expressions and the element's
    id, class, tag and location. Each text is what a click copies."""
    found = selectors(elements, index)
    element = elements[index]
    items: List[Tuple[str, str]] = []
    for key, name in FORM_LABELS:
        items.append((f"CSS {name}:  {found['css'][key]}", found["css"][key]))
    for key, name in FORM_LABELS:
        items.append((f"XPath {name}:  {found['xpath'][key]}", found["xpath"][key]))
    if element.id:
        items.append((f"Copy id:  {element.id}", element.id))
    if element.classes:
        items.append((f"Copy class:  {' '.join(element.classes)}", " ".join(element.classes)))
    items.append((f"Copy tag:  {element.tag}", element.tag))
    items.append((f"Copy location:  {location}", location))
    return items
