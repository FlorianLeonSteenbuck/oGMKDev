-- Copyright 2026 oGMKDev
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

{:app, :bindings, :command, :config, :interact, :signal, :timer} = howl
{:style, :highlight} = howl.ui

config.define {
  name: 'ogmkdev_todo_keywords'
  description: 'Words that mark a TODO inside comments, each with a priority (1 is the most urgent), e.g. FIXME:1,TODO:3'
  type_of: 'string'
  default: 'FIXME:1,XXX:2,HACK:2,TODO:3,NOTE:5'
}

config.define {
  name: 'ogmkdev_todo_highlight'
  description: 'Highlight TODO words in comments in the editor (on or off)'
  type_of: 'string'
  default: 'on'
}

-- one colour per priority; priorities below the last one share its colour
priority_colors = { '#ff5555', '#ffb86c', '#f1fa8c', '#8be9fd' }

for index, color in ipairs priority_colors
  highlight.define "ogmkdev-todo-#{index}", {
    type: highlight.RECTANGLE
    background: color
    background_alpha: 0.3
  }

flair_for = (priority) -> "ogmkdev-todo-#{math.min priority, #priority_colors}"

parse_keywords = (text) ->
  keywords = {}
  for entry in text\gmatch '[^,%s]+'
    word, priority = entry\match '^(%w+):(%d+)$'
    keywords[#keywords + 1] = { :word, priority: tonumber priority } if word
  keywords

is_comment = (buffer, pos) ->
  name = style.at_pos buffer, pos
  name != nil and name\find('comment', 1, true) != nil

-- line number and text of the line that contains byte position `s`
line_at = (text, s) ->
  line_start = (text\sub(1, s - 1)\match('.*\n()') or 1)
  line_end = text\find('\n', s, true) or (#text + 1)
  newlines = select 2, text\sub(1, s - 1)\gsub('\n', '')
  newlines + 1, text\sub(line_start, line_end - 1)

todos_in = (buffer) ->
  text = buffer.text
  found = {}
  for keyword in *parse_keywords config.ogmkdev_todo_keywords
    init = 1
    while true
      s, e = text\find "%f[%w]#{keyword.word}%f[%W]", init
      break unless s
      init = e + 1
      start_offset = buffer\char_offset s
      if is_comment buffer, start_offset
        line, line_text = line_at text, s
        found[#found + 1] = {
          :buffer
          :keyword
          :line
          line_text: (line_text\gsub('^%s+', ''))
          start_offset: start_offset
          end_offset: buffer\char_offset(e + 1)
        }
  found

-- finds the TODOs of a buffer and marks them; returns them
refresh = (buffer) ->
  return {} unless buffer
  buffer.markers\remove name: "ogmkdev-todo"
  todos = todos_in buffer
  if #todos > 0 and config.ogmkdev_todo_highlight != 'off'
    buffer.markers\add [{
      name: 'ogmkdev-todo'
      flair: flair_for t.keyword.priority
      start_offset: t.start_offset
      end_offset: t.end_offset
    } for t in *todos]
  todos

command.register
  name: 'todo-list'
  description: 'List the TODOs in comments of all open buffers, most urgent first'
  handler: ->
    todos = {}
    for buffer in *app.buffers
      for todo in *refresh buffer
        todos[#todos + 1] = todo

    if #todos == 0
      log.info 'No TODOs in comments of the open buffers'
      return

    table.sort todos, (a, b) ->
      if a.keyword.priority != b.keyword.priority
        return a.keyword.priority < b.keyword.priority
      if a.buffer.title != b.buffer.title
        return a.buffer.title < b.buffer.title
      a.line < b.line

    items = for t in *todos
      {
        "P#{t.keyword.priority}  #{t.keyword.word}"
        "#{t.buffer.title}:#{t.line}"
        t.line_text
        buffer: t.buffer
        line_nr: t.line
        pos: t.start_offset
      }

    loc = interact.select_location {
      title: "#{#todos} TODO(s) in comments"
      items: items
      columns: { {style: 'keyword'}, {style: 'string'}, {style: 'comment'} }
    }
    app\open loc if loc

bindings.push ctrl_alt_t: 'todo-list'

signal.connect 'file-opened', (args) -> timer.after 0.3, -> refresh args.buffer

return :todos_in, :refresh, :parse_keywords
