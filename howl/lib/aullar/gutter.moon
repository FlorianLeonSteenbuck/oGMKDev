-- Copyright 20222-2024 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

ffi = require 'ffi'
{:define_class} = require 'aullar.util'
Pango = require 'ljglibs.pango'
{:RGBA} = require 'ljglibs.gdk'
Layout = Pango.Layout
Gtk = require 'ljglibs.gtk'
pango_cairo = Pango.cairo

-- the colours of the change stripes: added, changed and deleted lines (fixed, like the breakpoint dots)
CHANGE_COLOURS = {
  added: {0.247, 0.725, 0.314}
  changed: {0.345, 0.651, 1.0}
  deleted: {0.973, 0.318, 0.286}
}

ffi_cast = ffi.cast
int_t = ffi.typeof 'int'
cairo_t = ffi.typeof 'cairo_t *'

define_class {

  new: (@view, config) =>
    @number_chars = 0
    @first_line = 0
    @last_line = 0
    @area = Gtk.DrawingArea {vexpand: true, css_classes: {'gutter'}}
    @area\set_draw_func_for @, self._draw
    @click = Gtk.GestureClick!
    @click.button = 0
    @area\add_controller @click
    @click\connect_for @, 'pressed', self._on_pressed
    @reconfigure config
    @sync view

  properties: {
    visible: {
      get: => @area.visible
      set: (visible) => @area.visible = visible
    }

    -- includes the theme's padding around the numbers
    width: => @area\measure(Gtk.ORIENTATION_HORIZONTAL, -1).natural
  }

  sync: =>
    return unless @area.visible
    view_first = @view.first_visible_line
    view_last = @view.last_visible_line + 1
    if view_first != @first_line or view_last != @last_line
      @first_line = view_first
      @last_line = view_last
      @area\queue_draw!

  to_gobject: => @area

  -- redraws the marks (breakpoints) after they changed
  refresh: => @area\queue_draw!

  -- sets the colour of one kind of change stripe: 'added', 'changed' or 'deleted', as {red, green, blue} from 0
  -- to 1; the colours are shared by all gutters
  set_change_colour: (kind, colour) =>
    CHANGE_COLOURS[kind] = colour

  release: =>

  reconfigure: (config) =>
    @foreground = RGBA(config.gutter_color)

  sync_dimensions: (buffer, opts = {}) =>
    return unless @area.visible
    lines_text = tostring(buffer.nr_lines)
    num_chars = #lines_text
    changed = @number_chars != num_chars
    return true if not opts.force and not changed
    -- room on the left for the breakpoint dots (see _draw)
    -- room on the left for the breakpoint dots, on the right for the fold arrows (see _draw)
    @_text_width = math.ceil(@view\text_dimensions(lines_text).width) + 34
    @area.content_width = @_text_width
    @number_chars = num_chars
    not changed

  _draw: (_, cr, width, height) =>
    cr = ffi_cast cairo_t, cr
    width = tonumber(ffi_cast int_t, width)
    height = tonumber(ffi_cast int_t, height)

    if width != @_text_width
      @area\queue_resize!
      return

    return if not @view.showing or not @area.visible

    p_ctx = @area.pango_context
    d_lines = @view.display_lines

    c = @foreground
    cr\set_source_rgba c.red, c.green, c.blue, c.alpha

    layout = Layout p_ctx
    layout.width = (@_text_width - 14) * Pango.SCALE
    layout.alignment = Pango.ALIGN_RIGHT

    y = 0

    for line_nr = @first_line, @last_line
      d_line = d_lines[line_nr]
      break unless d_line
      continue if d_line.hidden
      layout.text = tostring line_nr

      _, text_height = layout\get_pixel_size!
      line_height = d_line.height
      total_height = line_height

      if d_line.is_wrapped
        layout_line = d_line.layout\get_line_readonly 0
        _, log_rect = layout_line\get_pixel_extents!
        line_height = log_rect.height

      cr\move_to 0, y + (line_height - text_height) / 2
      pango_cairo.show_layout cr, layout

      if @_mark_at(line_nr) == 'breakpoint'
        cr\save!
        cr\set_source_rgba 0.86, 0.19, 0.19, 1
        -- in the frame the first pixels of the gutter get no presses, so the dot is drawn right of them
        cr\arc 12, y + total_height / 2, 4.5, 0, 2 * math.pi
        cr\fill!
        cr\restore!

      change = @_change_at line_nr
      if change
        cr\save!
        colour = CHANGE_COLOURS[change]
        cr\set_source_rgba colour[1], colour[2], colour[3], 1
        if change == 'deleted' -- a triangle at the top of the line: lines were removed above it
          cr\move_to 0, y
          cr\line_to 5, y + 3
          cr\line_to 0, y + 6
          cr\close_path!
        else
          cr\rectangle 0, y, 4, total_height
        cr\fill!
        cr\restore!

      fold = @_fold_mark line_nr
      if fold
        x0, mid = @_text_width - 11, y + total_height / 2
        cr\save!
        cr\set_source_rgba c.red, c.green, c.blue, 0.75
        if fold == 'open' -- a triangle pointing down
          cr\move_to x0, mid - 3
          cr\line_to x0 + 7, mid - 3
          cr\line_to x0 + 3.5, mid + 3
        else -- a closed fold: a triangle pointing right
          cr\move_to x0, mid - 4
          cr\line_to x0 + 6, mid
          cr\line_to x0, mid + 4
        cr\close_path!
        cr\fill!
        cr\restore!

      y += d_line.slot

  -- the mark the view's listener gives the line ('breakpoint' or nil)
  _mark_at: (line_nr) =>
    listener = @view.listener
    return nil unless listener and listener.gutter_mark
    listener.gutter_mark @view, line_nr

  -- 'added', 'changed', 'deleted' or nil for the change of a line since the file was saved
  _change_at: (line_nr) =>
    listener = @view.listener
    return nil unless listener and listener.gutter_change
    listener.gutter_change @view, line_nr

  -- 'open' or 'closed' for a line that can be folded, nil otherwise
  _fold_mark: (line_nr) =>
    listener = @view.listener
    return nil unless listener and listener.gutter_fold
    listener.gutter_fold @view, line_nr

  -- the line number at the height y of the gutter (nil below the last line)
  _line_at: (y) =>
    d_lines = @view.display_lines
    top = 0
    for line_nr = @first_line, @last_line
      d_line = d_lines[line_nr]
      break unless d_line
      continue if d_line.hidden
      return line_nr if y < top + d_line.slot
      top += d_line.slot
    nil

  _on_pressed: (g_click, n_press, x, y) =>
    listener = @view.listener
    return unless listener and listener.on_gutter_click
    line_nr = @_line_at tonumber(y)
    return unless line_nr
    -- the fold arrows are at the right edge, the rest of the gutter sets breakpoints
    region = tonumber(x) >= @_text_width - 14 and 'fold' or 'breakpoint'
    listener.on_gutter_click @view, line: line_nr, button: g_click\get_current_button!, :region
}
