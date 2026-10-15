# asus-tso-helper

**G-Helper for Linux.** A port of [G-Helper](https://github.com/seerge/g-helper) by
[seerge](https://github.com/seerge) to Linux, with the same windows, layout and behaviour.
Its interface is seerge's work. This project brings it to Linux on top of
[asusctl / supergfxctl](https://asus-linux.org).

> **Early preview.** Developed and tested on an ASUS TUF Gaming A15 (FA507NV) with Fedora 44 and
> KDE Plasma 6 (Wayland). A first-run setup and packages (AppImage, COPR, AUR) are on the way;
> see [ROADMAP.md](ROADMAP.md).

<p>
  <img src="docs/main.png" width="300" alt="Main window">
  <img src="docs/fans.png" width="470" alt="Fans + Power">
</p>

## Features

- **Performance modes**: Silent, Balanced and Turbo, plus your own custom modes. Each power source
  remembers its own mode, and a toast shows the mode when you switch with Fn+F5 or a bound key.
- **Fans + Power**: CPU and GPU fan curves with calibration to real RPM, factory defaults, and
  CPU power limits (SPL, sPPT, fPPT). For NVIDIA GPUs: Dynamic Boost and temperature target.
- **GPU modes**: Eco, Standard, Ultimate (MUX) and Optimized (Eco on battery). An optional
  **Eco without logout** switches inside the session (see below).
- **Screen**: 60 Hz, max Hz or automatic by power source, with panel overdrive.
- **Keyboard**: Aura effects, colour, speed, brightness, backlight timeout, and lighting on
  boot, awake and sleep.
- **Key bindings**: actions for Fn+F4 and other laptop keys, plus any keyboard shortcut through
  the desktop.
- **Battery**: charge limit, a one-time charge to 100%, battery health and charge rate.
- **Updates**: the BIOS for your model (the same ASUS source G-Helper uses), the kernel, the
  NVIDIA driver, asusctl, supergfxctl, firmware (fwupd) and this app. A single button installs
  kernel and driver updates on the next restart.
- **Sleep-friendly**: the NVIDIA GPU is only queried while it is already awake, so the app never
  keeps it from powering down.

## Requirements

- An ASUS laptop supported by [asusctl](https://asus-linux.org), with the `asusd` and `supergfxd`
  services.
- Python 3 with PySide6, python-evdev and dbus-python.
- KDE Plasma 6 is the main target: refresh rate, toasts and the logout prompt use KDE. Most other
  features work on any desktop.
- Optional: the NVIDIA driver (for games and the GPU temperature) and `swayidle` (for the
  keyboard backlight timeout).

Anything that needs root (the key rule, services, packages) is done from inside the app, behind
one password prompt.

## Running from source

```bash
git clone https://github.com/sprinterz5/asus-tso-helper
```

```bash
./asus-tso-helper/asus-tso-helper
```

## Eco without logout

Normally `supergfxd` waits for a logout before it turns the NVIDIA GPU off, because the desktop
(KWin) keeps it open. **Extra → Eco without logout** starts KWin with only the GPU that drives
the laptop panel and with Mesa's EGL. After one logout, Eco and Standard then switch in a few
seconds. The catch: ports wired to the NVIDIA GPU (on many laptops HDMI and USB-C video) do not
work while this option is on. The app refuses an in-session switch unless KWin really started
that way, because forcing it while KWin holds the GPU can hang the driver.

## Credits

- **[G-Helper](https://github.com/seerge/g-helper) by seerge**: the interface, layout, colours,
  behaviour and defaults this app follows. If you like this app, support G-Helper too.
- **[asus-linux](https://asus-linux.org)**: asusctl / asusd and supergfxctl / supergfxd, which do
  the actual hardware work.
- **[Lucide](https://lucide.dev)**: icons (ISC licence, `asus_tso_helper/assets/icons/LICENSE`).

## Support

Donation links are coming.

## License

[GPL-3.0](LICENSE), like G-Helper.

Not affiliated with or endorsed by ASUS. ASUS, ROG and TUF are trademarks of ASUSTeK Computer Inc.
