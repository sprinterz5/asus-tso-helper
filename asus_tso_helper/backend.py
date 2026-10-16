"""Hardware access for asus-tso-helper.

Everything that changes the machine goes through the existing daemons' tools
(asusctl -> asusd, Cardwire (D-Bus) -> cardwired, kscreen-doctor -> KWin), so the app
never needs root. Reads come straight from sysfs where that is cheap and safe.
"""
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

PROFILE_SYSFS = "/sys/firmware/acpi/platform_profile"
ARMOURY = "/sys/class/firmware-attributes/asus-armoury/attributes"
KBD_LED = "/sys/class/leds/asus::kbd_backlight"

# platform_profile name -> asusctl name
PROFILES = {"quiet": "Quiet", "balanced": "Balanced", "performance": "Performance"}
KBD_LEVELS = ["off", "low", "med", "high"]


def _read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def _read_int(path, default=None):
    value = _read(path)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def run(*cmd, timeout=15):
    """Run a command, return (ok, combined output)."""
    if not shutil.which(cmd[0]):
        return False, f"{cmd[0]} not found"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{cmd[0]} timed out"
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0, out


def _hwmon(name):
    for path in glob.glob("/sys/class/hwmon/hwmon*"):
        if _read(os.path.join(path, "name")) == name:
            return path
    return None


# --- performance profile ------------------------------------------------------

def get_profile():
    return _read(PROFILE_SYSFS)


def set_profile(name):
    return run("asusctl", "profile", "set", PROFILES[name])


ASUSD_PROFILE = {"balanced": 0, "performance": 1, "quiet": 2}  # asusd's PlatformProfile numbers


def set_source_profile(name, ac):
    """The profile asusd switches to when the laptop goes onto this power source."""
    prop = "PlatformProfileOnAc" if ac else "PlatformProfileOnBattery"
    return run("busctl", "--system", "set-property", "xyz.ljones.Asusd", "/xyz/ljones",
               "xyz.ljones.Platform", prop, "u", str(ASUSD_PROFILE[name]), timeout=5)


def osd(icon, text):
    """The desktop's on-screen display (KDE), like G-Helper's toast; False if there is none."""
    ok, _ = run("gdbus", "call", "--session", "-d", "org.kde.plasmashell", "-o", "/org/kde/osdService",
                "-m", "org.kde.osdService.showText", icon, text, timeout=3)
    return ok


KWIN_PLACE = os.path.join(os.path.dirname(__file__), "assets", "kwin", "place.js")
APPIMAGE = os.environ.get("APPIMAGE")  # set by the AppImage runtime: the .AppImage file itself


def launcher():
    """Command that starts this app: the AppImage file, the installed command, or the launcher
    of a source checkout. Inside an AppImage the code lives in a temporary mount instead."""
    if APPIMAGE:
        return APPIMAGE
    return shutil.which("asus-tso-helper") or os.path.abspath(sys.argv[0])


DESKTOP_FILE = os.path.expanduser("~/.local/share/applications/asus-tso-helper.desktop")
ICON_FILE = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/asus-tso-helper.png")


def integrate_desktop():
    """AppImage: a menu entry and icon pointing at the .AppImage file, like an installed app
    (the GlobalShortcuts portal and notifications also need the .desktop file). Rewritten only
    when something changed, e.g. the file was moved."""
    if not APPIMAGE:
        return
    src = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(src, "assets", "asus-tso-helper.png"), "rb") as f:
        icon = f.read()
    with open(os.path.join(src, "assets", "asus-tso-helper.desktop")) as f:
        entry = f.read().replace("@EXEC@", f'"{APPIMAGE}"').replace("@ICON@", "asus-tso-helper")
    for path, data in ((ICON_FILE, icon), (DESKTOP_FILE, entry.encode())):
        try:
            with open(path, "rb") as f:
                if f.read() == data:
                    continue
        except OSError:
            pass
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def kwin_place_window():
    """Loads (again, so an updated script counts) the KWin script that opens the main window
    next to the cursor, i.e. the tray icon. KDE only; elsewhere the desktop places it."""
    def call(*args):
        return run("busctl", "--user", "call", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting",
                   *args, timeout=5)
    name = "asus-tso-helper-place"
    call("unloadScript", "s", name)
    ok, out = call("loadScript", "ss", KWIN_PLACE, name)
    return call("start") if ok else (ok, out)


