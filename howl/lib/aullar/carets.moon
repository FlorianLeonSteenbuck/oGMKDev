-- Copyright 2015 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

-- Several carets at once. A caret is a range of byte positions: a plain caret has start == stop,
-- a selection has start < stop. Carets that overlap merge into one, and the primary caret (the
-- cursor of the view) keeps its mark when it merges. The functions here compute the edits and the
-- carets after them; the view applies them.

{:max, :min} = math

-- the carets in document order, overlapping or equal ones merged into one
merged = (carets) ->
  sorted = [{start: c.start, stop: c.stop, primary: c.primary} for c in *carets]
  table.sort sorted, (a, b) -> a.start < b.start or (a.start == b.start and a.stop < b.stop)

  result = {}
  for c in *sorted
    last = result[#result]
    if last and (c.start < last.stop or c.start == last.start)
      last.stop = max last.stop, c.stop
      last.primary = last.primary or c.primary
    else
      result[#result + 1] = c
  result

-- whether two carets touch the same text; a plain caret touches a selection it sits in
overlaps = (a, b) ->
  (a.start < b.stop and b.start < a.stop) or (a.start == a.stop and b.start <= a.start and a.start < b.stop) or (b.start == b.stop and a.start <= b.start and b.start < a.stop)

-- the edits that put the text of each caret in place of its range, and the carets after them;
-- text_for gives the text for a caret
insertion = (carets, text_for) ->
  edits, after, shift = {}, {}, 0
  for c in *merged(carets)
    text = text_for c
    edits[#edits + 1] = {start: c.start, stop: c.stop, :text}
    pos = c.start + shift + #text
    after[#after + 1] = {start: pos, stop: pos, primary: c.primary}
    shift += #text - (c.stop - c.start)
  edits, merged(after)

-- the edits that remove the text of each caret, and the carets after them: a selection loses its
-- text, a plain caret the character before it when backward, the one after it otherwise
deletion = (carets, backward, char_before, char_after) ->
  edits, after, shift = {}, {}, 0
  for c in *merged(carets)
    local first, stop
    if c.stop > c.start
      first, stop = c.start, c.stop
    elseif backward
      first, stop = (char_before(c.start) or c.start), c.start
    else
      first, stop = c.start, (char_after(c.start) or c.start)
    edits[#edits + 1] = {start: first, stop: stop, text: ''} if stop > first
    after[#after + 1] = {start: first - shift, stop: first - shift, primary: c.primary}
    shift += stop - first
  edits, merged(after)

-- the bytes of a word: letters, digits, '_' and every byte of a multibyte character
word_byte = (byte) ->
  byte != nil and (byte == 95 or (byte >= 48 and byte <= 57) or (byte >= 65 and byte <= 90) or (byte >= 97 and byte <= 122) or byte >= 128)

-- the word at pos as start and stop (not included), or nil; a caret right behind a word is on it
word_range = (text, pos) ->
  is_word = (p) -> word_byte text\byte(p)
  unless is_word pos
    return nil unless pos > 1 and is_word(pos - 1)
    pos -= 1

  first, stop = pos, pos
  while first > 1 and is_word(first - 1)
    first -= 1
  while is_word(stop)
    stop += 1
  first, stop

-- the occurrences of needle in text, in order and not overlapping; a needle that is a word only
-- matches whole words
occurrences = (text, needle) ->
  found = {}
  return found if needle == ''

  whole = needle\match('^[%w_\128-\255]+$') != nil
  init = 1
  while true
    first, last = text\find needle, init, true
    break unless first
    stop = last + 1
    if not whole or ((first == 1 or not word_byte(text\byte(first - 1))) and not word_byte(text\byte(stop)))
      found[#found + 1] = {start: first, :stop}
    init = stop
  found

{:merged, :insertion, :deletion, :overlaps, :word_range, :occurrences}
