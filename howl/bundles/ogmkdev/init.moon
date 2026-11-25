-- Copyright 2026 oGMKDev
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

-- oGMKDev additions to Howl: custom text highlighting (ogmkdev_highlights). TODOs are found by the
-- GTK frame (ogmkdev/todos.py), not by Howl.

info = {
  author: 'oGMKDev',
  description: 'Custom text highlighting',
  license: 'MIT',
}

bundle_load 'highlights'

return :info, unload: ->
