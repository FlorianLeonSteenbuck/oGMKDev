-- Copyright 2012-2015 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

{:app, :interact} = howl
{:DirectoryExplorer} = howl.explorers
{:File} = howl.io

interact.register
  name: 'select_file'
  description: ''
  handler: (opts={}) ->
    path = opts.path or File.home_dir.path
    explorer_path, text = DirectoryExplorer.for_path path, files_only: true, allow_new: opts.allow_new, show_subtree: opts.show_subtree
    interact.explore
      prompt: opts.prompt
      path: explorer_path
      text: text
      help: opts.help
      transform_result: (item) -> item.file

interact.register
  name: 'select_directory'
  description: ''
  handler: (opts={})->
    path = opts.path or File.home_dir.path
    interact.explore
      title: opts.title
      prompt: opts.prompt
      help: opts.help
      path: howl.explorers.DirectoryExplorer.for_path path, directories_only: true
      transform_result: (item) -> item.file



