# Features and roadmap

asus-tso-helper aims to look and behave like [G-Helper](https://github.com/seerge/g-helper)
on Linux. The reference is G-Helper's current `main` branch, not old screenshots.
Hardware access goes through `asusd` (asusctl) and Cardwire (`cardwired`). The goal is that a user never
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
| GPU Eco / Standard / Ultimate / Optimized | GPUModeControl | Eco / Standard: Cardwire (D-Bus `Mode`), at once, no logout. Ultimate: firmware MUX (`gpu_mux_mode`) through asusd, which queues the write and makes it at shutdown, reboot (tested: panel on the NVIDIA card after the reboot); pending shown with a dashed button, cancel by picking the current mode | `ui.on_gpu`, `ui.switch_gpu`, `backend.set_gpu_mode` |
| Screen 60 Hz / max / Auto, Overdrive | ScreenControl | kscreen-doctor, asus-armoury `panel_overdrive` | `ui.on_screen` |
| Keyboard: effect, colour, speed, brightness | Aura | asusctl aura | `ui.apply_aura` |
| Battery charge limit, one-time 100% charge | BatteryControl | asusd charge limit | `ui.on_limit`, `ui.on_full_charge` |
| Battery health, charge / discharge watts | — | sysfs power_supply | `backend.battery_status` |
| Time left / to full, battery cycles | (ROG Control Center) | UPower's estimate next to the charge; cycles on hover when the battery reports them | `backend.battery_time`, `backend.battery_cycles` |
| One-time charge to 100% through asusd | BatteryControl | asusd `OneShotFullCharge`: the limit comes back on unplug even without the app, at 100% the app restores it | `ui.on_full_charge` |
| Keyboard brightness per power source | `keyboard_brightness_ac` | Remembered by polling (Fn+F2/F3 are firmware keys), restored on plug / unplug; idle-off is not remembered | `ui.remember_kbd_level` |
| Main window opens at the tray icon | (window above the taskbar) | Wayland apps cannot place windows: a KWin script loaded over D-Bus at start puts it at the cursor, inside the work area | `assets/kwin/place.js`, `backend.kwin_place_window` |
| CPU / GPU temperature, fan RPM | Sensors | hwmon, nvidia-smi only when the dGPU is awake | `backend.sensors` |
| Tray icon and menu, autostart, single instance | — | QSystemTrayIcon, QLocalServer | `ui.Tray`, `ui.main` |
| First-run Setup | — | Checks ASUS laptop, asusd, Cardwire (installs it, replacing switcheroo-control; moves supergfxd back to Hybrid and disables it), Terra repo (moves off the dead lukenukem COPR), tuned-ppd → power-profiles-daemon (asusctl issue #724), key rule, Python modules, swayidle, NVIDIA driver (info only), KDE (info). Fixes everything in one pkexec script for dnf / pacman / apt / zypper, output shown live. Opens at start when something required or recommended is missing; also Extra → Setup | `setup.py` |
| BIOS and Driver Updates window | Updates.cs | BIOS from the same ASUS API (EZ Flash rows only); instead of Windows drivers: kernel, NVIDIA driver, asusctl, Cardwire (PackageKit = what Discover can install, upstream in the tooltip), fwupd firmware, this app (GitHub releases). "Install Updates" downloads only the red rows (each with all its packages: every kernel-* or every NVIDIA package, never split) through PackageKit and installs them on restart (offline update, as Discover; online fallback where offline updates are missing). No password on Fedora: PackageKit allows system updates for the active user | `updates.py` |
| New app version notice | AutoUpdateCheck | GitHub latest release at start and daily: red "Download Update" version label, tray notification | `ui.check_app_update` |
| AppImage + one-click update | AutoUpdateControl | Built in manylinux_2_34 (podman locally, GitHub Actions on a `v*` tag): python-appimage's Python 3.12, PySide6-Essentials (unused Qt modules dropped), evdev, dbus-python. The label or the Updates row downloads the new AppImage next to the running one, checks GitHub's SHA-256 digest, renames it over and restarts. On start it writes its menu entry and icon; root steps get file contents inline, since root cannot read the FUSE mount | `packaging/appimage/`, `selfupdate.py`, `backend.integrate_desktop` |
| Icons | Icons8 | Lucide (ISC, `assets/icons/LICENSE`); app and tray icon: white S on a circle in the GPU mode colour (`tools/make_icons.py`) | `widgets.icon` |
| Banner when asusd / cardwired are not running | — | Click to start them (polkit), or Setup when not installed | `ui.show_services` |

### Fans + Power
| Feature | Here | Code |
|---|---|---|
| CPU / GPU fan curves (8 points), per-fan on/off | asusd fan curves, raw PWM | `fans.py`, `backend.set_fan_curve` |
| Calibrate (real RPM per PWM, per mode) | Charts show real speed, not raw PWM | `FansWindow.calibrate` |
| Power Mode per mode (Advanced tab) | G-Helper's Windows power slider = the CPU's EPP: Best Battery … Best Performance, kept per profile by asusd (`Profile*Epp`). asusd applies any EPP the moment it is set, so the current profile's value is written again afterwards | `backend.set_profile_epp` |
| Factory defaults (saved snapshot / G-Helper defaults) | Snapshot taken on first start | `snapshot_factory_curves` |
| Clamp to grid | As in G-Helper | `FanChart` |
| SPL / sPPT / fPPT | asus-armoury, kept per mode and per power source by asusd | `SliderPanel`, `constrain_ppt` |
| NVIDIA Dynamic Boost, temperature target | asus-armoury `nv_*` | `FansWindow` GPU tab |

### Extra
| Feature | Here |
|---|---|
| Key bindings: FN+F4 and any other laptop key (Add → Laptop key) | evdev grab of "Asus WMI hotkeys" + uinput passthrough; udev rule installed through polkit |
| Key bindings: any keyboard shortcut (Add → Keyboard shortcut) | xdg GlobalShortcuts portal |
| Actions: volume, backlight, screenshot, play, Aura, mode cycle, one action per mode (custom too, G-Helper's `keybind_profile_N`), screen off, lock, brightness, touchpad, mic, calculator, open app, custom command | `hotkeys.ACTIONS`, `ui.on_hotkey` |
| Backlight: brightness, animation speed, Awake / Boot/Shutdown / Sleep | asusctl aura power |
| Backlight timeout on AC / battery | swayidle (installed through polkit) |
| Always on top, disable Overdrive, USB-C charger in Optimized | — |
| Stop apps using the GPU when switching to Eco | Cardwire blocks only new users, so running ones would keep the dGPU awake: asks first unless the checkbox is set. The desktop keeps it open too, but that does not wake it |
| Boot sound, memory assigned to GPU | Shown only where the firmware has them (asus-armoury `boot_sound`, `apu_mem`) |
| Stop NVIDIA power daemon on battery | asusd `DisableNvidiaPowerdOnBattery` (idea from ROG Control Center) |
| Diagnostics report | One text file for bug reports: versions, packages, services, asusd / firmware attributes, Cardwire, fan curves, settings (own commands hidden), asusd / cardwired journal; host name and home path redacted, no serial numbers (`diagnostics.py`) |

## Planned

### Priority 1: needed before a public release
| # | Feature | How | Seen in |
|---|---|---|---|
| 1 | **Translations** (Russian first) | Qt translations, strings follow G-Helper's resources | G-Helper, g-helper-linux (38 languages) |
| 2 | **Refresh rate outside KDE** | `gdctl` (GNOME 48+), `wlr-randr` (Sway, Hyprland) next to kscreen-doctor | g-helper-linux |
| 3 | **Donations** | GitHub Sponsors with Open Source Collective as fiscal host (Stripe and PayPal receiving are unavailable in Kazakhstan); apply once the repo is public, then set `DONATE_URL` and `.github/FUNDING.yml` | G-Helper |
| 4 | **Release** | GitHub repo, RPM/COPR requiring `asusctl`, `cardwire`, `python3-pyside6`, `python3-evdev`, `swayidle` | — |

### Priority 2: useful
| # | Feature | How | Notes |
|---|---|---|---|
| 6 | **Smart mode** (Cardwire) | dGPU blocked for everything except allowed apps (Steam games, "Launch using Discrete Graphics Card" in KDE) | Stable in Cardwire 0.12; a fifth GPU button or an Eco option |
| 7 | Hint when an app keeps the dGPU awake | Cardwire's `Gpu.Lsof`, e.g. Firefox's video decoder; tray tooltip "dGPU: active (firefox)" | ROG Control Center, g-helper-linux |
| 8 | CPU Boost on/off per mode (Fans → Advanced) | `/sys/devices/system/cpu/cpufreq/boost` | Grant write access in Setup (udev/tmpfiles), no prompt per change |
| 9 | GPU clock limits | `nvidia-smi -lgc / -lmc` (root) | Core/memory **offsets** depend on the driver version (NVML `SetClockOffsets`) |
| 10 | MangoHud toggle as a key action | G-Helper's new FPS overlay; on Linux MangoHud does it | Only a key action, no overlay of our own |

### Priority 3: possible, but risky or of little use
| # | Feature | Why it is low |
|---|---|---|
| 11 | CPU undervolt (Curve Optimizer), CPU temperature limit | Needs `ryzenadj` plus the `ryzen_smu` kernel module (not in Fedora, must be signed for Secure Boot). Bad values cause hangs. |
| 12 | Hibernate after N minutes of sleep | Needs a swap partition; Fedora ships zram only |
| 13 | Temperatures in the tray icon, °F | Small; not in G-Helper |

## Not possible or not applicable

| G-Helper feature | Reason |
|---|---|
| AniMe Matrix, Slash lighting, XG Mobile, ROG Ally controls, mid fan, miniLED / OLED modes, NumberPad, status LED, M4 / Armoury key | Not present on TUF A15 (FA507NV); can be added for models that have them |
| ELMB, keystone sound | No firmware attribute on this model |
| ASUS / NVIDIA services, Modern Standby networking, clamshell, ACPI DEVS test | Windows-only concepts, or KDE already does it |
| Audio effects (noise suppression, EQ), Logitech / ASUS mice (g-helper-linux) | Not about the laptop; separate tools do it better (EasyEffects, Piper / libratbag) |
| Software Fn-lock remapper, deep sleep selector (g-helper-linux) | TUF A15 has a firmware Fn-lock; Rembrandt supports s2idle only |
| Windows power plan per mode | asusd already links the CPU energy preference (EPP) to the profile |
| PCIe ASPM toggle | Would need root on every change for little gain |

## Hardware notes (FA507NV, Fedora 44, KDE Wayland)

- `asusd` 6.5.0 (Terra). PPT limits are stored per profile **and** per power source. asusd's
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
  them too, so supergfxd waited for a logout before Eco. An open file does not wake the dGPU
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
- GPU switching history: up to 0.2.1 (tag `v0.2.1-supergfxd`, branch `supergfxd`) the app used
  supergfxd. Hybrid → Integrated always needed a logout; with `no_logind: true` it killed what
  held `/dev/nvidia0` (`kill -9`), unloaded the driver and removed the device, and once hung in
  the kernel when KWin held the dGPU through NVIDIA's EGL. The workaround (KWin limited to the
  panel's GPU and Mesa's EGL) cost the HDMI port. asus-linux retired supergfxd for Cardwire,
  which only blocks new opens with eBPF/LSM (needs `bpf` in `/sys/kernel/security/lsm`; Fedora
  has it, also with Secure Boot) and leaves the driver loaded. Only stable Cardwire releases are
  used (Terra; 0.12.3 as of 2026-10).
