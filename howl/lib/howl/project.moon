-- Copyright 2012-2015 The Howl Developers
-- License: MIT (see LICENSE.md at the top-level directory of the distribution)

-- ogmkdev: Howl's project management is removed. There are no open projects, no project
-- roots, no environment files and no project commands. The "project" of a file is simply
-- the folder that contains it (the home folder for files without one), so modules that
-- ask for a project keep working.

{:sys} = howl
{:File} = howl.io

project_for = (root) ->
  {
    :root
    process_env: -> {}
    find_environment: -> {}
    find_executable: (name) -> sys.find_executable name
    files: -> {}
    paths: -> {}
  }

Project =
  roots: {}
  open: {}
  for_file: (file) ->
    return nil unless file
    project_for(file.parent or File.home_dir)
  get_for_file: (file) -> Project.for_file file
  new: (root) -> project_for root
  add_root: (root) ->
  remove_root: (root) ->
  register_environment_provider: (provider) ->
  unregister_environment_provider: (name) ->

signal = howl.signal
signal.register 'project-environment-changed',
  description: 'Kept for compatibility; no longer emitted since projects are removed'
  parameters:
    project: 'The project'

return Project
