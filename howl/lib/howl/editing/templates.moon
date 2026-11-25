-- Code templates. Ctrl+Space expands the trigger before the cursor to the template of the file, when it has
-- one; otherwise it starts completion, as before.
--
-- The frame sends the templates of each file through HOWL_EMBED_TEMPLATES (application.moon): the built-in
-- templates of its language and dialect, then the EditorConfig ones (ogmkdev/templates.py). A row is
-- "trigger<TAB>body"; in the body a backslash, a line break and a tab are written as \\, \n and \t.
--
-- In a body, ${name:default} becomes its default, ${name} stays as it is, $0 is where the cursor goes after
-- the expansion, and everything else is text.

import File from howl.io

by_path = {}

ESCAPES = {n: '\n', t: '\t'}

decode = (c) -> ESCAPES[c] or (c == '\\' and '\\') or '\\' .. c

unescape = (text) -> (text\gsub('\\(.)', decode))

-- the templates of the rows, as a list of {trigger: ..., body: ...}
parse = (rows) ->
  list = {}
  for line in rows\gmatch '[^\n]+'
    trigger, body = line\match '^([^\t]+)\t(.*)$'
    list[#list + 1] = {:trigger, body: unescape(body)} if trigger
  list

-- the text of a body with its defaults in place, and the offset of the cursor in characters
expand = (body) ->
  pieces = {}
  length = 0
  cursor = nil
  add = (text) ->
    pieces[#pieces + 1] = text
    length += text.ulen

  pos = 1
  while true
    start = body\find('$', pos, true)
    unless start
      add(body\sub(pos))
      break
    add(body\sub(pos, start - 1))
    pos = start + 1
    if body\sub(pos, pos) == '0'
      cursor = length
      pos += 1
    else
      name = body\sub(pos, pos) == '{' and body\match('^[A-Za-z_][A-Za-z0-9_]*', pos + 1)
      if name
        after = pos + 1 + #name
        following = body\sub(after, after)
        close = following == ':' and body\find('}', after + 1, true)
        if following == '}'
          add(body\sub(start, after))
          pos = after + 1
        elseif close
          add(body\sub(after + 1, close - 1))
          pos = close + 1
        else
          add('$')
      else
        add('$')
  return table.concat(pieces), cursor or length

-- the trigger that ends at the cursor: the letters, digits, '-' and '_' before it. It is no trigger when
-- the run goes on with a character outside ASCII (bytes of 128 or more) in front of it or after the cursor.
trigger_before = (editor) ->
  context = editor.current_context
  before = context.prefix
  run = before\match '[%w_%-]+$'
  return nil unless run
  start = #before - #run
  return nil if start > 0 and before\byte(start) >= 128
  after = context.next_char or ''
  return nil if after != '' and (after\byte(1) >= 128 or after\match('^[%w_%-]'))
  run

find = (list, trigger) ->
  for template in *list
    return template if template.trigger == trigger
  nil

-- expands the trigger before the cursor when one of the templates in list has it; true when it did
expand_at_cursor = (editor, list) ->
  buffer = editor.buffer
  return false if buffer.read_only or not editor.selection.empty
  trigger = trigger_before(editor)
  template = trigger and find(list, trigger)
  return false unless template
  text, cursor = expand template.body
  stop = editor.cursor.pos - 1
  start = stop - #trigger + 1
  buffer\as_one_undo ->
    buffer\delete(start, stop)
    buffer\insert(text, start)
  editor.cursor.pos = start + cursor
  true

-- the templates sent for the file that a buffer shows, or nil
for_buffer = (buffer) ->
  file = buffer.file
  file and by_path[file.path]

-- the templates of a file (src/embed.c howl_templates)
set_for_path = (path, rows) ->
  by_path[File(path).path] = parse(rows)

howl.command.register
  name: 'editor-expand-or-complete'
  description: 'Expands the code template of the word before the cursor, or starts completion'
  handler: ->
    editor = @editor
    return unless editor
    list = for_buffer editor.buffer
    return if list and expand_at_cursor(editor, list)
    editor\complete!

return {
  :parse
  :expand
  :expand_at_cursor
  :for_buffer
  :set_for_path
}
