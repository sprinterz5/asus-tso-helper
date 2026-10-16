Name:           asus-tso-helper
Version:        0.4.0
Release:        1%{?dist}
Summary:        G-Helper for Linux: modes, GPU, fans and battery of ASUS laptops

# the app is GPL-3.0; its Lucide icons are ISC
License:        GPL-3.0-only AND ISC
URL:            https://github.com/sprinterz5/asus-tso-helper
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  make
BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
BuildRequires:  systemd-rpm-macros

Requires:       python3
Requires:       python3-pyside6
Requires:       python3-evdev
Requires:       python3-dbus
Requires:       hicolor-icon-theme
# asusctl and cardwire come from the Terra repository, which the app's Setup adds;
# weak dependencies keep the package installable without it
Recommends:     asusctl
Recommends:     cardwire
Recommends:     swayidle
Recommends:     libkscreen

%description
A Linux port of G-Helper by seerge, with the same windows and behavior:
performance and custom modes, GPU modes (Eco, Standard, Ultimate, Optimized),
fan curves and power limits, keyboard lighting, battery charge limit, key
bindings and BIOS / driver updates. Hardware control goes through asusd
(asusctl) and Cardwire. Not affiliated with ASUS.

%prep
%autosetup

%build
# nothing to build: Python

%install
%make_install PREFIX=%{_prefix} UDEVDIR=%{_udevrulesdir}
%py_byte_compile %{python3} %{buildroot}%{_datadir}/%{name}

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/%{name}.desktop

%files
%license LICENSE asus_tso_helper/assets/icons/LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/%{name}
%{_datadir}/%{name}/
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/256x256/apps/%{name}.png
%{_datadir}/icons/hicolor/scalable/apps/%{name}.svg
%{_udevrulesdir}/70-%{name}.rules

%changelog
* Fri Oct 16 2026 sprinterz5 <63397324+sprinterz5@users.noreply.github.com> - 0.4.0-1
- AppImage and one-click update; GPU modes on Cardwire; see CHANGELOG.md