# --- CPU boost -------------------------------------------------------------------
# G-Helper's "CPU Boost" per mode. One global switch in cpufreq (amd-pstate, intel_pstate's
# no_turbo is the inverse and not covered); root-owned, so Setup lets the user's group write it.
BOOST = "/sys/devices/system/cpu/cpufreq/boost"
BOOST_TMPFILES = "/etc/tmpfiles.d/asus-tso-helper.conf"


def cpu_boost():
    """True / False, or None without the switch."""
    value = _read(BOOST)
    return None if value is None else value == "1"


def boost_writable():
    return os.access(BOOST, os.W_OK)


def set_cpu_boost(on):
    try:
        with open(BOOST, "w") as f:
            f.write("1" if on else "0")
    except OSError as err:
        return False, str(err)
    return True, ""


def boost_access_script():
    """Root lines for Setup: the logged-in user's group may write the switch, now and after boot."""
    return (f"g=$(id -gn \"${{PKEXEC_UID:-0}}\") && "
            f"echo \"z {BOOST} 0664 root $g - -\" > {BOOST_TMPFILES} && "
            f"systemd-tmpfiles --create {BOOST_TMPFILES} || exit 1\n")


# --- GPU (Cardwire, MUX through asusd) ----------------------------------------------
# Cardwire, supergfxd's successor from the same people, never unloads the NVIDIA driver: it
# blocks new opens of the dGPU with eBPF/LSM, so Eco and Standard switch at once, without a
# logout, and the dGPU powers down by itself once nothing uses it. Programs that already use it
# keep it until they quit. Ultimate is the firmware MUX (asus-armoury gpu_mux_mode, 0 = the dGPU
# drives the panel), set through asusd and applied on reboot.
CARDWIRE = "org.opengamingcollective.cardwire"
CARDWIRE_PATH = "/org/opengamingcollective/cardwire"
CARDWIRE_MODES = ["Integrated", "Hybrid", "Manual", "Smart"]  # D-Bus Mode values 0..3


def cardwire_mode():
    ok, out = run("busctl", "--system", "get-property", CARDWIRE, CARDWIRE_PATH, CARDWIRE + ".Mode",
                  "Mode", timeout=5)
    m = re.match(r"u (\d+)", out) if ok else None
    return CARDWIRE_MODES[int(m.group(1))] if m and int(m.group(1)) < len(CARDWIRE_MODES) else None


def set_cardwire_mode(mode):
    return run("busctl", "--system", "set-property", CARDWIRE, CARDWIRE_PATH, CARDWIRE + ".Mode",
               "Mode", "u", str(CARDWIRE_MODES.index(mode)), timeout=30)


def has_mux():
    return os.path.exists(os.path.join(ARMOURY, "gpu_mux_mode"))


def mux_dgpu():
    return _read(os.path.join(ARMOURY, "gpu_mux_mode", "current_value")) == "0"


def gpu_mode():
    """"Integrated" (Eco), "Hybrid" (Standard), "AsusMuxDgpu" (Ultimate), Cardwire's
    "Manual" / "Smart", or None when Cardwire is not running."""
    if has_mux() and mux_dgpu():
        return "AsusMuxDgpu"
    return cardwire_mode()


def gpu_supported():
    return ["Integrated", "Hybrid"] + (["AsusMuxDgpu"] if has_mux() else [])


def gpu_pending():
    """"Reboot required" while a MUX change waits for the reboot. asusd 6.5 keeps a MUX write
    queued in memory and writes it to the firmware at shutdown, so the firmware's own
    pending_reboot only shows writes made some other way."""
    if _read(os.path.join(ARMOURY, "pending_reboot")) == "1":
        return "Reboot required"
    if has_mux():
        queued = _bus_get("/xyz/ljones/asus_armoury/gpu_mux_mode", "xyz.ljones.AsusArmoury", "QueuedGpuValue")
        if isinstance(queued, int) and queued >= 0:
            return "Reboot required"
    return None


def set_gpu_mode(mode):
    """Eco / Standard at once through Cardwire. Ultimate and back: the MUX, after a reboot
    (Cardwire is left in Standard for it; the caller sets the wanted mode after the reboot)."""
    if mode == "AsusMuxDgpu":
        set_cardwire_mode("Hybrid")
        ok, out = set_armoury("gpu_mux_mode", 0)
        return ok, "Reboot required" if ok else out
    if has_mux() and mux_dgpu():
        ok, out = set_armoury("gpu_mux_mode", 1)
        return ok, "Reboot required" if ok else out
    return set_cardwire_mode(mode)


