#!/bin/sh
# Build the Debian/Ubuntu package: dist/ogmkdev_<version>_all.deb
#   sh packaging/build-deb.sh          (needs dpkg-deb; install with: apt install dpkg-dev)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

sh "$HERE/install-tree.sh" "$STAGE"
chmod 0755 "$STAGE"
install -d "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: ogmkdev
Version: $VERSION
Section: devel
Priority: optional
Architecture: all
Maintainer: ogmkdev maintainers <ogmkdev@localhost>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, gir1.2-gtksource-3.0
Recommends: gdb
Suggests: php-cli, php-xdebug, gcc
Homepage: https://github.com/FlorianLeonSteenbuck/oGMKDev
Description: lightweight GTK code editor
 ogmkdev is a code editor with EditorConfig configuration, a project index
 (classes, hierarchy, implementations, search in files), PHP 8.0 to 8.6
 feature checks, JetBrains-style run configurations and GDB and XDebug
 debugging.
CONTROL
mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/ogmkdev_${VERSION}_all.deb"
echo "built $ROOT/dist/ogmkdev_${VERSION}_all.deb"
