import Buffer from howl
import Editor from howl.ui
import File from howl.io
import templates from howl.editing

describe 'templates', ->
  describe 'parse', ->
    it 'reads one template per line: the trigger, a tab, and the body with its escapes', ->
      expected = {
        {trigger: 'fn', body: 'fn(${args:x}) => $0;'},
        {trigger: 'if', body: 'if (${cond:true}) {\n    $0\n}'},
      }
      assert.same expected, templates.parse('fn\tfn(${args:x}) => $0;\nif\tif (${cond:true}) {\\n    $0\\n}')

    it 'reads an escaped backslash as one backslash', ->
      assert.same {{trigger: 'x', body: 'a\\b'}}, templates.parse('x\ta\\\\b')

  describe 'expand', ->
    it 'replaces a variable by its default and puts the cursor at $0', ->
      text, cursor = templates.expand('fn(${args:x}) => $0;')
      assert.equal 'fn(x) => ;', text
      assert.equal 9, cursor

    it 'keeps a variable without a default, and counts the cursor in characters', ->
      text, cursor = templates.expand('é ${name} $0')
      assert.equal 'é ${name} ', text
      assert.equal 10, cursor

    it 'reads $$ as a dollar in front of a variable, and other dollars as text', ->
      text, cursor = templates.expand('$${variable:text} = $5 ${open')
      assert.equal '$text = $5 ${open', text
      assert.equal #text, cursor

  describe 'expand_at_cursor', ->
    local buffer, editor, list

    before_each ->
      buffer = Buffer!
      editor = Editor buffer
      list = templates.parse('if\tif (${cond:true}) {\\n    $0\\n}\nmy-tag\t<${tag:div}>$0</${tag:div}>')

    it 'replaces the trigger before the cursor by its expansion, and puts the cursor at $0', ->
      buffer.text = 'if'
      editor.cursor.pos = 3
      assert.is_true templates.expand_at_cursor(editor, list)
      assert.equal 'if (true) {\n    \n}', buffer.text
      assert.equal 17, editor.cursor.pos

    it 'takes a trigger with a hyphen', ->
      buffer.text = 'my-tag'
      editor.cursor.pos = 7
      assert.is_true templates.expand_at_cursor(editor, list)
      assert.equal '<div></div>', buffer.text

    it 'takes the trigger after other text on the line', ->
      buffer.text = 'x = if'
      editor.cursor.pos = 7
      assert.is_true templates.expand_at_cursor(editor, list)
      assert.equal 'x = if (true) {\n    \n}', buffer.text

    it 'does nothing when the word before the cursor has no template', ->
      buffer.text = 'foo'
      editor.cursor.pos = 4
      assert.is_false templates.expand_at_cursor(editor, list)
      assert.equal 'foo', buffer.text

    it 'does nothing inside a word', ->
      buffer.text = 'ifx'
      editor.cursor.pos = 3
      assert.is_false templates.expand_at_cursor(editor, list)
      assert.equal 'ifx', buffer.text

    it 'does nothing when a letter outside ASCII is in front of the trigger', ->
      buffer.text = 'éif'
      editor.cursor.pos = 4
      assert.is_false templates.expand_at_cursor(editor, list)
      assert.equal 'éif', buffer.text

    it 'does nothing while text is selected', ->
      buffer.text = 'if'
      editor.selection\set 1, 3
      assert.is_false templates.expand_at_cursor(editor, list)

    it 'undoes the expansion in one step', ->
      buffer.text = 'if'
      editor.cursor.pos = 3
      templates.expand_at_cursor(editor, list)
      buffer\undo!
      assert.equal 'if', buffer.text

  describe 'for_buffer', ->
    it 'gives a buffer the templates that were sent for its file', ->
      path = '/nonexistent/ogmkdev/templates-spec.php'
      templates.set_for_path(path, 'fn\tfn(${x:a}) => $0;')
      buffer = Buffer!
      buffer.file = File(path)
      assert.same {{trigger: 'fn', body: 'fn(${x:a}) => $0;'}}, templates.for_buffer(buffer)

    it 'has none for a buffer without a file', ->
      assert.is_nil templates.for_buffer(Buffer!)