# Leftovers of the supergfxd version's "Eco without logout": KWin limited to the panel's GPU
# and Mesa's EGL. With Cardwire they only cost the HDMI port, so they go (next login).
KWIN_ENV = os.path.expanduser("~/.config/plasma-workspace/env/asus-tso-helper-igpu.sh")
KWIN_DROPIN = os.path.expanduser("~/.config/systemd/user/plasma-kwin_wayland.service.d/asus-tso-helper.conf")


def remove_kwin_limits():
    """-> True when something was removed (takes effect at the next login)."""
    removed = False
    for path in (KWIN_ENV, KWIN_DROPIN):
        try:
            os.remove(path)
            removed = True
        except OSError:
            pass
    if removed:
        try:
            os.rmdir(os.path.dirname(KWIN_DROPIN))
        except OSError:
            pass
        run("systemctl", "--user", "daemon-reload", timeout=10)
    return removed


POWERDEVIL_SOURCES = ("AC", "Battery")  # LowBattery keeps KDE's power-saver


def stop_kde_power_profiles():
    """KDE's powerdevil sets the power profile on plug / unplug, a moment before the app brings
    back the mode remembered for that source: the mode flickers, and with quick plugging KDE's
    one stays. Sets KDE's choice for AC and battery to "leave unchanged", as G-Helper is the only
    one switching on Windows. -> True when something was changed."""
    changed = False
    for source in POWERDEVIL_SOURCES:
        key = ("--file", "powerdevilrc", "--group", source, "--group", "Performance", "--key", "PowerProfile")
        ok, value = run("kreadconfig6", *key, "--default", "unset", timeout=5)
        if ok and value:  # unset still means KDE's built-in default, which may switch
            changed = run("kwriteconfig6", *key, "", timeout=5)[0] or changed
    if changed:
        _powerdevil_reload()
    return changed


def _powerdevil_reload():
    run("busctl", "--user", "call", "org.kde.Solid.PowerManagement", "/org/kde/Solid/PowerManagement",
        "org.kde.Solid.PowerManagement", "reparseConfiguration", timeout=5)


def _clamshell_key(source):
    return ("--file", "powerdevilrc", "--group", source, "--group", "SuspendAndShutdown",
            "--key", "InhibitLidActionWhenExternalMonitorPresent")


def clamshell():
    """Clamshell mode: the lid closed with an external display connected keeps the session
    running (KDE's default; GNOME does it always). True / False on KDE, else None."""
    if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper() or not shutil.which("kreadconfig6"):
        return None
    return all(run("kreadconfig6", *_clamshell_key(source), "--default", "true", timeout=5)[1] == "true"
               for source in ("AC", "Battery", "LowBattery"))


def set_clamshell(on):
    for source in ("AC", "Battery", "LowBattery"):
        ok, out = run("kwriteconfig6", *_clamshell_key(source), "--type", "bool", "true" if on else "false", timeout=5)
        if not ok:
            return False, out
    _powerdevil_reload()
    return True, ""


DESKTOP_GPU_USERS = {"kwin_wayland", "kwin_x11", "Xwayland", "Xorg", "plasmashell", "gnome-shell",
                     "mutter", "sddm-greeter", "gdm-x-session"}


