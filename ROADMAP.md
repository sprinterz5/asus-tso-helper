# Features and roadmap

asus-tso-helper aims to look and behave like [G-Helper](https://github.com/seerge/g-helper)
on Linux. The reference is G-Helper's current `main` branch, not old screenshots.
Hardware access goes through `asusd` (asusctl) and `supergfxd`. The goal is that a user never
has to edit system files by hand: anything that needs root happens behind a single polkit
prompt the first time the app runs.

Legend: ✅ done · 🟡 planned · ⛔ not possible / not worth it (reason given)

## Done

### Main window
| Feature | G-Helper | Here | Code |
|---|---|---|---|
| Silent / Balanced / Turbo | Modes | asusd platform profile | `ui.on_profile`, `backend.set_profile` |
| Custom modes (`+`, rename, remove) | Modes.cs | Base profile + own fan curves + power limits; the base mode is restored exactly afterwards | `modes.py` |
| Mode remembered per power source | `performance_<ac>` | Stored in config and in asusd (`PlatformProfileOnAc/OnBattery`); custom modes too | `ui.remember_mode`, `ui.on_power_source` |
| Toast on mode / Aura change by key | ToastForm | KDE OSD (`org.kde.osdService.showText`), tray notification elsewhere | `ui.toast`, `backend.osd` |
| GPU Eco / Standard / Ultimate / Optimized | GPUModeControl | supergfxd; pending logout shown with a dashed button, cancel by picking the current mode | `ui.on_gpu`, `ui.switch_gpu` |
| Screen 60 Hz / max / Auto, Overdrive | ScreenControl | kscreen-doctor, asus-armoury `panel_overdrive` | `ui.on_screen` |
| Keyboard: effect, colour, speed, brightness | Aura | asusctl aura | `ui.apply_aura` |
| Battery charge limit, one-time 100% charge | BatteryControl | asusd charge limit | `ui.on_limit`, `ui.on_full_charge` |
| Battery health, charge / discharge watts | — | sysfs power_supply | `backend.battery_status` |
| CPU / GPU temperature, fan RPM | Sensors | hwmon, nvidia-smi only when the dGPU is awake | `backend.sensors` |
| Tray icon and menu, autostart, single instance | — | QSystemTrayIcon, QLocalServer | `ui.Tray`, `ui.main` |
| BIOS and Driver Updates window | Updates.cs | BIOS from the same ASUS API (EZ Flash rows only); instead of Windows drivers: kernel, NVIDIA driver, asusctl, supergfxctl (PackageKit = what Discover can install, upstream in the tooltip), fwupd firmware, this app (GitHub releases). "Install Updates" downloads only the red rows (each with all its packages: every kernel-* or every NVIDIA package, never split) through PackageKit and installs them on restart (offline update, as Discover; online fallback where offline updates are missing). No password on Fedora: PackageKit allows system updates for the active user | `updates.py` |
| New app version notice | AutoUpdateCheck | GitHub latest release at start and daily: red "Download Update" version label, tray notification | `ui.check_app_update` |
| Icons | Icons8 | Lucide (ISC, `assets/icons/LICENSE`); app and tray icon: white S on a circle in the GPU mode colour (`tools/make_icons.py`) | `widgets.icon` |
| Banner when asusd / supergfxd are not running | — | Click to start them (polkit) | `ui.show_services` |

### Fans + Power
| Feature | Here | Code |
|---|---|---|
| CPU / GPU fan curves (8 points), per-fan on/off | asusd fan curves, raw PWM | `fans.py`, `backend.set_fan_curve` |
| Calibrate (real RPM per PWM, per mode) | Charts show real speed, not raw PWM | `FansWindow.calibrate` |
| Factory defaults (saved snapshot / G-Helper defaults) | Snapshot taken on first start | `snapshot_factory_curves` |
| Clamp to grid | As in G-Helper | `FanChart` |
| SPL / sPPT / fPPT | asus-armoury, kept per mode and per power source by asusd | `SliderPanel`, `constrain_ppt` |
| NVIDIA Dynamic Boost, temperature target | asus-armoury `nv_*` | `FansWindow` GPU tab |

### Extra
| Feature | Here |
|---|---|
| Key bindings: FN+F4 and any other laptop key (Add → Laptop key) | evdev grab of "Asus WMI hotkeys" + uinput passthrough; udev rule installed through polkit |
| Key bindings: any keyboard shortcut (Add → Keyboard shortcut) | xdg GlobalShortcuts portal |
| Actions: volume, backlight, screenshot, play, Aura, mode cycle, screen off, lock, brightness, touchpad, mic, calculator, open app, custom command | `hotkeys.ACTIONS`, `ui.on_hotkey` |
| Backlight: brightness, animation speed, Awake / Boot/Shutdown / Sleep | asusctl aura power |
| Backlight timeout on AC / battery | swayidle (installed through polkit) |
| Always on top, disable Overdrive, USB-C charger in Optimized | — |
| Eco without logout (opt-in) | supergfxd `no_logind` + KWin limited to the panel's GPU (`KWIN_DRM_DEVICES`, plasma-workspace env script) **and** to Mesa's EGL (`__EGL_VENDOR_LIBRARY_FILENAMES` in a `plasma-kwin_wayland.service` drop-in). The first attempt without the EGL part let KWin keep `/dev/nvidia0`; supergfxd `kill -9`-ed KWin and hung unloading the driver (reboot). With both, root `lsof` showed only `nvidia-powerd` (stopped by supergfxd). The switch is refused unless KWin started after both files existed (`backend.kwin_igpu_only`). Ports wired to the dGPU (HDMI, DisplayPort here) stop working. |
| Stop apps using the GPU when switching to Eco | Asks first unless the checkbox is set; does nothing if the desktop itself holds the dGPU |
| Boot sound, memory assigned to GPU | Shown only where the firmware has them (asus-armoury `boot_sound`, `apu_mem`) |

## Planned

### Priority 1: important and easy
| # | Feature | How | Notes |
|---|---|---|---|
| 1 | **Release** | GitHub repo, GPL-3.0, README, credits (seerge/G-Helper, Icons8), RPM/COPR requiring `asusctl`, `supergfxctl`, `python3-pyside6`, `python3-evdev`, `swayidle`; first-run setup in one polkit prompt | — |

### Priority 2: useful, needs root
| # | Feature | How | Notes |
|---|---|---|---|
| 3 | CPU Boost on/off per mode (Fans → Advanced) | `/sys/devices/system/cpu/cpufreq/boost` | Grant write access in the first-run setup (udev/tmpfiles), no prompt per change |
| 4 | GPU clock limits | `nvidia-smi -lgc / -lmc` (root) | Core/memory **offsets** depend on the driver version (NVML `SetClockOffsets`) |
| 5 | Translations (Russian first) | Qt translations, strings follow G-Helper's resources | Lots of text, little risk |

### Priority 3: possible, but risky or of little use
| # | Feature | Why it is low |
|---|---|---|
| 6 | CPU undervolt (Curve Optimizer), CPU temperature limit | Needs `ryzenadj` plus the `ryzen_smu` kernel module (not in Fedora, must be signed for Secure Boot). Bad values cause hangs. |
| 8 | Hibernate after N minutes of sleep | Needs a swap partition; Fedora ships zram only |
| 9 | Hint when an app keeps the dGPU awake | e.g. Firefox's video decoder (RDD process) holds `/dev/nvidia0` and drains the battery |

## Not possible or not applicable

| G-Helper feature | Reason |
|---|---|
| AniMe Matrix, Slash lighting, XG Mobile, ROG Ally controls, mid fan, miniLED / OLED modes, NumberPad, status LED, M4 / Armoury key | Not present on TUF A15 (FA507NV); can be added for models that have them |
| ELMB, keystone sound | No firmware attribute on this model |
| ASUS / NVIDIA services, Modern Standby networking, clamshell, ACPI DEVS test | Windows-only concepts, or KDE already does it |
| Windows power plan per mode | asusd already links the CPU energy preference (EPP) to the profile |
| PCIe ASPM toggle | Would need root on every change for little gain |

## Hardware notes (FA507NV, Fedora 44, KDE Wayland)

- `asusd` 6.3.8. PPT limits are stored per profile **and** per power source. asusd's
  `PlatformProfile` numbers: Balanced = 0, Performance = 1, Quiet = 2.
- Firmware power ranges: battery 15 / 35 / 35–65 W, AC up to 80 W; Dynamic Boost 5–25 W on AC
  (locked to 0 on battery); GPU temperature target 75–87 °C.
- Fan curve PWM = percent × 255 / 100; write raw PWM to avoid rounding drift. asusd's
  "reset to defaults" is unreliable here, so use the factory snapshot instead.
- Fn+F4 sends scancode 0xB3 (KEY_PROG4) on "Asus WMI hotkeys"; Fn+F2 / F3 are handled by
  the keyboard firmware and send no event; Fn+F5 cycles the platform profile in the kernel.
- Aura power on TUF (`power-tuf`): the shutdown flag cannot be turned back on once off.
- GPU: the laptop panel is on the AMD iGPU (`card1-eDP-1`); HDMI and one DisplayPort
  (probably USB-C) are on the NVIDIA card. KWin opens every card with ports, and Xwayland gets
  them too, so supergfxd waits for a logout before Eco. An open file does not wake the dGPU
  (it stays `suspended`); apps that use it (e.g. Firefox's video decoder) do.
- dGPU sleep: it suspends ~5 s after its last use. Polling `nvidia-smi` every 2 s kept it awake
  for good (the app was its own culprit). The temperature is now read every 12 s and only while
  the window is open (`ui.DGPU_TEMP_EVERY`); asleep, the last value is shown, as G-Helper does
  since 0.248 (its issue #5290 was the same bug on Windows: NVAPI polling kept the dGPU awake).
- EC GPU temperature (ASUS ACPI `0x00120097`, G-Helper's fallback): not reachable here. With
  Secure Boot the kernel is in lockdown, so `/sys/kernel/debug/asus-nb-wmi` refuses writes even
  for root and `acpi_call` would need signing; Fedora builds without `ec_sys`. The real fix would
  be an asus-wmi hwmon patch upstream (the id is defined in the kernel as
  `ASUS_WMI_DEVID_DGPU_POWER_STATE`), and on some models it returns -65536 anyway.
- supergfxd: Hybrid → Integrated always reports "Logout required"; with `no_logind: true` it
  then switches in the background (kills what holds `/dev/nvidia0` with `kill -9`, unloads the
  driver, removes the device).
