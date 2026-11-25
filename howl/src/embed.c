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
