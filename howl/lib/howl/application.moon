-- Copyright 2012-2024 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

{:Window, :Editor, :theme} = howl.ui
{:Buffer, :Settings, :mode, :breadcrumbs, :bundle, :bindings, :keymap, :signal, :interact, :timer, :clipboard, :config} = howl
{:File, :Process} = howl.io
{:PropertyObject} = howl.util.moon
Gtk = require 'ljglibs.gtk'
callbacks = require 'ljglibs.callbacks'
{:get_monotonic_time} = require 'ljglibs.glib'
{:C} = require('ffi')
bit = require 'bit'

append = table.insert
coro_create, coro_status = coroutine.create, coroutine.status

non_idle_dispatches = {
  '^signal motion%-',
  '^signal key%-pressed',
  '^signal pressed',
}

is_idle_dispatch = (desc) ->
  for p in *non_idle_dispatches
    return false if desc\find(p) != nil
  true

last_activity = get_monotonic_time!

dispatcher = (f, description, ...) ->
  unless is_idle_dispatch(description)
    last_activity = get_monotonic_time!

  co = coro_create (...) -> f ...
  status, ret = coroutine.resume co, ...

  if status
    if coro_status(co) == 'dead'
      return ret
  else
    error ret, 2

  false

sort_buffers = (buffers, current_buffer=nil) ->
  table.sort buffers, (a, b) ->
    if current_buffer == a return true
    if current_buffer == b return false
    return true if a.showing and not b.showing
    return false if b.showing and not a.showing
    -- if none of the buffers are showing, we compare the last shown time
    unless a.showing
      ls_a = a.last_shown or 0
      ls_b = b.last_shown or 0
      return ls_a > ls_b if ls_a != ls_b
    a.title < b.title

