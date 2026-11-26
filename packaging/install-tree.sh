#!/bin/sh
# Copy the ogmkdev files into a root directory (a package build root or a test root).
#   sh packaging/install-tree.sh /path/to/root [libdir]
# The layout is the same for the Debian and the openSUSE packages:
#   usr/bin/ogmkdev                 the starter (packaging/ogmkdev-launcher)
#   LIBDIR/ogmkdev/libhowl.so       Howl as a library, built by packaging/build-howl.sh; LIBDIR is usr/lib
#                                   unless given: the RPM passes %{_libdir}, usr/lib64 on 64-bit systems
#   usr/share/ogmkdev/ogmkdev/      the Python package
#   usr/share/ogmkdev/howl/         Howl's Lua files, bundles, fonts and share data
#   usr/share/applications, icons, doc: the desktop entry, the logo and the documentation
set -eu
ROOT=${1:?usage: install-tree.sh ROOT [LIBDIR]}
LIBDIR=${2:-/usr/lib}
HERE=$(cd "$(dirname "$0")/.." && pwd)

if [ ! -f "$HERE/howl/src/libhowl.so" ]; then
  echo "install-tree: howl/src/libhowl.so is missing; run sh packaging/build-howl.sh first" >&2
  exit 1
fi

install -d "$ROOT/usr/bin" "$ROOT$LIBDIR/ogmkdev" "$ROOT/usr/share/ogmkdev/howl" \
           "$ROOT/usr/share/applications" "$ROOT/usr/share/icons/hicolor/scalable/apps" \
           "$ROOT/usr/share/doc/ogmkdev"
cp -r "$HERE/ogmkdev" "$ROOT/usr/share/ogmkdev/"
find "$ROOT/usr/share/ogmkdev" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m 0755 "$HERE/howl/src/libhowl.so" "$ROOT$LIBDIR/ogmkdev/libhowl.so"
for part in lib bundles share fonts; do
  if [ -d "$HERE/howl/$part" ]; then
    cp -r "$HERE/howl/$part" "$ROOT/usr/share/ogmkdev/howl/"
  fi
done
find "$ROOT/usr/share/ogmkdev/howl" -name '*.o' -o -name '*.a' | xargs -r rm -f
install -m 0755 "$HERE/packaging/ogmkdev-launcher" "$ROOT/usr/bin/ogmkdev"
install -m 0644 "$HERE/packaging/ogmkdev.desktop" "$ROOT/usr/share/applications/ogmkdev.desktop"
install -m 0644 "$HERE/packaging/logo.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/ogmkdev.svg"
install -m 0644 "$HERE/LICENSE" "$HERE/README.md" "$HERE/THIRD_PARTY_NOTICES.md" "$ROOT/usr/share/doc/ogmkdev/"
install -m 0644 "$HERE/howl/LICENSE.md" "$ROOT/usr/share/doc/ogmkdev/HOWL-LICENSE.md"