def gpu_apps():
    """Own processes holding the NVIDIA GPU open -> (apps that can be closed, desktop parts that can't)."""
    apps, desktop = [], []
    me = os.getuid()
    # /dev/nvidia* plus the NVIDIA card's DRM nodes (KWin opens those, not /dev/nvidia*)
    nodes = ["/dev/nvidia"]
    for vendor in glob.glob("/sys/bus/pci/devices/*/vendor"):
        if _read(vendor) == "0x10de":
            for node in glob.glob(os.path.join(os.path.dirname(vendor), "drm", "*")):
                nodes.append("/dev/dri/" + os.path.basename(node))
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            if os.stat(f"/proc/{pid}").st_uid != me:
                continue
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(f"/proc/{pid}/fd/{fd}")
                if target.startswith(nodes[0]) or target in nodes[1:]:
                    break
            except OSError:
                continue
        else:
            continue
        name = _read(f"/proc/{pid}/comm", "?")
        try:  # "RDD Process" -> "firefox": show the program, not the thread name
            exe = os.path.basename(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            exe = name
        is_desktop = name in DESKTOP_GPU_USERS or exe in DESKTOP_GPU_USERS
        (desktop if is_desktop else apps).append((int(pid), exe if not is_desktop else name))
    return apps, desktop


def armoury_choices(name):
    """possible_values of an enumeration firmware attribute (e.g. apu_mem), or None."""
    raw = _read(os.path.join(ARMOURY, name, "possible_values"))
    if not raw:
        return None
    return [v for v in re.split(r"[;,\s]+", raw) if v]


# --- fans and power limits (asusd) ---------------------------------------------------

def get_fan_curves(profile):
    """-> {"cpu": {"enabled": bool, "points": [(temp, percent) x8]}, "gpu": ...} for a profile.
    Percent is pwm/255 as a float, so a curve survives a read/write round trip unchanged."""
    ok, out = run("asusctl", "fan-curve", "--mod-profile", profile, timeout=5)
    curves = {}
    if not ok:
        return curves
    for m in re.finditer(r"fan:\s*(\w+),\s*pwm:\s*\(([^)]*)\),\s*temp:\s*\(([^)]*)\),\s*enabled:\s*(true|false)", out):
        pwm = [int(x) for x in m.group(2).split(",")]
        temp = [int(x) for x in m.group(3).split(",")]
        curves[m.group(1).lower()] = {"enabled": m.group(4) == "true",
                                      "points": [(t, v * 100 / 255) for t, v in zip(temp, pwm)]}
    return curves


def set_fan_curve(profile, fan, points):
    data = ",".join(f"{int(t)}c:{round(p * 255 / 100)}" for t, p in points)
    return run("asusctl", "fan-curve", "--mod-profile", profile, "--fan", fan, "--data", data)


def enable_fan_curves(profile, on):
    return run("asusctl", "fan-curve", "--mod-profile", profile,
               "--enable-fan-curves", "true" if on else "false")


def enable_fan_curve(profile, fan, on):
    return run("asusctl", "fan-curve", "--mod-profile", profile, "--fan", fan,
               "--enable-fan-curve", "true" if on else "false")


def reset_fan_curves():
    """Factory curve for the active profile."""
    return run("asusctl", "fan-curve", "--default")


def _bus(*args):
    return run("busctl", "--system", *args, timeout=5)


def _bus_get(path, iface, prop):
    ok, out = _bus("get-property", "xyz.ljones.Asusd", path, iface, prop)
    if not ok:
        return None
    kind, _, value = out.partition(" ")
    if kind == "b":
        return value == "true"
    if kind in ("i", "u", "y"):
        return int(value)
    return value


def platform_get(prop):
    """asusd's xyz.ljones.Platform property (charge limit, EPP per profile, ...)."""
    return _bus_get("/xyz/ljones", "xyz.ljones.Platform", prop)


def platform_set(prop, kind, value):
    if kind == "b":
        value = "true" if value else "false"
    return _bus("set-property", "xyz.ljones.Asusd", "/xyz/ljones", "xyz.ljones.Platform", prop, kind, str(value))


# energy_performance_preference per profile, kept and applied by asusd. G-Helper's "Power Mode"
# (the Windows power slider) is the same idea; its four steps match the four EPP values.
EPP_CHOICES = [(4, "Best Battery"), (3, "Better Battery"), (2, "Better Performance"), (1, "Best Performance")]
EPP_PROP = {"quiet": "ProfileQuietEpp", "balanced": "ProfileBalancedEpp", "performance": "ProfilePerformanceEpp"}


def get_profile_epp(profile):
    prop = EPP_PROP.get(profile)
    return platform_get(prop) if prop else None


def set_profile_epp(profile, value):
    """asusd applies an EPP the moment any profile's value is set, so the current profile's
    value is set again afterwards to keep the right one active."""
    ok, out = platform_set("PlatformProfileLinkedEpp", "b", True)
    if ok:
        ok, out = platform_set(EPP_PROP[profile], "u", value)
    current = get_profile()
    if ok and current != profile and current in EPP_PROP:
        platform_set(EPP_PROP[current], "u", get_profile_epp(current))
    return ok, out


def one_shot_full_charge():
    """asusd charges to 100% once and puts the limit back itself when the charger is unplugged,
    even if this app is not running."""
    return _bus("call", "xyz.ljones.Asusd", "/xyz/ljones", "xyz.ljones.Platform", "OneShotFullCharge")


def get_ppt_enabled():
    """asusd 'tuning group' for the current profile and power source."""
    return _bus_get("/xyz/ljones", "xyz.ljones.Platform", "EnablePptGroup")


def set_ppt_enabled(on):
    return _bus("set-property", "xyz.ljones.Asusd", "/xyz/ljones", "xyz.ljones.Platform",
                "EnablePptGroup", "b", "true" if on else "false")


def armoury_range(name):
    """-> (min, max, current) from sysfs, or None if the attribute does not exist."""
    base = os.path.join(ARMOURY, name)
    lo = _read_int(os.path.join(base, "min_value"))
    hi = _read_int(os.path.join(base, "max_value"))
    cur = _read_int(os.path.join(base, "current_value"))
    if lo is None or hi is None:
        return None
    return lo, hi, cur


def get_ppt(name):
    """Value asusd stores for the current profile (what 'Apply Power Limits' will use)."""
    return _bus_get(f"/xyz/ljones/asus_armoury/{name}", "xyz.ljones.AsusArmoury", "CurrentValue")


def set_armoury(name, value):
    """PPT values are stored per profile by asusd; GPU values are queued and then applied."""
    path = f"/xyz/ljones/asus_armoury/{name}"
    ok, out = _bus("set-property", "xyz.ljones.Asusd", path, "xyz.ljones.AsusArmoury",
                   "CurrentValue", "i", str(int(value)))
    if ok and name.startswith("nv_"):
        ok, out = _bus("call", "xyz.ljones.Asusd", path, "xyz.ljones.AsusArmoury", "ApplyQueuedGpuValue")
    return ok, out


def dgpu_name():
    """'NVIDIA GeForce RTX 4060 Laptop GPU' from lspci, without waking the dGPU like nvidia-smi."""
    ok, out = run("lspci", "-d", "10de:", "-mm", timeout=5)
    for line in out.splitlines() if ok else []:
        parts = re.findall(r'"([^"]*)"', line)
        if len(parts) >= 3 and ("VGA" in parts[0] or "3D" in parts[0]):
            m = re.search(r"\[(.+)\]", parts[2])
            name = (m.group(1) if m else parts[2]).replace(" Max-Q / Mobile", " Laptop GPU")
            return name if name.startswith("NVIDIA") else "NVIDIA " + name
    return ""


def cpu_name():
    for line in (_read("/proc/cpuinfo", "") or "").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].replace("with Radeon Graphics", "").strip()
    return ""