parse_path_args = (paths, cwd=nil) ->
  files = {}
  hints = {}

  for path in *paths
    local file
    line, col = 1, 1

    e_path, s_line, s_col = path\match '^(.+):(%d+):(%d+)$'
    if e_path
      file = e_path
      line = tonumber s_line
      col = s_col
    else
      e_path, s_line = path\match '^(.+):(%d+)$'
      if e_path
        file = e_path
        line = tonumber s_line
      else
        file = path

    files[#files + 1] = File(file, cwd).gfile
    hints[#hints + 1] = "#{line}:#{col}"

  files, hints

class Application extends PropertyObject
  title: 'Howl'

  new: (@root_dir, @args) =>
    @windows = {}
    @_editors = {}
    @_buffers = {}
    @_recently_closed = {}
    bundle.dirs = { @root_dir / 'bundles' }
    @_load_base!
    bindings.push keymap
    @window = nil
    @editor = nil

    callbacks.configure {
      :dispatcher,
      on_error: (e) ->
        _G.log.error e
    }

    signal.connect 'log-entry-appended', (entry) ->
      level = entry.level
      message = entry.message
      return if level == 'traceback'

      if @window and @window.visible
        essentials = entry.essentials

        status = @window.status
        status[level] status, essentials
        @window.command_panel\notify essentials, level
      elseif not @args.spec
        print message

    super!

  @property idle: get: =>
    tonumber(get_monotonic_time! - last_activity) / 1000 / 1000

  @property buffers: get: =>
    buffers = { table.unpack @_buffers }
    sort_buffers buffers, (@editor and @editor.buffer)
    buffers

  @property recently_closed: get: => moon.copy @_recently_closed

  @property editors: get: => @_editors

  @property next_buffer: get: =>
    return @new_buffer! if #@_buffers == 0

    sort_buffers @_buffers
    hidden_buffers = [b for b in *@_buffers when not b.showing]
    return #hidden_buffers > 0 and hidden_buffers[1] or @_buffers[1]

  -- Howl's editor as a widget of a GTK program that runs its own main loop (src/embed.c):
  -- the window Howl creates for the editor is hidden and its content moves into `container`
  embed: (container, file) =>
    @g_app = Gtk.Application 'org.ogmkdev.howl-embedded', Gtk.Application.NON_UNIQUE
    @g_app\register!
    files = if file and file != '' then {file} else {}
    @_load files, {}
    @_move_content @window, container
    -- further editors of the same process (src/embed.c calls this for every later container)
    _G.HOWL_EMBED_ADD = (more_container, more_file) -> @embed_window more_container, more_file
    -- opens a file (line and column 0 for none) in the editor that has the focus (src/embed.c)
    _G.HOWL_EMBED_OPEN = (path, line, column) ->
      loc = file: File(path)
      loc.line_nr = line if line and line > 0
      loc.column = column if column and column > 0
      @open loc, (@editor)
      -- the line is shown: folds that hide it open (src/embed.c howl_open)
      editor = @editor
      if editor and line and line > 0 and editor.buffer.file == File(path)
        editor\reveal_line line
        -- the column of a definition or a search hit (1-based, clamped to the line)
        if column and column > 0
          text_line = editor.buffer.lines[line]
          editor.cursor.column = math.min column, text_line.size + 1 if text_line
    -- runs a Howl command, e.g. "save" (src/embed.c howl_command)
    _G.HOWL_EMBED_COMMAND = (name) -> howl.timer.asap -> howl.command.run name
    -- "path<TAB>line:column<TAB>mode<TAB>modified" of the editor that has the focus (src/embed.c howl_status)
    -- registers a Howl theme file under a name and selects it (src/embed.c howl_theme)
    _G.HOWL_EMBED_THEME = (name, path) ->
      howl.ui.theme.register name, File(path)
      howl.config.theme = name

    -- error hints of a file: wavy underlines with the message as tooltip at the line, from the
    -- frame's diagnostics (src/embed.c howl_inspect). Rows: "line<TAB>start<TAB>end<TAB>type<TAB>message"
    inspection_api = require 'howl.inspect'
    highlight = howl.ui.highlight
    highlight.define_default 'hint',
      type: highlight.WAVY_UNDERLINE
      foreground: '#8a8a8a'
      line_width: 1
      line_type: 'solid'

    _G.HOWL_EMBED_INSPECT = (path, rows) ->
      buffer = @_buffer_for_file File(path)
      return unless buffer
      items = {}
      for row in rows\gmatch '[^\n]+'
        line_nr, start_col, end_col, kind, message = row\match '^(%d+)\t(%d+)\t(%d+)\t(%a+)\t(.*)$'
        if line_nr
          items[#items + 1] = {
            line: tonumber(line_nr)
            start_col: tonumber(start_col)
            end_col: tonumber(end_col)
            type: kind
            :message
          }
      inspection_api.publish buffer, 'ogmkdev', items

    -- the edge line (eclipse-style margin) of the focused editor; 0 for none (src/embed.c howl_edge)
    _G.HOWL_EMBED_EDGE = (path, column) ->
      file = File(path)
      for ed in *@editors
        target = ed.buffer and ed.buffer.file == file and column or 0
        ed.edge_column = target if ed.edge_column != target

    -- Ctrl+click in an editor leaves the word there for the frame (src/embed.c howl_take_click)
    pending_click = nil
    -- the word, the column (1-based, 0 when unknown) and the text of the line, tab separated
    howl.signal.connect 'editor-ctrl-click', (args) ->
      text = (args.line_text or '')\gsub('[\t\n]', ' ')
      pending_click = "#{args.word}\t#{args.column or 0}\t#{text}"
    _G.HOWL_EMBED_TAKE_CLICK = ->
      word = pending_click or ''
      pending_click = nil
      word

    -- breakpoints: a 'breakpoint' marker on the first character of the line; a left click in the
    -- gutter toggles it, the command does so for the current line (used by the frame's menus)
    toggle_breakpoint = (editor, line_nr) ->
      buffer = editor.buffer
      line = buffer.lines[line_nr]
      return false unless line
      set = if #buffer.markers\for_range(line.start_pos, line.start_pos + 1, name: 'breakpoint') > 0
        buffer.markers\remove_for_range line.start_pos, line.start_pos + 1, name: 'breakpoint'
        false
      else
        buffer.markers\add {{name: 'breakpoint', start_offset: line.start_pos, end_offset: line.start_pos + 1}}
        true
      editor.view.gutter\refresh!
      set

    howl.signal.connect 'editor-gutter-click', (args) ->
      toggle_breakpoint args.editor, args.line if args.button == 1

    howl.command.register
      name: 'breakpoint-toggle'
      description: 'Toggles a breakpoint on the current line'
      handler: ->
        editor = @editor
        toggle_breakpoint editor, editor.cursor.line if editor

    -- folds or opens the block of the current line (the gutter's arrows do the same)
    howl.command.register
      name: 'fold-toggle'
      description: 'Folds or unfolds the block that starts on the current line'
      handler: ->
        editor = @editor
        editor\toggle_fold editor.cursor.line if editor

    -- asks the frame for the definition of the word at the cursor (the frame takes it as a Ctrl+click)
    howl.command.register
      name: 'word-definition'
      description: 'Asks the frame for the definition of the word at the cursor'
      handler: ->
        editor = @editor
        group = editor and editor.current_context.word
        if group and not group.empty
          howl.signal.emit 'editor-ctrl-click', editor: editor, word: group.text

    -- inserts text (whole lines) in front of a line of the editor showing a file (src/embed.c howl_insert)
    _G.HOWL_EMBED_INSERT = (path, line, text) ->
      shown = nil
      for ed in *@editors
        if ed.buffer and ed.buffer.file == File(path)
          shown = ed
          break
      return false unless shown
      target = shown.buffer.lines[line]
      return false unless target
      shown.buffer\insert text, target.start_pos
      true

    -- the paths of the files shown in the Howl editors, one per line (src/embed.c howl_files)
    _G.HOWL_EMBED_FILES = ->
      paths = {}
      for ed in *@editors
        path = ed.buffer and ed.buffer.file and ed.buffer.file.path
        paths[#paths + 1] = path if path
      table.concat paths, '\n'

    _G.HOWL_EMBED_STATUS = ->
      editor = @editor
      buffer = editor and editor.buffer
      return '' unless buffer
      path = buffer.file and buffer.file.path or buffer.title
      mode_name = buffer.mode and buffer.mode.name or ''
      state = buffer.modified and 'modified' or 'saved'
      "#{path}\t#{editor.cursor.line}:#{editor.cursor.column}\t#{mode_name}\t#{state}"
    @window

  -- one more window with its own editor, its content moved into `container`
  embed_window: (container, file) =>
    window = @new_window!
    buffer = nil
    if file and file != ''
      path = File file
      buffer = @_buffer_for_file path
      unless buffer
        buffer = @new_buffer mode.for_file path
        buffer.file = path
    editor = @new_editor window: window, buffer: buffer
    @_move_content window, container

  _move_content: (window, container) =>
    ffi = require 'ffi'
    C = ffi.C
    gwindow = window\to_gobject!
    content = C.gtk_window_get_child gwindow
    C.gtk_window_set_child gwindow, nil
    C.gtk_box_append ffi.cast('GtkBox *', container), content
    C.gtk_widget_hide ffi.cast('GtkWidget *', gwindow)

  new_window: (properties = {}) =>
    props = title: @title
    props[k] = v for k, v in pairs(properties)
    window = Window props
    window\set_default_size 1024, 768
    window\connect_for @, 'close-request', self._on_window_close_request
    window\connect_for @, 'destroy', self._on_window_destroyed

    @g_app\add_window window\to_gobject!

    append @windows, window
    @window = window if #@windows == 1
    window

  new_editor: (opts = {}) =>
    editor = Editor opts.buffer or @next_buffer
    (opts.window or @window)\add_view editor, opts.placement or 'right_of'
    append @_editors, editor
    editor\grab_focus!
    editor

  editor_for_buffer: (buffer) =>
    for visible_editor in *@_editors
      if visible_editor.buffer == buffer
        return visible_editor

    nil

  new_buffer: (buffer_mode) =>
    buffer_mode or= mode.by_name 'default'
    buffer = Buffer buffer_mode
    @_append_buffer buffer
    buffer

  add_buffer: (buffer, show = true) =>
    for b in *@buffers
      return if b == buffer

    @_append_buffer buffer
    if show and @editor
      breadcrumbs.drop!
      @editor.buffer = buffer
      @editor

  close_buffer: (buffer, force = false) =>
    unless force
      local prompt
      if buffer.modified
        prompt = "Buffer '#{buffer.title}' is modified, close anyway? "
      elseif buffer.activity and buffer.activity\is_running!
        prompt = "Buffer has a running activity (#{buffer.activity.name}), close anyway? "

      if prompt and @editor
        @editor.buffer = buffer
        return unless interact.yes_or_no :prompt

    @_buffers = [b for b in *@_buffers when b != buffer]

    if buffer.file
      @_add_recently_closed buffer

    if buffer.showing
      for editor in *@editors
        if editor.buffer == buffer
          if editor == @editor -- if showing in the current editor
            breadcrumbs.drop! -- we drop a crumb here

          editor.buffer = @next_buffer

    signal.emit 'buffer-closed', :buffer

  open_file: (file, editor = @editor) =>
    @open :file, editor

  open: (loc, editor) =>
    return unless loc
    unless loc.buffer or loc.file
      error "Malformed loc: either .buffer or .file must be set", 2

    file = loc.file
    buffer = loc.buffer or @_buffer_for_file(file)

    if buffer
      @add_buffer buffer
    else
      -- open the file specified
      buffer = @new_buffer mode.for_file file
      status, err = pcall -> buffer.file = file
      if not status
        @close_buffer buffer
        error "Failed to open #{file}: #{err}"

      @_recently_closed = [file_info for file_info in *@_recently_closed when file_info.file != buffer.file]
      signal.emit 'file-opened', :file, :buffer

    -- all right, now we got a buffer, let's get an editor if needed
    unless editor
      editor = @editor_for_buffer(loc.buffer) or @editor
      editor or= @new_editor buffer

    -- buffer and editor in place, drop a crumb and show the location
    breadcrumbs.drop {
      buffer: editor.buffer,
      pos: editor.cursor.pos,
      line_at_top: editor.line_at_top
    }

    editor.buffer = buffer

    if loc.line_nr
      editor.line_at_center = loc.line_nr
      opts = line: loc.line_nr
      if loc.column
        opts.column = loc.column
      elseif loc.column_index
        opts.column_index = loc.column_index
      elseif loc.byte_column
        line = buffer.lines[loc.line_nr]
        opts.column_index = line\char_offset(math.min(loc.byte_column, line.size + 1)) if line

      editor.cursor\move_to opts

      if loc.highlights
        for hl in *loc.highlights
          editor\highlight hl, loc.line_nr

    -- drop another breadcrumb at the new location
    breadcrumbs.drop!

    buffer, editor

  save_all: =>
    for b in *@buffers
      if b.modified
        unless b.file
          log.error "No file associated with modified buffer '#{b}'"
          return false

        b\save!

    true

  synchronize: =>
    timer.after_exactly 0.2, -> clipboard.synchronize!

    reload_count = 0
    changed_count = 0

    for b in *@_buffers
      if b.modified_on_disk
        changed_count += 1
        unless b.modified
          b\reload!
          reload_count += 1

    if changed_count > 0
      msg = "Files modified on disk: #{reload_count} buffer(s) reloaded"
      stale_count = changed_count - reload_count
      if stale_count > 0
        log.warn "#{msg}, #{stale_count} modified buffer(s) left"
      else
        log.info msg

  run: =>
    jit.off true, true
    args = @args
    app_base = 'io.howl.Editor'
    flags = bit.bor(
      Gtk.Application.HANDLES_OPEN,
      Gtk.Application.HANDLES_COMMAND_LINE
    )
    @g_app = Gtk.Application app_base, flags
    @g_app\register!

    -- by default, files are opened in the running instance (ogmkdev change: the
    -- command line hands them over to the primary instance); --new-instance starts a
    -- separate instance instead
    if @g_app.is_remote and @args.new_instance
      -- well, this it not particularly intuitive, but we "run" this instance
      -- of the app, causing it to finish off correctly without warning
      @g_app\run {}

      @g_app = Gtk.Application "#{app_base}-#{os.time!}", bit.bor(
        flags,
        Gtk.Application.NON_UNIQUE
      )
      @g_app\register!

    @g_app\connect_for @, 'activate', self._on_activate

    -- XXX GTK4 change this as well to use connect_for
    @g_app\on_open (_, files, hint) ->
      hints = [h for h in hint\gmatch '[^,]+']
      @_load files, hints

    @g_app\connect_for @, 'command_line', self._on_command_line

    signal.connect 'window-focused', self\synchronize
    signal.connect 'editor-released', (s_args) ->
      @_editors =  [e for e in *@_editors when e != s_args.editor]

    breadcrumbs.init!

    @g_app\run args

  quit: (force = false) =>
    if force or not @_should_abort_quit!
      unless #@args > 1
        @save_session!

        if config.save_config_on_exit
          unless pcall config.save_config
            print 'Error saving config'

      for _, process in pairs Process.running
        process\send_signal 'KILL'

      for win in * moon.copy @windows
        win.command_panel\cancel!
        win\destroy!

  save_session: =>
    return if @args.no_profile or #@args > 1

    session = {
      version: 1
      buffers: {}
      recently_closed: {}
      window: {
        maximized: @window.maximized
        fullscreen: @window.fullscreen
      }
    }

    for b in *@buffers
      continue unless b.file
      append session.buffers, {
        file: b.file.path
        last_shown: b.last_shown
        properties: b.properties
      }

    for f in *@_recently_closed
      append session.recently_closed, {
        file: f.file.path
        last_shown: f.last_shown
      }

    @settings\save_system 'session', session

  pump_mainloop: (max_count = 100) =>
    jit.off true, true
    count = 0
    ctx = C.g_main_context_default!
    while count < max_count and C.g_main_context_iteration(ctx, false) != 0
      count += 1

  _append_buffer: (buffer) =>
    if config.autoclose_single_buffer and #@_buffers == 1
      present = @_buffers[1]
      if not present.file and not present.modified and present.length == 0
        @_buffers[1] = buffer
        return

    append @_buffers, buffer

  _buffer_for_file: (file) =>
    for b in *@buffers
      return b if b.file == file

    nil

  _load: (files = {}, hints = {}) =>
    local window

    -- bootstrap if we're booting up
    unless @_loaded
      @settings = Settings!
      config.load_config!
      @_load_core!
      if @settings.dir and not @args.no_profile
        append bundle.dirs, @settings.dir\join 'bundles'
        fonts_dir = @settings.dir\join('fonts')
        if fonts_dir.exists
          C.FcConfigAppFontAddDir(nil, fonts_dir.path)
      if howl.sys.info.is_flatpak
        append bundle.dirs, File '/app/bundles'

      bundle.load_all!

      unless @args.no_profile
        status, ret = pcall @settings.load_user, @settings
        unless status
          log.error "Failed to load user settings: #{ret}"

      theme.apply!
      @_load_application_icon!

      signal.connect 'mode-registered', self\_on_mode_registered
      signal.connect 'mode-unregistered', self\_on_mode_unregistered

      window = @new_window!

      howl.janitor.start!

    -- load files from command line
    loaded_buffers = {}
    for i = 1, #files
      file = File files[i]
      buffer = @_buffer_for_file file

      unless buffer
        buffer = @new_buffer mode.for_file file
        status, ret = pcall -> buffer.file = file
        if not status
          @close_buffer buffer
          buffer = nil
          log.error "Failed to open file '#{file}': #{ret}"

      if buffer
        hint = hints[i]
        if hint
          nums =  [tonumber(v) for v in hint\gmatch('%d+')]
          {line, column} = nums
          buffer.properties.position = :line, :column

        append loaded_buffers, buffer

    -- files we've loaded via a --reuse invocation should be shown
    if #loaded_buffers > 0 and @_loaded
      for i = 1, math.min(#@editors, #loaded_buffers)
        b = loaded_buffers[i]
        pos = b.properties.position
        with @editors[i]
          .buffer = b
          .cursor\move_to pos
          .line_at_center = .cursor.line

    -- all loaded files should be considered as having been viewed just now
    now = howl.sys.time!
    for b in *loaded_buffers
      b.last_shown = now

    -- restore session properties
    unless @_loaded
      unless @args.no_profile
        @_restore_session window, #files == 0

    if #@editors == 0
      @editor = @new_editor @_buffers[1] or @new_buffer!

    for b in *loaded_buffers
      signal.emit 'file-opened', file: b.file, buffer: b

    unless @_loaded
      window\show! if window
      @editor.line_at_center = @editor.cursor.line
      @_loaded = true
      howl.io.File.async = true
      config.broadcast_config!
      signal.emit 'app-ready'
      @_set_initial_status window

  _on_window_close_request: =>
    if #@windows == 1
      modified = [b for b in *@_buffers when b.modified]
      if #modified > 0
        -- postpone the quit check, since we really need to prevent
        -- the close right away by returning true
        timer.asap -> @quit!
      else
        @quit!

      return true

    false

  _on_window_destroyed: (destroy_window) =>
    @windows = [w for w in *@windows when w\to_gobject! != destroy_window]

  _on_activate: (app) =>
    @_load!

  _on_command_line: (app, command_line) =>
    paths = [v for v in *command_line.arguments[2, ] when not v\match('^-')]
    files, hints = parse_path_args paths, command_line.cwd
    if #files > 0
      app\open files, table.concat(hints, ',')
    else
      app\activate!

  _should_abort_quit: =>
    modified = [b for b in *@_buffers when b.modified]
    if #modified > 0
      if not interact.yes_or_no prompt: "Modified buffers exist, close anyway? "
        return true

    false

  _on_mode_registered: (args) =>
    -- check if any buffers with default_mode could use this new mode
    default_mode = mode.by_name 'default'
    for buffer in *@_buffers
      if buffer.file and buffer.mode == default_mode
        buffer_mode = mode.for_file buffer.file
        if mode != default_mode
          buffer.mode = buffer_mode

  _on_mode_unregistered: (args) =>
    -- remove the mode from any buffers that are previously using it
    mode_name = args.name
    default_mode = mode.by_name 'default'
    for buffer in *@_buffers
      if buffer.mode.name == mode_name
        if buffer.file
          buffer.mode = mode.for_file buffer.file
        else
          buffer.mode = default_mode

  _restore_session: (window, restore_buffers) =>
    status, session = pcall @settings.load_system, @settings, 'session'
    unless status
      log.error "Failed to load the session: #{session}"
      return

    if session and session.version == 1
      if restore_buffers
        for entry in *session.buffers
          file = File(entry.file)
          continue unless file.exists
          status, err = pcall ->
            buffer = @new_buffer mode.for_file file
            buffer.file = file
            buffer.last_shown = entry.last_shown
            buffer.properties = entry.properties
            signal.emit 'file-opened', :file, :buffer

          log.error "Failed to load #{file}: #{err}" unless status

        if session.recently_closed
          @_recently_closed = [{file: File(file_info.file), last_shown: file_info.last_shown} for file_info in *session.recently_closed]

      if session.window
        with session.window
          window.maximized = .maximized
          window.fullscreen = .fullscreen

  _set_initial_status: (window) =>
    if log.last_error
      startup_errors = [e for e in *log.entries when e.level == 'error']
      window.status\error "#{log.last_error.message} (#{#startup_errors} startup errors in total)"
    else
      window.status\info 'Howl ready.'

  -- Bootstraps as much of the application as makes sense without a window, for
  -- --run and --run-async. This is the non-GUI half of _load: no theme, no
  -- window, no janitor and no session, but core modules, config and bundles.
  load_headless: =>
    return if @_headless_loaded
    @_headless_loaded = true

    @settings = Settings!
    config.load_config!
    @_load_core!

    if @settings.dir and not @args.no_profile
      append bundle.dirs, @settings.dir\join 'bundles'

    if howl.sys.info.is_flatpak
      append bundle.dirs, File '/app/bundles'

    bundle.load_all!

    unless @args.no_profile
      status, ret = pcall @settings.load_user, @settings
      log.error "Failed to load user settings: #{ret}" unless status

  _load_base: =>
    require 'howl.variables.core_variables'
    require 'howl.modes'

  _load_core: =>
    require 'howl.ui.icons.nerd_fonts'
    require 'howl.completion.in_buffer_completer'
    require 'howl.completion.api_completer'
    require 'howl.interactions.basic'
    require 'howl.interactions.buffer_selection'
    require 'howl.interactions.buffer_search'
    require 'howl.interactions.bundle_selection'
    require 'howl.interactions.clipboard'
    require 'howl.interactions.external_command'
    require 'howl.interactions.explorer'
    require 'howl.interactions.file_selection'
    require 'howl.interactions.location_selection'
    require 'howl.interactions.mode_selection'
    require 'howl.interactions.search'
    require 'howl.interactions.select'
    require 'howl.interactions.signal_selection'
    require 'howl.interactions.text_entry'
    require 'howl.interactions.variable_assignment'
    require 'howl.commands.file_commands'
    require 'howl.commands.app_commands'
    require 'howl.commands.ui_commands'
    require 'howl.commands.edit_commands'
    require 'howl.editing'
    require 'howl.janitor'
    require 'howl.inspect'
    require 'howl.file_search'

  _load_application_icon: =>
    -- GTK4: remove?
    -- dir = @root_dir
    -- while dir
    --   icon = dir\join('share/icons/hicolor/scalable/apps/howl.svg')
    --   if icon.exists
    --     status, err = pcall Gtk.Window.set_default_icon_from_file, icon.path
    --     log.error "Failed to load application icon: #{err}" unless status
    --     return

    --   dir = dir.parent

    -- log.warn "Failed to find application icon"

  _add_recently_closed: (buffer) =>
    @_recently_closed = [file_info for file_info in *@_recently_closed when file_info.file != buffer.file]
    append @_recently_closed, {
      file: buffer.file
      last_shown: buffer.last_shown
    }
    count = #@_recently_closed
    limit = config.recently_closed_limit
    if count > limit
      overage = count - limit
      @_recently_closed = [@_recently_closed[idx] for idx = 1 + overage, limit + overage]

config.define
  name: 'recently_closed_limit'
  description: 'The number of files to remember in the recently closed list'
  default: 1000
  type_of: 'number'
  scope: 'global'

config.define
  name: 'autoclose_single_buffer'
  description: 'When only one, empty buffer is open, automatically close it when another is created'
  default: true
  type_of: 'boolean'
  scope: 'global'

signal.register 'file-opened',
  description: 'Signaled right after a file was opened in a buffer',
  parameters:
    buffer: 'The buffer that the file was opened into'
    file: 'The file that was opened'


signal.register 'buffer-closed',
  description: 'Signaled right after a buffer was closed',
  parameters:
    buffer: 'The buffer that was closed'

signal.register 'app-ready',
  description: 'Signaled right after the application has completed initialization'

return Application
