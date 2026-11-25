/* Howl as a library. The editor's content is a GTK widget that the calling program puts into
   its own layout (for example a GtkBox of a GTK 4 Python application). The window Howl creates
   for the content is hidden; the content itself is moved into the container.
   Build: make libhowl.so (see packaging/build-howl.sh). */
#include <gtk/gtk.h>
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>

int luaopen_lpeg(lua_State *L);

static lua_State *embedded = NULL;

/* Starts Howl's Lua side in the process and puts the editor into `container`.
   Returns 0 on success. The Lua state lives as long as the process (the GTK main loop runs it). */
int howl_embed(GtkBox *container, const char *app_root, const char *file)
{
  if (embedded != NULL)
    return 1;

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
