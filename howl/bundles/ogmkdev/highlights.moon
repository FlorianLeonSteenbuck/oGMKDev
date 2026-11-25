-- Copyright 2026 oGMKDev
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

{:config, :signal, :timer} = howl
{:highlight} = howl.ui

config.define {
  name: 'ogmkdev_highlights'
  description: 'Text to highlight in every buffer as text=#colour pairs separated by ;, e.g. console.log=#ffb86c;DEPRECATED=#ff5555'
  type_of: 'string'
  default: ''
}

MAX_RULES = 50

parse_rules = (text) ->
  rules = {}
  for entry in text\gmatch '[^;]+'
    word, color = entry\match '^%s*(.-)%s*=%s*(#%x+)%s*$'
    rules[#rules + 1] = { :word, :color } if word and word != ''
  rules

refresh = (buffer) ->
  return unless buffer
  for index = 1, MAX_RULES
    highlight.remove_all "ogmkdev-highlight-#{index}", buffer

  text = buffer.text
  for index, rule in ipairs parse_rules config.ogmkdev_highlights
    name = "ogmkdev-highlight-#{index}"
    highlight.define name, {
      type: highlight.RECTANGLE
      background: rule.color
      background_alpha: 0.35
    }
    ranges = {}
    init = 1
    while true
      s, e = text\find rule.word, init, true
      break unless s
      start = buffer\char_offset s
      ranges[#ranges + 1] = { start, buffer\char_offset(e + 1) - start }
      init = e + 1
    highlight.apply name, buffer, ranges if #ranges > 0

signal.connect 'file-opened', (args) -> timer.after 0.3, -> refresh args.buffer

return :parse_rules, :refresh
