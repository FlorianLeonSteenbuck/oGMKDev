#!/bin/sh
# Copy the ogmkdev files into a root directory (a package build root or a test root).
#   sh packaging/install-tree.sh /path/to/root
# The layout is the same for the Debian and the openSUSE packages.
set -eu
ROOT=${1:?usage: install-tree.sh ROOT}
HERE=$(cd "$(dirname "$0")/.." && pwd)

install -d "$ROOT/usr/bin" "$ROOT/usr/share/ogmkdev" "$ROOT/usr/share/applications" \
           "$ROOT/usr/share/icons/hicolor/scalable/apps" "$ROOT/usr/share/doc/ogmkdev"
cp -r "$HERE/ogmkdev" "$ROOT/usr/share/ogmkdev/"
find "$ROOT/usr/share/ogmkdev" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m 0755 "$HERE/packaging/ogmkdev-launcher" "$ROOT/usr/bin/ogmkdev"
install -m 0644 "$HERE/packaging/ogmkdev.desktop" "$ROOT/usr/share/applications/ogmkdev.desktop"
install -m 0644 "$HERE/ogmkdev/ui/logo.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/ogmkdev.svg"
install -m 0644 "$HERE/LICENSE" "$HERE/README.md" "$HERE/THIRD_PARTY_NOTICES.md" "$ROOT/usr/share/doc/ogmkdev/"
