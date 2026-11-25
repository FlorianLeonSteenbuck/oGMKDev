-- Copyright 2026 oGMKDev
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

-- oGMKDev additions to Howl: TODOs in comments with priorities and an overview, and custom
-- text highlighting. Both are configured with the ogmkdev_* settings (EditorConfig or Howl config).

info = {
  author: 'oGMKDev',
  description: 'TODOs in comments with priorities and an overview, and custom text highlighting',
  license: 'MIT',
}

bundle_load 'todo'
bundle_load 'highlights'

return :info, unload: ->
