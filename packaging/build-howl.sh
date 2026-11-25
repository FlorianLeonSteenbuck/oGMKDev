#!/bin/sh
# Builds the Howl library and binary that the oGMKDev editor window runs on.
#
# howl/ is a patched copy of https://github.com/howl-editor/howl (see howl/OGMKDEV.md).
# Howl's own Makefile downloads LuaJIT and lpeg; this script builds the same versions
# from sources that can be fetched here instead:
#
#   LuaJIT 2.1, built with LUA52COMPAT (Howl needs table.pack and other Lua 5.2 functions).
#   Its source tree is found in LUAJIT_SRC, or in build/howl-deps/luajit-src/luajit-*/, or it is
#   fetched with apt-get source (needs a deb-src entry in apt).
#   lpeg 0.10.2 from the LuaDist repository tag (Howl's lexers need its variable-length B()).
#
# Needs: gcc, make, pkg-config, git, GTK 4 development files (libgtk-4-dev).
# Output: howl/src/howl (run it as ./howl/src/howl file.txt) and howl/src/libhowl.so (the library
# that the GTK 4 frame loads).
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${OGMKDEV_BUILD_DIR:-$ROOT/build/howl-deps}
mkdir -p "$WORK"

if [ -z "${LUAJIT_SRC:-}" ]; then
  LUAJIT_SRC=$(ls -d "$WORK"/luajit-src/luajit-*/ 2>/dev/null | head -1 || true)
  if [ -z "$LUAJIT_SRC" ]; then
    mkdir -p "$WORK/luajit-src"
    if (cd "$WORK/luajit-src" && apt-get source -q luajit) >/dev/null 2>&1; then
      LUAJIT_SRC=$(ls -d "$WORK"/luajit-src/luajit-*/ 2>/dev/null | head -1 || true)
    fi
  fi
  if [ -z "$LUAJIT_SRC" ]; then
    echo "build-howl: no LuaJIT source tree found." >&2
    echo "  Unpack LuaJIT 2.1 and set LUAJIT_SRC to it, or add a deb-src entry and run apt-get source" >&2
    echo "  in $WORK/luajit-src." >&2
    exit 1
  fi
  LUAJIT_SRC=${LUAJIT_SRC%/}
fi
if [ ! -f "$LUAJIT_SRC/src/libluajit.a" ]; then
  make -C "$LUAJIT_SRC" XCFLAGS="-DLUAJIT_ENABLE_LUA52COMPAT -fPIC"
fi
cp "$LUAJIT_SRC/src/libluajit.a" "$WORK/libluajit.a"

if [ ! -d "$WORK/lpeg" ]; then
  git clone -q --depth 1 --branch 0.10.2 https://github.com/LuaDist/lpeg.git "$WORK/lpeg"
fi
cc -c -O2 -fPIC -I"$LUAJIT_SRC/src" "$WORK/lpeg/lpeg.c" -o "$WORK/lpeg.o"

GTK_LIBS=$(pkg-config --libs gtk4 gmodule-2.0 gio-unix-2.0)
make -C "$ROOT/howl/src" howl \
  LUAJIT="$LUAJIT_SRC" \
  LUAJIT_SRC_DIR="$LUAJIT_SRC/src" \
  LUAJIT_CFLAGS="-I$LUAJIT_SRC/src" \
  ARCHIVES="$WORK/libluajit.a" \
  DEP_OBJECTS="$WORK/lpeg.o" \
  LIBS="-lm -ldl $GTK_LIBS"

make -C "$ROOT/howl/src" libhowl.so \
  LUAJIT="$LUAJIT_SRC" \
  LUAJIT_SRC_DIR="$LUAJIT_SRC/src" \
  LUAJIT_CFLAGS="-I$LUAJIT_SRC/src" \
  ARCHIVES="$WORK/libluajit.a" \
  DEP_OBJECTS="$WORK/lpeg.o" \
  LIBS="-lm -ldl $GTK_LIBS"

echo "built $ROOT/howl/src/howl and $ROOT/howl/src/libhowl.so"
