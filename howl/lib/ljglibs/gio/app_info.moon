-- Copyright 2024 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

require 'ljglibs.cdefs.gio'

C = require('ffi').C

-- opens a URI with the application the desktop picks for it (a web address opens the browser);
-- true when an application was started
launch_uri = (uri) ->
  C.g_app_info_launch_default_for_uri(uri, nil, nil) != 0

{:launch_uri}
