Name:           ogmkdev
Version:        %{version}
Release:        1
Summary:        Lightweight GTK code editor with EditorConfig, project index and debugging
License:        GPL-2.0-or-later
URL:            https://github.com/FlorianLeonSteenbuck/oGMKDev
Source0:        %{name}-%{version}.tar.gz
Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       python3-gobject-cairo
Requires:       typelib-1_0-Gtk-4_0
Requires:       libgtk-4-1
Recommends:     gdb
Suggests:       php-cli

%description
ogmkdev is a code editor with EditorConfig configuration, a project index
(classes, hierarchy, implementations, search in files), PHP 8.0 to 8.6
feature checks, JetBrains-style run configurations and GDB and XDebug
debugging. The editor windows are Howl (libhowl.so, with its Lua files).

%prep
%setup -q

%build
# The library is built by packaging/build-howl.sh (needs LuaJIT sources, see packaging/README.md);
# a tree that already has howl/src/libhowl.so is packaged as it is.
test -f howl/src/libhowl.so || sh packaging/build-howl.sh

%install
sh packaging/install-tree.sh %{buildroot} %{_libdir}

%files
%license LICENSE
%doc README.md THIRD_PARTY_NOTICES.md
%{_bindir}/ogmkdev
%{_libdir}/ogmkdev/libhowl.so
%{_datadir}/ogmkdev
%{_datadir}/applications/ogmkdev.desktop
%{_datadir}/icons/hicolor/scalable/apps/ogmkdev.svg
%{_docdir}/ogmkdev

%changelog
* Wed Nov 25 2026 ogmkdev maintainers <ogmkdev@localhost> - 0.1.0-1
- First package: editor, workspace and project tools, debugging, PHP 8.0 to 8.6 checks.
- The window runs on GTK 4 with Howl as a library (libhowl.so and the Howl Lua files).
