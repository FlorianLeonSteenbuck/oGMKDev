-- The line kinds and inline spans of ogmkdev/baredown.py, as styles of the frame's Howl theme:
-- heading, marker, bullet, ordered, quote, comment, rule, fence, code (the body of a fenced block),
-- bold, italic, code (inline), link.

howl.util.lpeg_lexer ->

  -- an inline span lies on one line: **bold**, //italic//, |code| and [[target|label]]
  span_pair = (start, stop) -> P(start) * scan_until(any(P(stop), eol)) * P(stop)

  bold = capture 'bold', span_pair '**', '**'
  italic = capture 'italic', span_pair '//', '//'
  code = capture 'code', span_pair '|', '|'
  link = capture 'link', P'[[' * scan_until(any(P']]', eol)) * P']]'
  inline = any { bold, italic, code, link }

  -- the text between the spans of a line, in one style
  text = (style) -> capture style, (-inline * (P(1) - eol))^1

  -- a line that starts with a block marker: the marker, then the text with its spans
  block = (marker, marker_style, text_style) ->
    line_start * capture(marker_style, marker) * (inline + text(text_style))^0

  -- a fenced block: the opening line with its language, the code up to the closing line, the closing line
  fenced = sequence {
    line_start,
    capture('fence', P'~~~' * scan_until eol),
    capture('code', scan_until(any(line_start * P'~~~', -P(1)))),
    (line_start * capture('fence', P'~~~' * scan_until eol))^-1,
  }

  rule = line_start * capture('rule', P'----' * S'-'^0 * blank^0) * #(eol + -P(1))
  comment = line_start * capture('comment', P'%%' * (P(1) - eol)^0)
  heading = block(P'='^1 * #blank, 'marker', 'heading')
  bullet = block(P'-' * #blank, 'marker', 'bullet')
  ordered = block(P'+' * #blank, 'marker', 'ordered')
  quote = block(P'>', 'marker', 'quote')

  any {
    fenced,
    rule,
    comment,
    heading,
    bullet,
    ordered,
    quote,
    inline,
  }
