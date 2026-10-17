# Changelog

## 0.5.0
- **Battery** window (the small chart button next to Battery Charge Limit, or the tray menu):
  charge and power draw over 24 hours or 7 days, battery health, and the average draw of each mode
  on battery with the hours a full charge lasts in it.
- **Game hints**: a notification with a button when a game starts in Eco (Cardwire kept it off the
  NVIDIA GPU: switch to Standard) or in Silent (switch to Turbo). Once per game; off in Extra.
- **After sleep** the mode of the current power source, screen rate, GPU auto mode, keyboard
  level and lighting are put back: the charger may have changed while asleep.
- **Deep sleep (S3)** option in Extra on laptops whose firmware offers it, instead of s2idle that
  can drain the battery overnight.
- Install Updates shows a progress bar under each update and the package being fetched; it no
  longer hangs on packages with two architectures, and reopening the window keeps a running install.
- The tray tooltip always shows the dGPU: off (Eco), sleeping, or awake and which apps keep it so.
- "Keep app window always on top" works on Wayland (through KWin).
- Closing the main window closes Fans, Extra, Updates and Battery too; opening it brings them back.

## 0.4.0
- **AppImage**: one file for any distribution with glibc 2.34+ (2021 on), with Python, Qt and the
  key libraries inside. It adds itself to the app menu on first start.
- **Update in one click**: when a new release is out, the red version label (or the app row in
  Updates) downloads it, checks GitHub's SHA-256 and restarts into it.
- Ultimate (MUX) tested both ways; a MUX change asusd keeps queued until shutdown shows as pending.
- **Russian** translation, picked from the system language or in Extra → Language. Other languages
  are one JSON file each in `asus_tso_helper/translations/`.
- Refresh rate also on **GNOME** (Mutter's display API), **Sway / Hyprland** (wlr-randr) and X11
  (xrandr), not only KDE.
- **RPM** (COPR) and **AUR** packages on the system's Python and Qt.
- KDE no longer switches the power profile on plug / unplug: it did so before the app and could
  leave Silent on battery instead of the remembered mode.
- The tray tooltip names the apps keeping the dGPU awake ("dGPU awake: firefox").
- **CPU Boost** on or off per mode (Fans → Advanced), a **MangoHud** key action, and a clamshell
  mode checkbox in Extra (KDE).
- Light / dark theme follows the desktop while the app runs, in the AppImage too; Extra can fix it
  to dark or light, and take the desktop's accent colour instead of G-Helper's blue.
- Fans, Extra, Updates and Setup open beside the main window, left or right where there is room (KDE).

## 0.3.0
- GPU modes on **Cardwire** instead of supergfxd: Eco and Standard switch at once, without a
  logout, and HDMI keeps working. Ultimate switches the firmware MUX through asusd.
- Setup installs Cardwire from Terra and retires supergfxd.
- Power Mode (CPU EPP) per mode in Fans → Advanced, battery time left / to full, keyboard brightness
  per power source, a key action per mode, stop nvidia-powerd on battery, diagnostics report.
- The main window opens at the tray icon (KDE).

## 0.2.1
- First-run Setup: Terra repository, power-profiles-daemon, key rule, swayidle in one password.
- Updates installs only the red rows.

## 0.2.0
- First version: G-Helper's main window, Fans + Power, Extra, Updates on asusctl / supergfxctl.
