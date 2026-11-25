{:Buffer} = howl
{:Editor} = howl.ui

describe 'Editor with several carets', ->
  buffer = Buffer howl.mode.by_name 'default'
  editor = Editor buffer
  test_window editor\to_gobject!

  before_each ->
    editor.view\clear_extra_carets!
    editor.buffer.text = 'abcd\nabcd'
    editor.cursor.pos = 1

  describe 'typing', ->
    it 'puts the text at every caret', ->
      editor.view\set_extra_carets {{pos: 6, anchor: 6}}
      editor\insert 'x'
      assert.equal 'xabcd\nxabcd', editor.buffer.text
      assert.equal 2, editor.cursor.pos
      assert.equal 8, editor.view\extra_carets![1].pos

    it 'is one undo step', ->
      editor.view\set_extra_carets {{pos: 6, anchor: 6}}
      editor\insert 'x'
      editor\undo!
      assert.equal 'abcd\nabcd', editor.buffer.text

    it 'does not complete while carets are active', ->
      editor.view\set_extra_carets {{pos: 6, anchor: 6}}
      editor\_on_key_press editor.view, key_name: 'a', character: 'a'
      assert.equal 1, #editor.view\extra_carets!

  describe 'return', ->
    it 'breaks the line at every caret and keeps the indentation of each line', ->
      editor.buffer.text = 'abcd\n  abcd'
      editor.cursor.pos = 3
      editor.view\set_extra_carets {{pos: 10, anchor: 10}}
      editor\_on_key_press editor.view, key_name: 'return'
      assert.equal 'ab\ncd\n  ab\n  cd', editor.buffer.text
      assert.equal 4, editor.cursor.pos
      assert.equal 14, editor.view\extra_carets![1].pos

  describe 'backspace and delete', ->
    it 'removes the character before each caret', ->
      editor.buffer.text = 'abc\nabc'
      editor.cursor.pos = 4
      editor.view\set_extra_carets {{pos: 8, anchor: 8}}
      editor\_on_key_press editor.view, key_name: 'backspace'
      assert.equal 'ab\nab', editor.buffer.text
      assert.equal 3, editor.cursor.pos
      assert.equal 6, editor.view\extra_carets![1].pos

    it 'removes the character after each caret with delete', ->
      editor.buffer.text = 'abc\nabc'
      editor.cursor.pos = 1
      editor.view\set_extra_carets {{pos: 5, anchor: 5}}
      editor\_on_key_press editor.view, key_name: 'delete'
      assert.equal 'bc\nbc', editor.buffer.text
      assert.equal 1, editor.cursor.pos
      assert.equal 4, editor.view\extra_carets![1].pos

  describe 'movement', ->
    it 'moves every caret with the left and right keys', ->
      editor.cursor.pos = 3
      editor.view\set_extra_carets {{pos: 8, anchor: 8}}
      editor\_on_key_press editor.view, key_name: 'left'
      assert.equal 2, editor.cursor.pos
      assert.equal 7, editor.view\extra_carets![1].pos
      editor\_on_key_press editor.view, key_name: 'right'
      assert.equal 3, editor.cursor.pos
      assert.equal 8, editor.view\extra_carets![1].pos

    it 'extends the selections with shift', ->
      editor.cursor.pos = 3
      editor.view\set_extra_carets {{pos: 8, anchor: 8}}
      editor\_on_key_press editor.view, key_name: 'left'
      editor\_on_key_press editor.view, key_name: 'left', shift: true
      assert.equal 1, editor.cursor.pos
      assert.equal 2, editor.selection.anchor
      extras = editor.view\extra_carets!
      assert.equal 6, extras[1].pos
      assert.equal 7, extras[1].anchor

    it 'collapses a selection to its start with a plain left', ->
      editor.cursor.pos = 4
      editor.view.selection\set 2, 4
      editor.view\set_extra_carets {{pos: 8, anchor: 8}}
      editor\_on_key_press editor.view, key_name: 'left'
      assert.equal 2, editor.cursor.pos
      assert.is_true editor.view.selection.is_empty
      assert.equal 7, editor.view\extra_carets![1].pos

    it 'adds a caret on the line below at the same column', ->
      editor.cursor.pos = 3
      editor\add_caret_below!
      extras = editor.view\extra_carets!
      assert.equal 1, #extras
      assert.equal 8, extras[1].pos

  describe 'ending the carets', ->
    it 'escape leaves the cursor alone', ->
      editor.cursor.pos = 2
      editor.view\set_extra_carets {{pos: 6, anchor: 6}}
      editor\_on_key_press editor.view, key_name: 'escape'
      assert.equal 0, #editor.view\extra_carets!
      assert.equal 2, editor.cursor.pos

    it 'another command ends the carets first', ->
      editor.cursor.pos = 2
      editor.view\set_extra_carets {{pos: 6, anchor: 6}}
      editor\_on_key_press editor.view, key_name: 'f5'
      assert.equal 0, #editor.view\extra_carets!

  describe 'Alt+click', ->
    it 'toggles a caret at a position', ->
      editor.cursor.pos = 2
      editor\_toggle_extra_caret 6
      assert.equal 1, #editor.view\extra_carets!
      editor\_toggle_extra_caret 6
      assert.equal 0, #editor.view\extra_carets!

    it 'does not add a caret where the cursor is', ->
      editor.cursor.pos = 2
      editor\_toggle_extra_caret 2
      assert.equal 0, #editor.view\extra_carets!

  describe 'occurrences', ->
    before_each ->
      editor.buffer.text = 'foo bar foo baz foo'

    it 'selects the word at the cursor first', ->
      editor.cursor.pos = 2
      editor\select_next_occurrence!
      assert.equal 1, editor.selection.anchor
      assert.equal 4, editor.cursor.pos
      assert.equal 0, #editor.view\extra_carets!

    it 'adds the next occurrence and keeps the earlier selections', ->
      editor.cursor.pos = 2
      editor\select_next_occurrence!
      editor\select_next_occurrence!
      assert.equal 9, editor.selection.anchor
      assert.equal 12, editor.cursor.pos
      extras = editor.view\extra_carets!
      assert.equal 1, #extras
      assert.equal 1, extras[1].anchor
      assert.equal 4, extras[1].pos

    it 'wraps around and stops when every occurrence is selected', ->
      editor.cursor.pos = 2
      editor\select_next_occurrence!
      editor\select_next_occurrence!
      editor\select_next_occurrence!
      assert.equal 17, editor.selection.anchor
      assert.equal 2, #editor.view\extra_carets!
      editor\select_next_occurrence!
      assert.equal 17, editor.selection.anchor
      assert.equal 2, #editor.view\extra_carets!

    it 'selects all occurrences of the word at the cursor', ->
      editor.cursor.pos = 10
      editor\select_all_occurrences!
      assert.equal 9, editor.selection.anchor
      assert.equal 12, editor.cursor.pos
      assert.equal 2, #editor.view\extra_carets!

    it 'skips occurrences in folded away lines', ->
      editor.buffer.text = 'foo\n  foo\nfoo'
      editor.cursor.pos = 1
      editor\toggle_fold 1
      editor\select_all_occurrences!
      extras = editor.view\extra_carets!
      assert.equal 1, #extras
      assert.equal 11, extras[1].anchor
