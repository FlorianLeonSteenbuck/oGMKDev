# Packaging

The packages contain the Python package, the starter, the desktop entry, and Howl as a library:
`libhowl.so` (built from `howl/` by `build-howl.sh`) and Howl's Lua files. The library is for the
machine it was built on, so the packages are per architecture.

Build order:

| Step | Command | Output |
|---|---|---|
| 1. Howl library | `sh packaging/build-howl.sh` | `howl/src/libhowl.so`, `howl/src/howl` |
| 2a. Debian, Ubuntu | `sh packaging/build-deb.sh` | `dist/ogmkdev_<version>_<arch>.deb` |
| 2b. openSUSE (and Fedora-style) | `sh packaging/build-rpm.sh` | `dist/rpmbuild/RPMS/<arch>/ogmkdev-<version>-1.<arch>.rpm` |

`build-howl.sh` needs the LuaJIT 2.1 sources: set `LUAJIT_SRC` to an unpacked tree, or put one in
`build/howl-deps/luajit-src/luajit-*/`, or enable a `deb-src` entry so that `apt-get source luajit`
works. It also needs `gcc`, `make`, `pkg-config`, `git` and the GTK 4 development files
(`libgtk-4-dev`, `gir1.2-gtk-4.0` for the runtime).

Install:

```bash
sudo apt install ./dist/ogmkdev_0.1.0_amd64.deb                  # Debian, Ubuntu
sudo zypper install ./dist/rpmbuild/RPMS/x86_64/ogmkdev-0.1.0-1.x86_64.rpm   # openSUSE
```

The layout is the same for both packages (`packaging/install-tree.sh`):

- `/usr/bin/ogmkdev`: the starter. It sets `OGMKDEV_HOWL_LIBRARY` and `OGMKDEV_HOWL_ROOT` and runs the
  frame with the first Python 3 that has GTK 4 (`python3 -m ogmkdev.frame`).
- `/usr/lib/ogmkdev/libhowl.so`: Howl as a library.
- `/usr/share/ogmkdev/ogmkdev`: the Python package; `/usr/share/ogmkdev/howl`: Howl's `lib`, `bundles`,
  `share` and `fonts`.
- The desktop entry, the logo and the documentation.

Build dependencies: `dpkg-dev` for the `.deb`; `rpm-build` (openSUSE) for the `.rpm`.
The `.deb` build is tested here: the installed layout was checked by running the starter from an
unpacked package on Xvfb.
The `.rpm` spec is written for openSUSE and has not been built in CI.
