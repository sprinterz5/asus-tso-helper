# Changelog

## 0.4.0
- **AppImage**: one file for any distribution with glibc 2.34+ (2021 on), with Python, Qt and the
  key libraries inside. It adds itself to the app menu on first start.
- **Update in one click**: when a new release is out, the red version label (or the app row in
  Updates) downloads it, checks GitHub's SHA-256 and restarts into it.
- Ultimate (MUX) tested both ways; a MUX change asusd keeps queued until shutdown shows as pending.

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
