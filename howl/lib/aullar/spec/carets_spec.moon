-- Copyright 2015 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

carets = require 'aullar.carets'

describe 'carets', ->
  describe 'merged(carets)', ->
    it 'puts the carets in document order', ->
      result = carets.merged {{start: 5, stop: 5}, {start: 2, stop: 2}}
      assert.same {{start: 2, stop: 2}, {start: 5, stop: 5}}, result

    it 'merges equal carets and keeps the primary mark', ->
      result = carets.merged {{start: 4, stop: 4}, {start: 4, stop: 4, primary: true}}
      assert.same {{start: 4, stop: 4, primary: true}}, result

    it 'merges a caret inside a selection and overlapping selections', ->
      result = carets.merged {{start: 1, stop: 6}, {start: 3, stop: 3}, {start: 5, stop: 9}}
      assert.same {{start: 1, stop: 9}}, result

    it 'keeps a caret at the end of a selection apart', ->
      result = carets.merged {{start: 1, stop: 3}, {start: 3, stop: 3}}
      assert.equal 2, #result

  describe 'insertion(carets, text_for)', ->
    it 'puts the text at every caret and gives the carets after it', ->
      edits, after = carets.insertion({{start: 1, stop: 1}, {start: 5, stop: 5, primary: true}}, -> 'x')
      assert.same {{start: 1, stop: 1, text: 'x'}, {start: 5, stop: 5, text: 'x'}}, edits
      assert.same {{start: 2, stop: 2}, {start: 7, stop: 7, primary: true}}, after

    it 'replaces a selection with the text', ->
      edits, after = carets.insertion({{start: 2, stop: 4, primary: true}}, -> 'ab')
      assert.same {{start: 2, stop: 4, text: 'ab'}}, edits
      assert.same {{start: 4, stop: 4, primary: true}}, after

    it 'moves the carets behind a shorter replacement', ->
      _, after = carets.insertion({{start: 1, stop: 4}, {start: 6, stop: 6, primary: true}}, -> 'x')
      assert.same {{start: 2, stop: 2}, {start: 5, stop: 5, primary: true}}, after

  describe 'deletion(carets, backward, char_before, char_after)', ->
    text = 'abcdef'
    char_before = (pos) -> pos > 1 and pos - 1 or nil
    char_after = (pos) -> pos <= #text and pos + 1 or nil

    it 'removes the character before a plain caret when backward', ->
      edits, after = carets.deletion({{start: 4, stop: 4, primary: true}}, true, char_before, char_after)
      assert.same {{start: 3, stop: 4, text: ''}}, edits
      assert.same {{start: 3, stop: 3, primary: true}}, after

    it 'removes the character after a plain caret when forward', ->
      edits, after = carets.deletion({{start: 4, stop: 4, primary: true}}, false, char_before, char_after)
      assert.same {{start: 4, stop: 5, text: ''}}, edits
      assert.same {{start: 4, stop: 4, primary: true}}, after

    it 'removes a selection and leaves the caret at its start', ->
      edits, after = carets.deletion({{start: 2, stop: 5, primary: true}}, true, char_before, char_after)
      assert.same {{start: 2, stop: 5, text: ''}}, edits
      assert.same {{start: 2, stop: 2, primary: true}}, after

    it 'does nothing at the start of the text', ->
      edits, after = carets.deletion({{start: 1, stop: 1, primary: true}}, true, char_before, char_after)
      assert.same {}, edits
      assert.same {{start: 1, stop: 1, primary: true}}, after

    it 'counts the removals of the carets before a caret', ->
      edits, after = carets.deletion({{start: 3, stop: 3}, {start: 5, stop: 5, primary: true}}, true, char_before, char_after)
      assert.same {{start: 2, stop: 3, text: ''}, {start: 4, stop: 5, text: ''}}, edits
      assert.same {{start: 2, stop: 2}, {start: 3, stop: 3, primary: true}}, after

    it 'merges carets that end up at the same place', ->
      _, after = carets.deletion({{start: 2, stop: 2}, {start: 3, stop: 3, primary: true}}, true, char_before, char_after)
      assert.same {{start: 1, stop: 1, primary: true}}, after

  describe 'word_range(text, pos)', ->
    it 'finds the word a caret is in', ->
      assert.equal 1, (carets.word_range 'foo bar', 2)
      assert.equal 4, select(2, carets.word_range 'foo bar', 2)

    it 'finds the word a caret right behind it is on', ->
      start, stop = carets.word_range 'foo bar', 4
      assert.equal 1, start
      assert.equal 4, stop

    it 'finds nothing between two blanks', ->
      assert.is_nil carets.word_range 'a  b', 3

    it 'takes multibyte characters as part of the word', ->
      start, stop = carets.word_range 'über x', 1
      assert.equal 1, start
      assert.equal 6, stop

  describe 'occurrences(text, needle)', ->
    it 'finds every occurrence in order', ->
      assert.same {{start: 1, stop: 4}, {start: 9, stop: 12}}, carets.occurrences 'foo bar foo', 'foo'

    it 'matches a word only as a whole word', ->
      assert.same {{start: 8, stop: 11}}, carets.occurrences 'foobar foo', 'foo'

    it 'matches anything else inside words', ->
      assert.same {{start: 1, stop: 4}, {start: 5, stop: 8}}, carets.occurrences 'a.b a.b', 'a.b'

    it 'finds nothing for an empty needle', ->
      assert.same {}, carets.occurrences 'abc', ''

  describe 'overlaps(a, b)', ->
    it 'is true for selections that share text', ->
      assert.is_true carets.overlaps {start: 1, stop: 4}, {start: 3, stop: 6}

    it 'is false for selections that only touch', ->
      assert.is_false carets.overlaps {start: 1, stop: 2}, {start: 2, stop: 3}

    it 'is true for a caret inside a selection, at its start, but not at its end', ->
      assert.is_true carets.overlaps {start: 3, stop: 3}, {start: 2, stop: 5}
      assert.is_true carets.overlaps {start: 2, stop: 2}, {start: 2, stop: 5}
      assert.is_false carets.overlaps {start: 5, stop: 5}, {start: 2, stop: 5}