# --- screen: refresh rate of the laptop panel ----------------------------------------
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


# --- battery ---------------------------------------------------------------------

def _battery():
    for path in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        return path
    return None


def get_charge_limit():
    bat = _battery()
    return _read_int(os.path.join(bat, "charge_control_end_threshold")) if bat else None


def set_charge_limit(percent):
    return run("asusctl", "battery", "limit", str(percent))


def ac_online():
    for path in glob.glob("/sys/class/power_supply/*/online"):
        if _read(os.path.join(os.path.dirname(path), "type")) == "Mains":
            return _read(path) == "1"
    return None


def battery_health():
    """Full-charge capacity as a percentage of design capacity."""
    bat = _battery()
    if not bat:
        return None
    for full, design in (("charge_full", "charge_full_design"), ("energy_full", "energy_full_design")):
        f = _read_int(os.path.join(bat, full))
        d = _read_int(os.path.join(bat, design))
        if f and d:
            return f * 100 / d
    return None


def battery_status():
    """-> dict(percent, status, watts) or None."""
    bat = _battery()
    if not bat:
        return None
    watts = None
    power = _read_int(os.path.join(bat, "power_now"))
    if power is not None:
        watts = power / 1e6
    else:
        current = _read_int(os.path.join(bat, "current_now"))
        voltage = _read_int(os.path.join(bat, "voltage_now"))
        if current is not None and voltage is not None:
            watts = current * voltage / 1e12
    return {
        "percent": _read_int(os.path.join(bat, "capacity")),
        "status": _read(os.path.join(bat, "status"), "Unknown"),
        "watts": watts,
    }


