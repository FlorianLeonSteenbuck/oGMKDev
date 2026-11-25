# Packaging

| Target | Command | Output |
|---|---|---|
| Debian, Ubuntu | `sh packaging/build-deb.sh` | `dist/ogmkdev_<version>_all.deb` |
| openSUSE (and Fedora-style) | `sh packaging/build-rpm.sh` | `dist/rpmbuild/RPMS/noarch/ogmkdev-<version>-1.noarch.rpm` |

Install:

```bash
sudo apt install ./dist/ogmkdev_0.1.0_all.deb        # Debian, Ubuntu
sudo zypper install ./dist/rpmbuild/RPMS/noarch/ogmkdev-0.1.0-1.noarch.rpm   # openSUSE
```

Both packages share one layout (`packaging/install-tree.sh`): the Python package is installed under
`/usr/share/ogmkdev`, the starter is `/usr/bin/ogmkdev`, and the desktop entry and the logo are installed
for the application menu.

Build dependencies: `dpkg-dev` for the `.deb`; `rpm-build` (openSUSE) for the `.rpm`.
The `.deb` build is tested; the `.rpm` spec is written for openSUSE and is not yet built in CI.
