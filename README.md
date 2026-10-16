# asus-tso-helper

**G-Helper for Linux.** A port of [G-Helper](https://github.com/seerge/g-helper) by
[seerge](https://github.com/seerge) to Linux, with the same windows, layout and behaviour.
Its interface is seerge's work. This project brings it to Linux on top of
[asusctl](https://asus-linux.org) and [Cardwire](https://opengamingcollective.github.io/cardwire/).

> **Early preview.** Developed and tested on an ASUS TUF Gaming A15 (FA507NV) with Fedora 44 and
> KDE Plasma 6 (Wayland). Packages for COPR and AUR are on the way; see [ROADMAP.md](ROADMAP.md).

<p>
  <img src="docs/main.png" width="300" alt="Main window">
  <img src="docs/fans.png" width="470" alt="Fans + Power">
</p>

## Features

- **Performance modes**: Silent, Balanced and Turbo, plus your own custom modes. Each power source
  remembers its own mode, and a toast shows the mode when you switch with Fn+F5 or a bound key.
- **Fans + Power**: CPU and GPU fan curves with calibration to real RPM, factory defaults, and
  CPU power limits (SPL, sPPT, fPPT). For NVIDIA GPUs: Dynamic Boost and temperature target.
- **GPU modes**: Eco, Standard, Ultimate (MUX) and Optimized (Eco on battery). Eco and Standard
  switch at once, without a logout (Cardwire).
- **Screen**: 60 Hz, max Hz or automatic by power source, with panel overdrive.
- **Keyboard**: Aura effects, colour, speed, brightness, backlight timeout, and lighting on
  boot, awake and sleep.
- **Key bindings**: actions for Fn+F4 and other laptop keys, plus any keyboard shortcut through
  the desktop.
- **Battery**: charge limit, a one-time charge to 100%, battery health and charge rate.
- **Updates**: the BIOS for your model (the same ASUS source G-Helper uses), the kernel, the
  NVIDIA driver, asusctl, Cardwire, firmware (fwupd) and this app. A single button installs
  kernel and driver updates on the next restart.
- **Sleep-friendly**: the NVIDIA GPU is only queried while it is already awake, so the app never
  keeps it from powering down.

## Requirements

- An ASUS laptop supported by [asusctl](https://asus-linux.org), with the `asusd` service.
- For GPU modes: [Cardwire](https://opengamingcollective.github.io/cardwire/) (stable release,
  Wayland, a kernel with BPF LSM; Fedora and Arch have it).
- Python 3 with PySide6, python-evdev and dbus-python.
- KDE Plasma 6 is the main target: refresh rate, toasts and the logout prompt use KDE. Most other
  features work on any desktop.
- Optional: the NVIDIA driver (for games and the GPU temperature) and `swayidle` (for the
  keyboard backlight timeout).

Anything that needs root (the key rule, services, packages) is done from inside the app, behind
one password prompt.

## Install

Download `asus-tso-helper-x86_64.AppImage` from the
[latest release](https://github.com/sprinterz5/asus-tso-helper/releases/latest), then:

```bash
chmod +x asus-tso-helper-x86_64.AppImage
```

```bash
./asus-tso-helper-x86_64.AppImage
```

On first start it adds itself to the app menu, and the Setup window offers to install what the
laptop still needs (asusd, Cardwire) behind one password prompt. New versions install from the
app itself: click the red version label. The AppImage runs on distributions with glibc 2.34 or
newer (Fedora 35+, Ubuntu 22.04+, Debian 12+, Arch).

### Packages

- **Fedora**: COPR `sprinterz5/asus-tso-helper` (coming with the first public release). asusctl and
  Cardwire come from the Terra repository; the app's Setup adds it.
- **Arch**: AUR `asus-tso-helper`. Cardwire is in the AUR too.

The packages use the system's Python and Qt (about 250 KB) and ship the key rule, so Setup has
less to do. Updates come through the package manager.

### From source

```bash
git clone https://github.com/sprinterz5/asus-tso-helper
```

```bash
./asus-tso-helper/asus-tso-helper
```

Build the AppImage yourself with `packaging/appimage/build-in-podman.sh` (needs podman).

## GPU modes

Eco and Standard go through Cardwire, the successor of supergfxd from the asus-linux / Open
Gaming Collective people. It does not unload the NVIDIA driver: it stops new programs from
opening the dGPU, which then powers down by itself. So switching takes a moment and needs no
logout, and HDMI keeps working in Standard. Programs that already use the dGPU keep it until they
quit; the app offers to close them. Ultimate switches the MUX in the firmware and needs a reboot.
The Setup window installs Cardwire and retires supergfxd if it is still running.

## Credits

- **[G-Helper](https://github.com/seerge/g-helper) by seerge**: the interface, layout, colours,
  behaviour and defaults this app follows. If you like this app, support G-Helper too.
- **[asus-linux](https://asus-linux.org)** / **[Open Gaming Collective](https://github.com/OpenGamingCollective)**:
  asusctl / asusd and Cardwire, which do the actual hardware work.
- **[Lucide](https://lucide.dev)**: icons (ISC licence, `asus_tso_helper/assets/icons/LICENSE`).

## Support

Donation links are coming.

## License

[GPL-3.0](LICENSE), like G-Helper.

Not affiliated with or endorsed by ASUS. ASUS, ROG and TUF are trademarks of ASUSTeK Computer Inc.