def battery_time():
    """UPower's smoothed estimate -> ("left" | "to full", seconds), or None."""
    path = "/org/freedesktop/UPower/devices/DisplayDevice"
    for prop, kind in (("TimeToEmpty", "left"), ("TimeToFull", "to full")):
        ok, out = run("busctl", "--system", "get-property", "org.freedesktop.UPower", path,
                      "org.freedesktop.UPower.Device", prop, timeout=3)
        m = re.match(r"x (\d+)", out) if ok else None
        if m and int(m.group(1)) > 0:
            return kind, int(m.group(1))
    return None


def battery_cycles():
    bat = _battery()
    return _read_int(os.path.join(bat, "cycle_count")) if bat else None


# --- keyboard --------------------------------------------------------------------

def get_kbd_level():
    value = _read_int(os.path.join(KBD_LED, "brightness"))
    if value is None:
        return None
    return KBD_LEVELS[max(0, min(value, 3))]


def set_kbd_level(level):
    return run("asusctl", "leds", "set", level)


def set_aura(effect, colour, speed="med"):
    """effect: static | breathe | pulse (ASUS "Strobe") | rainbow-cycle. colour: 'rrggbb'."""
    if effect == "rainbow-cycle":
        return run("asusctl", "aura", "effect", "rainbow-cycle", "--speed", speed)
    if effect == "breathe":
        return run("asusctl", "aura", "effect", "breathe", "--colour", colour,
                   "--colour2", "000000", "--speed", speed)
    if effect == "pulse":
        return run("asusctl", "aura", "effect", "pulse", "-c", colour)
    return run("asusctl", "aura", "effect", "static", "-c", colour)


AURA_SPEEDS = ["low", "med", "high"]


def _aura_config():
    for path in sorted(glob.glob("/etc/asusd/aura_*.ron")):
        text = _read(path)
        if text:
            return text
    return ""


def get_aura_power():
    """Keyboard zone power states from asusd's config -> dict(boot, awake, sleep, shutdown)."""
    text = _aura_config()
    m = re.search(r"zone:\s*Keyboard,(.*?)\)", text, re.S)
    if not m:
        return None
    return {k: v == "true" for k, v in re.findall(r"(boot|awake|sleep|shutdown):\s*(true|false)", m.group(1))}


def set_aura_power(awake, boot, sleep):
    flag = lambda b: "true" if b else "false"
    return run("asusctl", "aura", "power-tuf", "--awake", flag(awake), "--keyboard",
               "--boot", flag(boot), "--sleep", flag(sleep))


def get_aura_speed():
    """Speed of the current aura mode ('low' | 'med' | 'high')."""
    text = _aura_config()
    mode = re.search(r"current_mode:\s*(\w+)", text)
    if not mode:
        return None
    block = re.search(r"\b" + mode.group(1) + r":\s*\((.*?)direction", text, re.S)
    speed = re.search(r"speed:\s*(\w+)", block.group(1)) if block else None
    return speed.group(1).lower() if speed else None


# --- system ----------------------------------------------------------------------

def usb_c_charger():
    """True when power comes in over USB-C (UCSI source online)."""
    for path in glob.glob("/sys/class/power_supply/ucsi-source-psy-*/online"):
        if _read(path) == "1":
            return True
    return False


def services_running():
    names = ("asusd", "cardwired")
    return [n for n in names if run("systemctl", "is-active", "--quiet", n, timeout=5)[0]]


# --- system ----------------------------------------------------------------------

KBD_IDLE_FILE = os.path.expanduser("~/.cache/asus-tso-helper/kbd-level")


def kbd_idle(state):
    """Called by swayidle: 'off' remembers the backlight level and turns it off, 'on' restores it."""
    if state == "off":
        level = get_kbd_level()
        if level and level != "off":
            os.makedirs(os.path.dirname(KBD_IDLE_FILE), exist_ok=True)
            with open(KBD_IDLE_FILE, "w") as f:
                f.write(level)
            set_kbd_level("off")
    elif state == "on":
        level = _read(KBD_IDLE_FILE)
        if level in KBD_LEVELS:
            set_kbd_level(level)
        try:
            os.remove(KBD_IDLE_FILE)
        except OSError:
            pass


