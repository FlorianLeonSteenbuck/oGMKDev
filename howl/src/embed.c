/* Howl as a library. The editor's content is a GTK widget that the calling program puts into
   its own layout (for example a GtkBox of a GTK 4 Python application). The window Howl creates
   for the content is hidden; the content itself is moved into the container.
   Build: make libhowl.so (see packaging/build-howl.sh). */
#include <stdio.h>
#include <gtk/gtk.h>
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>

int luaopen_lpeg(lua_State *L);

static lua_State *embedded = NULL;

/* Error handler: the message with a Lua traceback, so a failing Howl call shows where it failed. */
static int traceback_handler(lua_State *L)
{
  const char *message = lua_tostring(L, 1);
  luaL_traceback(L, L, message ? message : "(error)", 1);
  return 1;
}

/* Starts Howl's Lua side in the process and puts the editor into `container`; later calls add
   further editors to the same Howl. Returns 0 on success. The Lua state lives as long as the process. */
int howl_embed(GtkBox *container, const char *app_root, const char *file)
{
  if (embedded != NULL) {
    /* a further editor in the same process: Howl adds a window and moves its content */
    int handler = lua_gettop(embedded) + 1;
    lua_pushcfunction(embedded, traceback_handler);
    lua_getglobal(embedded, "HOWL_EMBED_ADD");
    if (!lua_isfunction(embedded, -1)) {
      lua_settop(embedded, handler - 1);
      return 1;
    }
    lua_pushlightuserdata(embedded, container);
    lua_pushstring(embedded, file ? file : "");
    if (lua_pcall(embedded, 2, 0, handler)) {
      g_critical("Failed to add an editor: %s", lua_tostring(embedded, -1));
      lua_settop(embedded, handler - 1);
      return 1;
    }
    lua_settop(embedded, handler - 1);
    return 0;
  }

  lua_State *L = luaL_newstate();
  luaL_openlibs(L);
  luaopen_lpeg(L);
  lua_pop(L, 1);

  lua_pushlightuserdata(L, container);
  lua_setglobal(L, "HOWL_EMBED_CONTAINER");
  lua_pushstring(L, file ? file : "");
  lua_setglobal(L, "HOWL_EMBED_FILE");

  gchar *script = g_build_filename(app_root, "lib", "howl", "init.lua", NULL);
  int status = luaL_loadfile(L, script);
  g_free(script);
  if (status) {
    g_critical("Couldn't load howl: %s", lua_tostring(L, -1));
    return 1;
  }

  lua_pushstring(L, app_root);
  lua_newtable(L);
  lua_pushnumber(L, 1);
  lua_pushstring(L, "--embed");
  lua_settable(L, -3);
  status = lua_pcall(L, 2, 0, 0);
  if (status) {
    g_critical("Failed to embed howl: %s", lua_tostring(L, -1));
    return 1;
  }

  embedded = L;
  return 0;
}

#include <glib-object.h>
/* Used by Howl's Lua side (ljglibs), same as in main.c. */
GType howl_gobject_type_from_instance(gpointer instance) {
  return G_TYPE_FROM_INSTANCE(instance);
}

/* Opens a file (line and column are 1-based, 0 for none) in the editor that has the focus. */
int howl_open(const char *file, int line, int column)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_OPEN");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  lua_pushinteger(embedded, line);
  lua_pushinteger(embedded, column);
  if (lua_pcall(embedded, 3, 0, 0)) {
    g_critical("Failed to open %s: %s", file, lua_tostring(embedded, -1));
    return 1;
  }
  return 0;
}

/* Runs a Howl command (for example "save", "editor-undo") in the editor that has the focus. */
int howl_command(const char *name)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_COMMAND");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, name);
  if (lua_pcall(embedded, 1, 0, 0)) {
    g_critical("Howl command %s failed: %s", name, lua_tostring(embedded, -1));
    return 1;
  }
  return 0;
}

