-- Copyright 2012-2014-2015 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

{:app, :breadcrumbs, :command, :config, :mode} = howl
{:style, :ActionBuffer, :BufferPopup, :StyledText} = howl.ui
serpent = require 'serpent'



command.register
  name: 'describe-style',
  description: 'Describe the current style at cursor'
  handler: ->
    name = style.at_pos app.editor.buffer, app.editor.cursor.pos
    unless name
      log.info "Unstyled"
      return

    def = style[name]
    editor = app.editor
    buf = ActionBuffer!
    buf\append name, 'h1'
    buf\append "\n\n"
    def_s = serpent.block def, comment: false
    lua_mode = mode.by_name 'lua'

    if lua_mode
      styles = lua_mode.lexer(def_s)
      def_s = StyledText def_s, styles

    buf\append def_s
    editor\show_popup BufferPopup buf

command.register
  name: 'zoom-in',
  description: 'Increase the current font size by 1 (globally)'
  handler: ->
    size = config.font_size + 1
    config.font_size = size
    log.info "zoom-in: global font size set to #{size}"

command.register
  name: 'zoom-out',
  description: 'Decrease the current font size by 1 (globally)'
  handler: ->
    size = config.font_size - 1
    if size <= 6
      log.error 'zoom-out: minimum font size reached (6)'
    else
      config.font_size = size
      log.info "zoom-out: global font size set to #{size}"
