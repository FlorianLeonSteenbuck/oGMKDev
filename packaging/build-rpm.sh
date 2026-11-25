#!/bin/sh
# Build the openSUSE (and Fedora-style) package: dist/rpmbuild/RPMS/noarch/ogmkdev-<version>.noarch.rpm
#   sh packaging/build-rpm.sh          (needs rpmbuild; openSUSE: sudo zypper install rpm-build)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")
TOP="$ROOT/dist/rpmbuild"
mkdir -p "$TOP/SOURCES" "$TOP/SPECS"
tar czf "$TOP/SOURCES/ogmkdev-$VERSION.tar.gz" \
    --exclude=./dist --exclude=./.git --exclude=./kdevelop --exclude=__pycache__ \
    --transform "s,^\.,ogmkdev-$VERSION," -C "$ROOT" .
cp "$HERE/ogmkdev.spec" "$TOP/SPECS/"
rpmbuild --define "_topdir $TOP" --define "version $VERSION" -ba "$TOP/SPECS/ogmkdev.spec"
