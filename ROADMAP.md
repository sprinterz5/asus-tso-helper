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
| Mode remembered per power source | `performance_<ac>` | Stored in config and in asusd (`PlatformProfileOnAc/OnBattery`); custom modes too. KDE's own per-source power profile is set to "leave unchanged" once, else it switched first and sometimes stayed | `ui.remember_mode`, `ui.on_power_source` |
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
| Translations | Strings.<lang>.resx | `i18n.tr()`, one JSON per language in `translations/` (English text -> translation, missing entries stay English); language from Extra → Language or the system. Russian complete (313 strings). Language is read at start, like G-Helper | `i18n.py` |
| Refresh rate outside KDE | — | GNOME through Mutter's DisplayConfig D-Bus API (works on GNOME 3.26+, so older Ubuntu LTS too; tested on a headless mutter), wlroots through `wlr-randr` (JSON parsing and mode format checked on headless sway and against wlr-randr's source), X11 through `xrandr` | `backend.screen_backend` |
| RPM and AUR packages | — | `make install` puts the app in /usr/share/asus-tso-helper on the system's Python and PySide6, the key rule in /usr/lib/udev/rules.d. RPM spec: Requires PySide6 / evdev / dbus, Recommends asusctl / cardwire (Terra) / swayidle; built and installed in a clean Fedora 44 container, rpmlint clean apart from name spellings. PKGBUILD: depends on asusctl (Arch extra), cardwire optional (AUR); built with makepkg in an Arch container. Arch already ships evdev 2.0 / PySide6 6.12, nothing the app uses changed | `Makefile`, `packaging/rpm`, `packaging/aur` |
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
| 1 | **Donations** | GitHub Sponsors with Open Source Collective as fiscal host (Stripe and PayPal receiving are unavailable in Kazakhstan); apply once the repo is public, then set `DONATE_URL` and `.github/FUNDING.yml` | G-Helper |
| 2 | **Release** | Done: GitHub (tags build the AppImage release), COPR `thesecondone/asus-tso-helper` (`.copr/Makefile`; `copr-cli build-package asus-tso-helper --name asus-tso-helper` after a tag). Left: AUR, once its registration reopens (`packaging/aur` has the 0.4.0 checksum) | — |

### Priority 2: useful
| # | Feature | How | Notes |
|---|---|---|---|
| 6 | **Smart mode** (Cardwire) | dGPU blocked for everything except allowed apps (Steam games, "Launch using Discrete Graphics Card" in KDE) | Stable in Cardwire 0.12; a fifth GPU button or an Eco option |
| 7 | ~~Hint when an app keeps the dGPU awake~~ | **Done in 0.4.0**: tray tooltip "dGPU awake: firefox" from Cardwire's `Gpu.Lsof` | ROG Control Center, g-helper-linux |
| 8 | ~~CPU Boost on/off per mode (Fans → Advanced)~~ | **Done in 0.4.0**: cpufreq `boost`; Setup lets the user's group write it (tmpfiles.d) | Grant write access in Setup (udev/tmpfiles), no prompt per change |
| 9 | GPU clock limits | `nvidia-smi -lgc / -lmc` (root) | Core/memory **offsets** depend on the driver version (NVML `SetClockOffsets`) |
| 10 | ~~MangoHud toggle as a key action~~ | **Done in 0.4.0**: `mangohudctl toggle no_display` | Only a key action, no overlay of our own |

### Priority 3: other laptops, distributions and desktops
Everything here is needed by someone, but cannot be tested on the FA507NV this was built on.
Rule, as in G-Helper: a control appears only when the hardware or the service has it, so nobody
sees buttons that do nothing. Each item needs a tester with that hardware; Extra → Diagnostics
gives them a report to attach.