/* Copies the status line of the focused Howl editor (see HOWL_EMBED_STATUS in application.moon). */
int howl_status(char *out, int size)
{
  out[0] = 0;
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_STATUS");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  if (lua_pcall(embedded, 0, 1, 0)) {
    g_critical("Howl status failed: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  const char *text = lua_tostring(embedded, -1);
  if (text)
    snprintf(out, size, "%s", text);
  lua_pop(embedded, 1);
  return 0;
}

/* Registers the Howl theme file `file` under `name` and selects it (see HOWL_EMBED_THEME). */
int howl_theme(const char *name, const char *file)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_THEME");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, name);
  lua_pushstring(embedded, file);
  if (lua_pcall(embedded, 2, 0, 0)) {
    g_critical("Howl theme failed: %s", lua_tostring(embedded, -1));
    return 1;
  }
  return 0;
}

/* Sets the error hints of a file in its Howl buffer: one line per hint,
   "line<TAB>start<TAB>end<TAB>type<TAB>message" (columns 1-based, end exclusive, type error,
   warning or hint). See HOWL_EMBED_INSPECT in application.moon. */
int howl_inspect(const char *file, const char *rows)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_INSPECT");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  lua_pushstring(embedded, rows);
  if (lua_pcall(embedded, 2, 0, 0)) {
    g_critical("Howl hints for %s failed: %s", file, lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  return 0;
}

/* Copies the breakpoints of the Howl editors, one "path<TAB>line" per line (see HOWL_EMBED_BREAKPOINTS in
   application.moon). */
int howl_breakpoints(char *out, int size)
{
  out[0] = 0;
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_BREAKPOINTS");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  if (lua_pcall(embedded, 0, 1, 0)) {
    g_critical("Howl breakpoints failed: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  const char *rows = lua_tostring(embedded, -1);
  if (rows)
    snprintf(out, size, "%s", rows);
  lua_pop(embedded, 1);
  return 0;
}

/* Releases the Howl editor that the frame shows in `container` (a GtkBox), before the frame drops
   the container. See HOWL_EMBED_CLOSE in application.moon. */
int howl_close(void *container)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_CLOSE");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushlightuserdata(embedded, container);
  if (lua_pcall(embedded, 1, 0, 0)) {
    g_critical("Howl could not close an editor: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  return 0;
}

/* Gives the keyboard focus to the Howl editor that the frame shows in `container`. See HOWL_EMBED_FOCUS
   in application.moon. */
int howl_focus(void *container)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_FOCUS");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushlightuserdata(embedded, container);
  if (lua_pcall(embedded, 1, 0, 0)) {
    g_critical("Howl could not focus an editor: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  return 0;
}

/* Sets the code templates of a file for Ctrl+Space in its Howl editor: one row per template,
   "trigger<TAB>body", the body with its backslashes, line breaks and tabs escaped (see
   HOWL_EMBED_TEMPLATES in application.moon and howl.editing.templates). */
int howl_templates(const char *file, const char *rows)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_TEMPLATES");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  lua_pushstring(embedded, rows);
  if (lua_pcall(embedded, 2, 0, 0)) {
    g_critical("Howl templates for %s failed: %s", file, lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  return 0;
}

/* Takes the word of the last Ctrl+click in a Howl editor ("" if none). See HOWL_EMBED_TAKE_CLICK. */
int howl_take_click(char *out, int size)
{
  out[0] = 0;
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_TAKE_CLICK");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  if (lua_pcall(embedded, 0, 1, 0)) {
    g_critical("Howl click failed: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  const char *word = lua_tostring(embedded, -1);
  if (word)
    snprintf(out, size, "%s", word);
  lua_pop(embedded, 1);
  return 0;
}

/* Sets the edge line (eclipse-style margin) of the editors showing `file` to `column` (0 for none);
   other editors get none. See HOWL_EMBED_EDGE in application.moon. */
int howl_edge(const char *file, int column)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_EDGE");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  lua_pushinteger(embedded, column);
  if (lua_pcall(embedded, 2, 0, 0)) {
    g_critical("Howl edge line failed: %s", lua_tostring(embedded, -1));
    return 1;
  }
  return 0;
}

/* Copies the paths of the files shown in the Howl editors, one per line (see HOWL_EMBED_FILES). */
int howl_files(char *out, int size)
{
  out[0] = 0;
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_FILES");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  if (lua_pcall(embedded, 0, 1, 0)) {
    g_critical("Howl files failed: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  const char *text = lua_tostring(embedded, -1);
  if (text)
    snprintf(out, size, "%s", text);
  lua_pop(embedded, 1);
  return 0;
}

/* Inserts text (whole lines) in front of a line of the editor that shows `file` (see HOWL_EMBED_INSERT). */
int howl_insert(const char *file, int line, const char *text)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_INSERT");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  lua_pushinteger(embedded, line);
  lua_pushstring(embedded, text);
  if (lua_pcall(embedded, 3, 1, 0)) {
    g_critical("Howl insert into %s failed: %s", file, lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  int done = lua_toboolean(embedded, -1);
  lua_pop(embedded, 1);
  return done ? 0 : 1;
}

/* Replaces the change marks of the editors that show a file: rows of "line<TAB>kind" (kinds added, changed,
   deleted). See HOWL_EMBED_CHANGES in application.moon. */
int howl_changes(const char *file, const char *rows)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_CHANGES");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  lua_pushstring(embedded, rows);
  if (lua_pcall(embedded, 2, 0, 0)) {
    g_critical("Howl changes for %s failed: %s", file, lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  return 0;
}

/* Copies the text of the buffer that shows a file into out (at most size - 1 bytes). Returns 1 when no Howl
   editor shows the file. See HOWL_EMBED_TEXT in application.moon. */
int howl_text(const char *file, char *out, int size)
{
  out[0] = 0;
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_TEXT");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, file);
  if (lua_pcall(embedded, 1, 1, 0)) {
    g_critical("Howl text of %s failed: %s", file, lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  const char *text = lua_tostring(embedded, -1);
  int found = text != NULL;
  if (text)
    snprintf(out, size, "%s", text);
  lua_pop(embedded, 1);
  return found ? 0 : 1;
}

/* Sets the display options of the editors that show a file and returns the state of the first one: bit 1 when
   it shows the syntax colours, bit 2 when it highlights the current line. A negative syntax or current_line is
   left as it is, so a call with both negative only reads the state. Returns -1 when no Howl editor shows the
   file. See HOWL_EMBED_OPTIONS in application.moon. */
int howl_options(const char *file, int syntax, int current_line)
{
  if (embedded == NULL)
    return -1;

  lua_getglobal(embedded, "HOWL_EMBED_OPTIONS");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return -1;
  }
  lua_pushstring(embedded, file);
  if (syntax < 0)
    lua_pushnil(embedded);
  else
    lua_pushboolean(embedded, syntax);
  if (current_line < 0)
    lua_pushnil(embedded);
  else
    lua_pushboolean(embedded, current_line);
  if (lua_pcall(embedded, 3, 1, 0)) {
    g_critical("Howl options for %s failed: %s", file, lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return -1;
  }
  int state = lua_isnumber(embedded, -1) ? (int) lua_tointeger(embedded, -1) : -1;
  lua_pop(embedded, 1);
  return state;
}

/* Sets the colours of the change stripes in the gutters: "#RRGGBB" for added, modified and deleted lines. See
   HOWL_EMBED_CHANGE_COLOURS in application.moon. */
int howl_change_colours(const char *added, const char *modified, const char *deleted)
{
  if (embedded == NULL)
    return 1;

  lua_getglobal(embedded, "HOWL_EMBED_CHANGE_COLOURS");
  if (!lua_isfunction(embedded, -1)) {
    lua_pop(embedded, 1);
    return 1;
  }
  lua_pushstring(embedded, added);
  lua_pushstring(embedded, modified);
  lua_pushstring(embedded, deleted);
  if (lua_pcall(embedded, 3, 0, 0)) {
    g_critical("Howl change colours failed: %s", lua_tostring(embedded, -1));
    lua_pop(embedded, 1);
    return 1;
  }
  return 0;
}
