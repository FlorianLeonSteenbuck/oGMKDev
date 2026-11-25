-- The BareDown lexer: the styles of the line kinds and the inline spans of ogmkdev/baredown.py

import mode from howl

-- the lexer of the BareDown mode (its bundle loads when the mode is first asked for)
bundles = require 'howl.bundle'
bundles.load_by_name 'baredown' unless mode.by_name 'baredown'
lexer = mode.by_name('baredown').lexer

-- the styled parts of a text: a list of { style, text }, in order
spans = (text) ->
  parts = lexer text
  result = {}
  for i = 1, #parts, 3
    result[#result + 1] = { parts[i + 1], text\sub parts[i], parts[i + 2] - 1 }
  result

-- true when the text has a part in that style with exactly that text
has = (text, style, part) ->
  for span in *spans text
    return true if span[1] == style and span[2] == part
  false

describe 'baredown lexer', ->
  it 'styles a heading and its marker', ->
    assert.is_true has '= Title', 'marker', '='
    assert.is_true has '= Title', 'heading', ' Title'

  it 'styles the inline spans of a heading', ->
    assert.is_true has '== a **b**', 'bold', '**b**'

  it 'styles bullet, ordered and quote items', ->
    assert.is_true has '- item', 'marker', '-'
    assert.is_true has '- item', 'bullet', ' item'
    assert.is_true has '+ one', 'ordered', ' one'
    assert.is_true has '> quoted', 'quote', ' quoted'

  it 'styles a comment line as a whole', ->
    assert.is_true has '%% note', 'comment', '%% note'

  it 'styles a rule of four or more dashes', ->
    assert.is_true has '----', 'rule', '----'
    assert.is_false has '- item', 'rule', '- item'

  it 'styles bold, italic, inline code and links', ->
    assert.is_true has 'a **bold** b', 'bold', '**bold**'
    assert.is_true has 'a //it// b', 'italic', '//it//'
    assert.is_true has 'a |code| b', 'code', '|code|'
    assert.is_true has 'see [[Target|label]].', 'link', '[[Target|label]]'

  it 'styles a fenced block: the fences and the code between them', ->
    text = "~~~ python\nx = 1\n~~~"
    assert.is_true has text, 'fence', '~~~ python'
    assert.is_true has text, 'code', "\nx = 1\n"
    assert.is_true has text, 'fence', '~~~'

  it 'leaves plain paragraph text unstyled', ->
    for span in *spans 'plain text'
      assert.equals 'whitespace', span[1]  -- the blanks between the words only

  it 'does not take a span across a line end', ->
    assert.is_false has "**a\nb**", 'bold', "**a\nb**"