#### Hardware other ASUS laptops have
| # | Feature | Models | How on Linux | Notes |
|---|---|---|---|---|
| 11 | **All Aura effects** | every model with RGB | asusctl `aura effect`: rainbow-wave, stars, rain, highlight, laser, ripple, comet, flash, pulse; asusd lists what the keyboard supports | The combo now offers G-Helper's four; read the model's list from asusd instead |
| 12 | **Aura zones**: logo, lightbar, lid, rear glow | ROG Strix / Scar / Zephyrus | asusctl `aura power keyboard/logo/lightbar/lid/rear-glow` (awake / boot / sleep / shutdown each) | We only drive `power-tuf` (TUF's single zone); G-Helper shows a column per zone |
| 13 | **Per-key / multizone RGB**, lightbar effects | Strix, Scar | asusd aura zones; LampArray on 2024+ models | g-helper-linux paints software modes (heatmap, battery) |
| 14 | **AniMe Matrix** | Zephyrus G14 / G16 (2020-2024) | asusctl `anime` (asusd rog-anime: built-in animations, image, brightness, on sleep / shutdown) | asusctl's `simulators/` has an AniMe simulator to develop against |
| 15 | **Slash lighting** | Zephyrus G14 / G16 2024+ | asusctl `slash` (modes, brightness, interval, show on battery / sleep) | |
| 16 | **Third (mid) fan** | Strix Scar, some Zephyrus | asusctl `fan-curve --fan mid` | Fans window has CPU and GPU charts only; add a third when asusd reports it |
| 17 | **More power limits**: `ppt_apu_sppt`, `ppt_platform_sppt`, `ppt_fppt`, NVIDIA `nv_tgp` / `nv_base_tgp` | newer ROG (Strix Point, 2024+) | asus-armoury attributes through asusd, same as SPL / sPPT / fPPT | Sliders only for attributes that exist |
| 18 | **MiniLED modes**, panel HD mode, screen auto brightness | Scar, Zephyrus with MiniLED, ProArt | asus-armoury `mini_led_mode`, `panel_hd_mode`, `screen_auto_brightness` | G-Helper: "Toggle MiniLED" key action too |
| 19 | **XG Mobile** (external GPU dock) | Flow X13 / Z13 / X16 | asus-armoury `egpu_enable` / `egpu_connected`, asusctl `xgmled` | Needs the dock to test; g-helper-linux has hints for hangs |
| 20 | **Hard Eco** (`dgpu_disable`) | laptops whose dGPU never reaches D3cold (RTX 20 series, some 2020-21 models) | asus-armoury `dgpu_disable`: the firmware cuts the dGPU's power | G-Helper's Eco does exactly this on Windows. Cardwire's Eco relies on runtime power management, which these GPUs lack. Only with the dGPU released, else the driver hangs |
| 21 | **Intel CPUs**: P/E cores (CPU Cores Configuration), sensors | Intel ROG / TUF / Zenbook | asus-armoury `cores_performance` / `cores_efficiency`; temperature from coretemp (already read) | Intel undervolting is locked on current CPUs |
| 22 | **AMD dGPU** (RX 6800S, 7600S) | G14 2022-23, Strix G15 AMD Advantage | Cardwire supports it; the GPU temperature comes from the dGPU's own amdgpu hwmon | The app assumes an NVIDIA dGPU in places: `nvidia-smi`, `/dev/nvidia*`, the GPU tab |
| 23 | **iGPU-only laptops** (Zenbook, Vivobook) | most non-gaming models | no Cardwire needed; GPU panel hidden | Check the main window has no empty GPU row and Setup asks for nothing GPU-related |
| 24 | **Screenpad** brightness and toggle | Zenbook Pro Duo, Zephyrus Duo | asusctl `backlight` (screenpad) | G-Helper key actions Screenpad up / down |
| 25 | **NumberPad** on the touchpad | Zenbook, Vivobook | the asus-numberpad-driver project; G-Helper's NumberPad key | Separate driver: show it in Setup as optional |
| 26 | **Fn-Lock in software**, camera and status LEDs | models without a firmware Fn-Lock key | kernel `asus_wmi` fnlock, LED class devices | On the FA507NV Fn-Lock is Fn+Esc in firmware |
| 27 | **ROG Ally** (handheld) | Ally, Ally X | asusd's Ally support; G-Helper's Handheld window | A handheld UI of its own; low priority for a laptop app |
| 28 | **Models without fan curve support** | older TUF (FA506, FX506) | asusd reports no curves; g-helper-linux drives the fans manually (experimental) | Hide the charts with a clear note before trying manual control |

#### ASUS peripherals (G-Helper's Mouse / Keyboard / Headset windows)
G-Helper finds ROG mice, keyboards and headsets on USB and the 2.4 GHz dongle and opens a settings
window for each. On Linux the same reports go over `/dev/hidraw*`: no extra library, a Setup step
installs a udev rule that lets the logged-in user open ASUS (vendor 0x0B05) HID devices. The
protocols are readable in G-Helper's source (GPL-3.0, same as this app); credit them per device.
| # | Feature | Devices (G-Helper's list) | Settings | Notes |
|---|---|---|---|---|
| 29 | **Mice** | 31 models: Chakram (Core, X), Gladius II / III, Harpe Ace, Keris (Wireless, II Ace, II Origin), Pugio (II), Spatha X, Strix Impact (II / III, wireless), Strix Carry / Evolve, TUF M3 / M4 / M5, MD200, Balteus / Bulwark docks | DPI (with X / Y and per-DPI colours), polling rate, lift-off, debounce, angle snapping, acceleration, button bindings, profiles, RGB zones and brightness, battery, auto power off, low-battery warning | libratbag / Piper covers only some ROG mice; OpenRGB only lighting |
| 30 | **Keyboards** | Azoth, Claymore II, Falchion, Strix Flare II, Strix Scope II / RX, TUF K3 | lighting modes and per-key RGB, OLED screen (Azoth), key bindings | |
| 31 | **Headsets** | Cetra RGB, Cetra Speed Nova, Clavis, Delta II, Pelta, Strix Go 2.4 | lighting, AI noise cancelling, sidetone, microphone type, EQ, auto power off, battery | |
| 32 | **Aura sync and tray battery** | all of the above | peripheral lighting follows the laptop's Aura; wireless battery level in the tray tooltip | G-Helper's "Sync with laptop" checkboxes |

#### Distributions
| # | Feature | How | Notes |
|---|---|---|---|
| 33 | **Cardwire without BPF LSM** | Ubuntu's kernels ship without `bpf` in the LSM list; Setup adds it to the kernel command line (grub / kernelstub) and asks for a reboot | Otherwise the GPU modes need the supergfxd backend |
| 34 | **supergfxd backend as a fallback** | where Cardwire is missing or cannot run: the code exists on the `supergfxd` branch (tag `v0.2.1-supergfxd`) | Eco there needs a logout, as before |
| 35 | **Ubuntu / Debian packages for asusctl and Cardwire** | Cardwire ships a .deb on its releases; asusctl has no official Debian package | Setup currently only points to asus-linux.org on Debian / Ubuntu |
| 36 | **openSUSE** | asusctl / Cardwire repositories for zypper | Setup installs the basics only |
| 37 | **Immutable systems** (Silverblue, Kinoite, Bazzite, SteamOS) | `rpm-ostree install` instead of dnf, reboot; Bazzite already ships Cardwire | The AppImage itself works there |

#### Desktops
| # | Feature | How | Notes |
|---|---|---|---|
| 38 | ~~Clamshell mode toggle~~ | **Done in 0.4.0**: Extra checkbox for KDE's `InhibitLidActionWhenExternalMonitorPresent` | On by default on both; a checkbox only makes it visible |
| 39 | **GNOME tray** | vanilla GNOME has no tray: needs the AppIndicator extension | Setup should detect it and say so; without a tray the window just stays open |
| 40 | **Toasts, logout prompt, window at the tray outside KDE** | GNOME: notifications via the portal; logout via `gnome-session-quit`; window placement is the compositor's choice | KDE-only today |
| 41 | **Screen off, lock and screenshot key actions outside KDE** | `loginctl lock-session` works everywhere; screen off and screenshot need the desktop's own commands | Today they call KDE tools |

### Priority 4: possible, but risky or of little use
| # | Feature | Why it is low |
|---|---|---|
| 42 | CPU undervolt (Curve Optimizer), CPU temperature limit | Needs `ryzenadj` plus the `ryzen_smu` kernel module (not in Fedora, must be signed for Secure Boot). Bad values cause hangs. |
| 43 | Hibernate after N minutes of sleep | Needs a swap partition (Fedora ships zram only), and with Secure Boot the kernel's lockdown forbids hibernation |
| 44 | Temperatures in the tray icon, °F | Small; not in G-Helper |

## Not possible or not applicable

| G-Helper feature | Reason |
|---|---|
| ELMB, keystone sound | No firmware attribute on this model |
| ASUS / NVIDIA services, Modern Standby networking, ACPI DEVS test | Windows-only concepts (asusd / cardwired take the services' place) |
| Audio effects (noise suppression, EQ), Logitech devices (g-helper-linux) | Not in G-Helper and not ASUS; separate tools do it better (EasyEffects, Solaar, Piper) |
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
