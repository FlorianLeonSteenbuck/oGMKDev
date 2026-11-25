"""The class diagram of the Hierarchy tab (GTK 4): one column per inheritance level, the selected class in
the middle, supertypes to the left and subtypes to the right. Each class is a box that opens its declaration
on a click. An inheritance edge is an orthogonal line that ends in a hollow arrow at the supertype. The
diagram zooms with its buttons or with Ctrl and the mouse wheel. The geometry comes from
:mod:`ogmkdev.diagram`; this widget only draws it.
"""

from __future__ import annotations

from typing import Callable, Dict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo  # noqa: E402

from .. import diagram as geometry  # noqa: E402
from .theme import palette_for  # noqa: E402

BOX_RADIUS = 6.0


def _rgb(colour: str):
    """An '#rrggbb' colour as the three floats cairo takes."""
    colour = colour.lstrip("#")
    return tuple(int(colour[index:index + 2], 16) / 255 for index in (0, 2, 4))


class ClassDiagram(Gtk.Box):
    def __init__(self, on_activate: Callable[[str, int, int], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._on_activate = on_activate
        self._palette: Dict[str, str] = palette_for("light", "blend")
        self.boxes: list = []
        self.edges: list = []
        self.routes: list = []          # (points, superclass box) for each inheritance edge
        self.size = (geometry.MARGIN * 2, geometry.MARGIN * 2)
        self.zoom = 1.0

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, action in (("−", self.zoom_out), ("100 %", self.zoom_reset), ("+", self.zoom_in)):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _button, step=action: step())
            bar.append(button)
        self._zoom_label = Gtk.Label(xalign=0)
        bar.append(self._zoom_label)
        self.append(bar)

        self.area = Gtk.DrawingArea()
        self.area.set_draw_func(self._draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.area.add_controller(click)
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.connect("scroll", self._on_scroll)
        self.area.add_controller(wheel)
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.area)
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)
        self.append(scroller)
        self.set_vexpand(True)
        self._update_zoom_label()

    # ------------------------------------------------------------ content

    def show(self, tree: dict) -> None:
        self.boxes, self.edges, self.size = geometry.layout(tree)
        by_name = {box.name: box for box in self.boxes}
        self.routes = []
        for edge in self.edges:
            points = geometry.route(edge, self.boxes)
            parent = by_name.get(edge.parent)
            if points and parent is not None:
                self.routes.append((points, parent))
        self._resize()
        self.area.queue_draw()

    def set_palette(self, palette: Dict[str, str]) -> None:
        """The colours of the diagram: the palette of the frame's mode and scheme."""
        self._palette = palette
        self.area.queue_draw()

    # ------------------------------------------------------------- zoom

    def set_zoom(self, zoom: float) -> None:
        self.zoom = geometry.clamp_zoom(zoom)
        self._update_zoom_label()
        self._resize()
        self.area.queue_draw()

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom + geometry.ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom - geometry.ZOOM_STEP)

    def zoom_reset(self) -> None:
        self.set_zoom(1.0)

    def _update_zoom_label(self) -> None:
        self._zoom_label.set_text(f"{round(self.zoom * 100)} %")

    def _resize(self) -> None:
        width, height = geometry.content_size(self.size, self.zoom)
        self.area.set_content_width(int(width))
        self.area.set_content_height(int(height))

    def _on_scroll(self, controller, _dx: float, dy: float) -> bool:
        if controller.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            self.set_zoom(self.zoom - dy * geometry.ZOOM_STEP)
            return True
        return False

    # ------------------------------------------------------------ clicks

    def _on_pressed(self, _gesture, _n_press: int, x: float, y: float) -> None:
        box = geometry.box_at(self.boxes, (x - geometry.MARGIN) / self.zoom, (y - geometry.MARGIN) / self.zoom)
        if box is not None:
            self._activate(box)

    def _activate(self, box) -> None:
        if box.file:
            self._on_activate(box.file, box.line, box.column)

    # ----------------------------------------------------------- drawing

    def _draw(self, _area, cr, _width: int, _height: int) -> None:
        colours = self._palette
        cr.translate(geometry.MARGIN, geometry.MARGIN)
        cr.scale(self.zoom, self.zoom)
        line_colour = _rgb(colours.get("comment", "#888888"))
        background = _rgb(colours.get("background", "#ffffff"))
        cr.set_line_width(1.5)
        for points, _parent in self.routes:
            cr.set_source_rgb(*line_colour)
            cr.move_to(*points[0])
            for point in points[1:]:
                cr.line_to(*point)
            cr.stroke()
        for _points, parent in self.routes:
            head = geometry.arrow_head(parent)
            cr.move_to(*head[0])
            cr.line_to(*head[1])
            cr.line_to(*head[2])
            cr.close_path()
            cr.set_source_rgb(*background)
            cr.fill_preserve()
            cr.set_source_rgb(*line_colour)
            cr.stroke()
        for box in self.boxes:
            self._draw_box(cr, box, colours, background)

    def _draw_box(self, cr, box, colours: Dict[str, str], background) -> None:
        x, y, w, h = box.x, box.y, box.width, box.height
        radius = BOX_RADIUS
        cr.new_sub_path()
        cr.arc(x + w - radius, y + radius, radius, -1.5708, 0)
        cr.arc(x + w - radius, y + h - radius, radius, 0, 1.5708)
        cr.arc(x + radius, y + h - radius, radius, 1.5708, 3.1416)
        cr.arc(x + radius, y + radius, radius, 3.1416, 4.7124)
        cr.close_path()
        cr.set_source_rgb(*_rgb(colours.get("chrome", "#eeeeee")))
        cr.fill_preserve()
        border = colours.get("accent", "#3366cc") if box.root else colours.get("chrome_border", "#999999")
        cr.set_source_rgb(*_rgb(border))
        cr.set_line_width(2.0 if box.root else 1.0)
        cr.stroke()
        label = box.name.rsplit("\\", 1)[-1]
        text_colour = colours.get("foreground", "#000000") if box.kind != "external" else colours.get("comment", "#888888")
        cr.set_source_rgb(*_rgb(text_colour))
        name = PangoCairo.create_layout(cr)
        name.set_font_description(Pango.FontDescription.from_string("Sans bold 11" if box.root else "Sans 11"))
        name.set_width(int((w - 16) * Pango.SCALE))
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_text(label, -1)
        cr.move_to(x + 8, y + 3)
        PangoCairo.show_layout(cr, name)
        kind = PangoCairo.create_layout(cr)
        kind.set_font_description(Pango.FontDescription.from_string("Sans 8"))
        kind.set_text(box.kind, -1)
        cr.move_to(x + 8, y + h - 14)
        PangoCairo.show_layout(cr, kind)
