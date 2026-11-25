Name:           ogmkdev
Version:        %{version}
Release:        1
Summary:        Lightweight GTK code editor with EditorConfig, project index and debugging
License:        GPL-2.0-or-later
URL:            https://github.com/FlorianLeonSteenbuck/oGMKDev
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       typelib-1_0-Gtk-3_0
Requires:       typelib-1_0-GtkSource-3_0
Recommends:     gdb
Suggests:       php-cli

%description
ogmkdev is a code editor with EditorConfig configuration, a project index
(classes, hierarchy, implementations, search in files), PHP 8.0 to 8.6
feature checks, JetBrains-style run configurations and GDB and XDebug
debugging.

%prep
%setup -q

%build

%install
sh packaging/install-tree.sh %{buildroot}

%files
%license LICENSE
%doc README.md THIRD_PARTY_NOTICES.md
%{_bindir}/ogmkdev
%{_datadir}/ogmkdev
%{_datadir}/applications/ogmkdev.desktop
%{_datadir}/icons/hicolor/scalable/apps/ogmkdev.svg

%changelog
* Wed Nov 25 2026 ogmkdev maintainers <ogmkdev@localhost> - 0.1.0-1
- First package: editor, workspace and project tools, debugging, PHP 8.0 to 8.6 checks.
