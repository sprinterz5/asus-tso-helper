# How Shiftray is built

A small Qt (PySide6) app in plain Python. It owns no hardware itself: it is a front end for the
daemons that do the work.

```
 you ──► windows (ui.py, fans.py, extra.py, ...) ──► backend/ ──► asusd        (modes, fans, power limits, Aura, battery limit)
                                                             ├──► cardwired    (GPU modes Eco / Standard)
                                                             ├──► KWin, Mutter, wlr-randr, xrandr (refresh rate)
                                                             ├──► UPower       (battery state and history)
                                                             └──► sysfs reads  (temperatures, fans, battery)
```

The running app needs no root. Root is asked for, with one password prompt each time, only by
Setup, the deep sleep option and Undo, and every such change is listed in `system_changes.py`.

## Where things are

| File | What it does |
|---|---|
| `bin/shiftray` | Launcher for a source checkout (`./bin/shiftray`, add `--debug` for a verbose log) |
| `shiftray/ui.py` | The main window: layout, refresh loops, mode / GPU / screen actions, tray icon, `main()` |
| `shiftray/window_keys.py` | Main window part: key bindings (laptop keys and desktop shortcuts) |
| `shiftray/window_update.py` | Main window part: the app's own update, the Updates window |
| `shiftray/window_idle.py` | Main window part: keyboard backlight timeout (swayidle, or GNOME's IdleMonitor) |
| `shiftray/window_games.py` | Main window part: a running game switches the mode (Extra, opt-in) and the old one comes back |
| `shiftray/config.py` | App name, version, links; the settings file |
| `shiftray/fans.py` | Fans + Power window: fan curves, power limits, CPU boost, EPP |
| `shiftray/extra.py` | Extra window: lighting, other options, language, theme, Setup / Diagnostics / System changes |
| `shiftray/updates.py` | BIOS and driver updates window (PackageKit `pkcon`) |
| `shiftray/battery.py` | Battery window: history chart, health, draw per mode |
| `shiftray/setup.py` | First-run Setup: checks what is missing and installs it behind one password |
| `shiftray/system_changes.py` | **Every change outside the app's own files**: what, why, risk, state, undo |
| `shiftray/conflicts.py` | Other tools that change the same settings (TLP, supergfxd, ...): found, stopped in Setup |
| `shiftray/changes_window.py` | Extra → System changes window (Undo) |
| `shiftray/modes.py` | Custom modes (Turbo+ 30W, ...) on top of asusd's three profiles |
| `shiftray/hotkeys.py` | Reads the "Asus WMI hotkeys" input device (needs the udev rule) |
| `shiftray/shortcuts.py` | Desktop shortcuts through the GlobalShortcuts portal |
| `shiftray/selfupdate.py` | Downloads a new AppImage and checks its SHA-256 |
| `shiftray/diagnostics.py` | Extra → Diagnostics report |
| `shiftray/log.py` | The log file and `--debug` |
| `shiftray/widgets.py` | G-Helper's controls (RButton, slider, ...) and the theme colours |
| `shiftray/i18n.py`, `translations/` | `tr("English")` → the user's language |
| `shiftray/backend/` | **All hardware access**, one module per area (below) |
| `shiftray/assets/` | Icons, the udev rule, the KWin window placement script |
| `tests/` | Unit tests: `python3 -m unittest discover -s tests -t .` |
| `packaging/` | AppImage, RPM (COPR) and AUR builds |

### backend/

Everything else calls it as `hw.<name>` (`from . import backend as hw`); `backend/__init__.py`
only re-exports, so a function can move between modules without touching its callers.

| Module | Area |
|---|---|
| `common.py` | `run()` (every command goes through it and is logged), sysfs reads, asusd's D-Bus properties |
| `profile.py` | Silent / Balanced / Turbo, EPP, CPU boost, fan curves, power limits |
| `gpu.py` | GPU modes (Cardwire, MUX), who keeps the dGPU awake, game detection |
| `screen.py` | Refresh rate and overdrive, per desktop |
| `battery.py` | Charge limit, status, health, UPower history, the mode log |
| `keyboard.py` | Backlight level, Aura, idle timeout |
| `desktop.py` | Menu entry, KWin script, theme and accent, OSD, notifications, KDE settings |
| `system.py` | Model, CPU, services, sensors, deep sleep |

## How the main window works

- **Two timers** in `ui.py`: `refresh_fast` (2 s: mode, battery, charger, sensors) and
  `refresh_slow` (5 s, only while the window is visible: screen, services). Hidden in the tray,
  the app does almost nothing.
- **Signals instead of polling** where the system offers them (connected in `MainWindow.__init__`):
  Cardwire's `PropertiesChanged` (GPU mode) and `ProcessBlockedChanged` (game hints), logind's
  `PrepareForSleep` (restore after sleep), the portal's `SettingChanged` (theme), the notification
  `ActionInvoked` (buttons in notifications).
- **Slow calls run in a thread pool**: `self.bg(fn, *args, then=callback)` runs `fn` off the GUI
  thread and `callback(result)` back on it. A failure in `fn` is logged with its traceback.
- **Settings** live in `~/.config/shiftray/config.json` (`self.cfg`, saved with
  `self.save()`). Hardware settings themselves stay in asusd, so they work with the app closed.

## Adding something

- **A hardware read or write**: a function in the right `backend/` module, using `run()` or
  `_read()`; add its name to `backend/__init__.py`. A test in `tests/test_backend.py` with the
  tool's real output.
- **Anything that changes the system** (root, a package, a system file, another program's
  settings): an entry in `system_changes.py` first, with the reason and how to undo it. Setup and
  Extra → System changes pick it up from there.
- **A visible string**: write it in English inside `tr(...)` and add it to
  `translations/ru.json`; the tests fail when one is missing.
