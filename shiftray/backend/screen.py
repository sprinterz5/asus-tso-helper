"""Refresh rate and overdrive of the laptop panel (KDE, GNOME, wlroots, X11)."""
import json
import os
import re
import shutil

from .common import ARMOURY, _read, run


# KDE through kscreen-doctor, GNOME through Mutter's DisplayConfig D-Bus API (GNOME 3.26 on, so
# also older Ubuntu LTS), Sway / Hyprland / other wlroots desktops through wlr-randr, X11 through
# xrandr. Each backend gives (output, current mode, modes) with modes as (width, height, Hz, key).
INTERNAL = ("eDP", "LVDS", "DSI")


def screen_backend():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    if "KDE" in desktop and shutil.which("kscreen-doctor"):
        return "kscreen"
    if "GNOME" in desktop:
        return "mutter"
    if wayland and shutil.which("wlr-randr"):
        return "wlr"
    if os.environ.get("DISPLAY") and not wayland and shutil.which("xrandr"):
        return "xrandr"
    return "kscreen" if shutil.which("kscreen-doctor") else None


def _kscreen_panel():
    ok, out = run("kscreen-doctor", "-j", timeout=5)
    if not ok:
        return None
    try:
        outputs = json.loads(out[out.index("{"):])["outputs"]
    except (ValueError, KeyError):
        return None
    for o in outputs:
        if o.get("connected") and o.get("enabled") and o["name"].startswith(INTERNAL):
            modes = [(m["size"]["width"], m["size"]["height"], m["refreshRate"], m["id"]) for m in o["modes"]]
            current = next((m for m in modes if m[3] == o["currentModeId"]), None)
            return o["name"], current, modes
    return None


def _wlr_panel():
    ok, out = run("wlr-randr", "--json", timeout=5)
    try:
        outputs = json.loads(out) if ok else []
    except ValueError:
        return None
    for o in outputs:
        if o.get("enabled") and o.get("name", "").startswith(INTERNAL):
            modes = [(m["width"], m["height"], m["refresh"], f"{m['width']}x{m['height']}@{m['refresh']:.6f}Hz")
                     for m in o.get("modes", [])]
            current = next((mode for mode, m in zip(modes, o.get("modes", [])) if m.get("current")), None)
            return o["name"], current, modes
    return None


def _xrandr_panel():
    ok, out = run("xrandr", "--query", timeout=5)
    name, modes, current = None, [], None
    for line in out.splitlines() if ok else []:
        if not line.startswith(" "):
            name = line.split()[0] if " connected" in line and line.startswith(INTERNAL) else None
            if modes:
                break
            continue
        parts = line.split()
        if name and parts and re.match(r"\d+x\d+", parts[0]):
            w, h = (int(x) for x in re.match(r"(\d+)x(\d+)", parts[0]).groups())
            for rate in parts[1:]:
                hz = float(re.sub(r"[*+]", "", rate) or 0)
                if hz:
                    mode = (w, h, hz, f"{parts[0]} {hz:.2f}")
                    modes.append(mode)
                    if "*" in rate:
                        current = mode
            panel = name
    return (panel, current, modes) if modes else None


MUTTER = ("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig")


def _mutter_state():
    import dbus  # dbus-python: GNOME only, so not needed elsewhere
    bus = dbus.SessionBus()
    iface = dbus.Interface(bus.get_object(*MUTTER), MUTTER[0])
    return iface, iface.GetCurrentState()


def _mutter_panel():
    try:
        _, (_serial, monitors, _logical, _props) = _mutter_state()
    except Exception:  # noqa: BLE001 - no GNOME session bus / no dbus-python
        return None
    for (connector, *_), mode_list, _props in monitors:
        if not str(connector).startswith(INTERNAL):
            continue
        modes, current = [], None
        for mode_id, w, h, hz, _scale, _scales, mprops in mode_list:
            mode = (int(w), int(h), float(hz), str(mode_id))
            modes.append(mode)
            if mprops.get("is-current"):
                current = mode
        return str(connector), current, modes
    return None


def _mutter_apply(connector, mode_id):
    """Same layout, the panel on another mode; method 1 = temporary, as GNOME Settings' preview
    would keep it for the session only, so 2 = persistent like choosing it in Settings."""
    import dbus
    iface, (serial, monitors, logical, _props) = _mutter_state()
    current = {str(m[0][0]): next((str(mm[0]) for mm in m[1] if mm[6].get("is-current")), None) for m in monitors}
    current[connector] = mode_id
    config = []
    for x, y, scale, transform, primary, mons, _lprops in logical:
        config.append(dbus.Struct((x, y, dbus.Double(scale), dbus.UInt32(transform), primary,
                                   [dbus.Struct((str(m[0]), current[str(m[0])], dbus.Dictionary({}, signature="sv")))
                                    for m in mons]), signature=None))
    iface.ApplyMonitorsConfig(dbus.UInt32(serial), dbus.UInt32(2), config, dbus.Dictionary({}, signature="sv"))


def _panel():
    return {"kscreen": _kscreen_panel, "mutter": _mutter_panel, "wlr": _wlr_panel,
            "xrandr": _xrandr_panel}.get(screen_backend(), lambda: None)()


def screen_info():
    """-> (output name, current Hz, sorted list of available Hz at current resolution)."""
    panel = _panel()
    if not panel or not panel[1]:
        return None
    name, cur, modes = panel
    rates = sorted({round(m[2]) for m in modes if m[:2] == cur[:2]})
    return name, round(cur[2]), rates


def set_refresh(hz):
    panel = _panel()
    if not panel or not panel[1]:
        return False, "internal display not found"
    name, cur, modes = panel
    best = min((m for m in modes if m[:2] == cur[:2]), key=lambda m: abs(m[2] - hz))
    backend = screen_backend()
    if backend == "kscreen":
        return run("kscreen-doctor", f"output.{name}.mode.{best[3]}")
    if backend == "wlr":
        return run("wlr-randr", "--output", name, "--mode", best[3])
    if backend == "xrandr":
        size, rate = best[3].split()
        return run("xrandr", "--output", name, "--mode", size, "--rate", rate)
    try:
        _mutter_apply(name, best[3])
    except Exception as err:  # noqa: BLE001 - shown to the user
        return False, str(err)
    return True, ""


def get_overdrive():
    value = _read(os.path.join(ARMOURY, "panel_overdrive", "current_value"))
    return None if value is None else value == "1"


def set_overdrive(on):
    return run("asusctl", "armoury", "set", "panel_overdrive", "1" if on else "0")
