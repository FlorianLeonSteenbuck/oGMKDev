-- BareDown: the markup of ogmkdev (ogmkdev/baredown.py), highlighted by the frame's Howl editors
-- License: GPL-2.0-or-later (see LICENSE at the top-level directory of the distribution)

mode_reg =
  name: 'baredown'
  extensions: {'bd', 'baredown'}
  create: -> bundle_load('baredown_mode')

howl.mode.register mode_reg

unload = -> howl.mode.unregister 'baredown'

return {
  info:
    author: 'The oGMKDev developers',
    description: 'BareDown markup support',
    license: 'GPL-2.0-or-later',
  :unload
}