def model_name():
    """'ASUS TUF Gaming A15 FA507NV_FA507NV' -> 'ASUS TUF Gaming A15 FA507NV'."""
    name = _read("/sys/class/dmi/id/product_name", "")
    return name.split("_")[0].strip()


# --- sensors ---------------------------------------------------------------------

def dgpu_power(blocked=False):
    """NVIDIA GPU runtime PM state, without waking it: "active", "suspended", or None.
    While Cardwire blocks the dGPU (Eco) it also hides its sysfs files from programs, so then
    (blocked=True, or the files are gone) the state comes from Cardwire."""
    if not blocked:
        for vendor in glob.glob("/sys/bus/pci/devices/*/vendor"):
            dev = os.path.dirname(vendor)
            if _read(vendor) == "0x10de" and (_read(os.path.join(dev, "class")) or "").startswith("0x03"):
                state = _read(os.path.join(dev, "power", "runtime_status"))
                if state:
                    return state
    path = cardwire_dgpu()
    if not path:
        return None
    ok, out = run("busctl", "--system", "call", CARDWIRE, path, CARDWIRE + ".Gpu", "PowerState", timeout=5)
    m = re.search(r'"(D\w+)', out) if ok else None
    return None if not m else "active" if m.group(1) == "D0" else "suspended"


_cardwire_dgpu = []


def cardwire_dgpu():
    """Cardwire's D-Bus object of the offload dGPU (discrete, not the default GPU), or None."""
    if not _cardwire_dgpu:
        for i in range(8):
            path = f"{CARDWIRE_PATH}/Gpu/{i}"
            ok, out = run("busctl", "--system", "call", CARDWIRE, path, CARDWIRE + ".Gpu", "GetDevice", timeout=5)
            if not ok:
                break
            try:
                fields = shlex.split(out)  # ssuubbbbssbs name pci render card default discrete ...
            except ValueError:
                continue
            if len(fields) > 6 and fields[5] == "false" and fields[6] == "true":
                _cardwire_dgpu.append(path)
                break
    return _cardwire_dgpu[0] if _cardwire_dgpu else None


DGPU_SYSTEM_USERS = DESKTOP_GPU_USERS | {"cardwired", "nvidia-powerd", "systemd", "systemd-logind"}


def dgpu_users():
    """Apps keeping the dGPU awake, from Cardwire's Gpu.Lsof (no sysfs or /proc scan of our own,
    so it works in Eco too and does not wake the GPU): sorted names without the desktop's own."""
    path = cardwire_dgpu()
    if not path:
        return []
    ok, out = run("busctl", "--system", "call", CARDWIRE, path, CARDWIRE + ".Gpu", "Lsof", timeout=5)
    try:
        words = shlex.split(out)[1:] if ok else []  # a{sas} N  node M name... node M name...
    except ValueError:
        return []
    names, i = set(), 1
    while i < len(words):
        count = int(words[i + 1]) if words[i + 1].isdigit() else 0
        names.update(words[i + 2:i + 2 + count])
        i += 2 + count
    return sorted(names - DGPU_SYSTEM_USERS)


def sensors(include_dgpu):
    """Cheap sysfs reads, plus nvidia-smi when include_dgpu. Each nvidia-smi run keeps the dGPU
    awake for a few seconds more, so the caller asks rarely (ui.DGPU_TEMP_EVERY)."""
    out = {"cpu": None, "igpu": None, "dgpu": None, "fans": {}}
    k10 = _hwmon("k10temp") or _hwmon("coretemp")
    if k10:
        t = _read_int(os.path.join(k10, "temp1_input"))
        out["cpu"] = t / 1000 if t is not None else None
    amdgpu = _hwmon("amdgpu")
    if amdgpu:
        t = _read_int(os.path.join(amdgpu, "temp1_input"))
        out["igpu"] = t / 1000 if t is not None else None
    asus = _hwmon("asus")
    if asus:
        for n in (1, 2, 3):
            rpm = _read_int(os.path.join(asus, f"fan{n}_input"))
            if rpm is not None:
                label = _read(os.path.join(asus, f"fan{n}_label"), f"fan{n}")
                out["fans"][label.replace("_fan", "")] = rpm
    if include_dgpu:
        ok, val = run("nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits",
                      timeout=3)
        if ok and val.strip().isdigit():
            out["dgpu"] = int(val.strip())
    return out
