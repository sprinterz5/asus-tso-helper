# Debugging Shiftray

## First: the log

```bash
tail -f ~/.local/state/shiftray/app.log
```

A normal run logs what the user did (mode, GPU, charger, sleep), every failure, and every crash
with its traceback. For **every command** the app runs, with exit code, time and output, start
it with `--debug`. It then also prints to the terminal:

```bash
./bin/shiftray --debug
```

The AppImage takes the same flag. Quit the running copy first (tray → Quit): a second start only
brings the first one's window up.

Users can send **Extra → Diagnostics**: versions, services, asusd and Cardwire state, the system
changes, the last lines of this log and of the asusd / cardwired journals.

## Something is wrong: where to look

| Symptom | Look at | Usually |
|---|---|---|
| A red line "asusd / cardwired is not running" | `systemctl status asusd cardwired` | Service not installed or crashed: Extra → Setup |
| Mode buttons do nothing | log: `run asusctl ...` lines | asusd too old or not running; try `asusctl profile -n` by hand |
| Orange line "Also running: ..." | `conflicts.py`, log: `conflicting tools` | Another tool changes the same settings: Setup stops it |
| Mode changes by itself on plug / unplug | `backend/desktop.py` `stop_kde_power_profiles`, `ui.py` `on_power_source` | Something else switches profiles too: KDE, tuned-ppd, TLP |
| Eco does not save power | tray tooltip "dGPU awake: ..." | A program opened the dGPU before Eco; `backend/gpu.py` `dgpu_users` |
| "Integrated and Smart modes require a offload discrete GPU" | `cardwire list`: no `(*)` under DISCRETE for the NVIDIA GPU | Cardwire started before the NVIDIA driver (first boot after a kernel update, akmods) and decides the GPU type only at start. The app offers to restart it (one password); by hand: `sudo systemctl restart cardwired` |
| GPU mode stuck "Changing ..." | `cardwire list`, `journalctl -u cardwired` | Cardwire version; `backend/gpu.py` `set_gpu_mode` |
| Fn keys do nothing | `ls -l /dev/input/by-path/*` and the udev rule | Rule missing: Setup row "Laptop keys"; `hotkeys.py` |
| Refresh rate buttons greyed | log: `kscreen-doctor` / `wlr-randr` / `xrandr` | Desktop not recognised: `backend/screen.py` `screen_backend` |
| Install Updates stuck | log: `pkcon` lines | A question pkcon asked (stdin is closed, so it fails instead of hanging) |
| Windows open in the wrong place (KDE) | `journalctl --user -b \| grep -i kwin` | KWin script: `assets/kwin/place.js` |
| Something in the window looks wrong | run from source, change, restart | Widgets are in `widgets.py`; colours in `widgets.Theme` |
| A crash | log: `uncaught exception` with traceback | The traceback names the file and line |

## Trying a backend function by hand

Every hardware function can be called without the GUI:

```bash
python3 -c "from shiftray import backend as hw; print(hw.get_profile(), hw.gpu_mode(), hw.screen_info())"
```

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

They need no ASUS laptop: the parsers get the real output of each tool. GitHub runs them on every
push (`.github/workflows/tests.yml`). When a tool changes its output and something breaks, add
that output to a test first, then fix the parser.

## Undoing what the app changed

Extra → System changes lists every change outside the app's own files (`system_changes.py`)
with Undo. The same list is in Diagnostics.
