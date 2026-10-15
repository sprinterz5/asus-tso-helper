"""Hardware access for asus-tso-helper.

Everything that changes the machine goes through the existing daemons' tools
(asusctl -> asusd, supergfxctl -> supergfxd, kscreen-doctor -> KWin), so the app
never needs root. Reads come straight from sysfs where that is cheap and safe.
"""
import glob
import json
import os
import re
import shutil
import subprocess

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


# --- GPU (supergfxd) -------------------------------------------------------------

def gpu_mode():
    ok, out = run("supergfxctl", "-g", timeout=5)
    return out if ok else None


def gpu_supported():
    ok, out = run("supergfxctl", "-s", timeout=5)
    if not ok:
        return []
    return [m.strip() for m in out.strip("[]").split(",") if m.strip()]


def gpu_pending():
    ok, out = run("supergfxctl", "-p", timeout=5)
    return out if ok and "No action" not in out else None


def gpu_pending_mode():
    """Mode supergfxd will switch to after logout / reboot, or None."""
    ok, out = run("supergfxctl", "-P", timeout=5)
    out = out.strip() if ok else ""
    return out if out and out not in ("Unknown", "None") else None


# --- Eco without logout ----------------------------------------------------------------
# supergfxd waits for a logout before Eco because the desktop (KWin) keeps the dGPU open: it
# drives the ports wired to it. With KWin limited to the GPU of the laptop panel and supergfxd's
# "no_logind", Eco switches right away: supergfxd closes what still holds the dGPU, unloads
# the driver and powers it off. The dGPU's own ports (HDMI on many laptops) stop working.
# KWIN_DRM_DEVICES alone is not enough: KWin still opened /dev/nvidia0 through NVIDIA's EGL
# library (glvnd loads every vendor), supergfxd killed it with kill -9, could not unload the
# driver and hung in the kernel (reboot). KWin therefore also runs with Mesa's EGL only, and the
# switch is allowed only once KWin was started with both (root lsof confirmed: nothing left but
# nvidia-powerd, which supergfxd stops itself).
ECO_IN_SESSION_READY = True
SUPERGFX_CONF = "/etc/supergfxd.conf"
KWIN_ENV = os.path.expanduser("~/.config/plasma-workspace/env/asus-tso-helper-igpu.sh")
KWIN_DROPIN = os.path.expanduser("~/.config/systemd/user/plasma-kwin_wayland.service.d/asus-tso-helper.conf")
MESA_EGL = "/usr/share/glvnd/egl_vendor.d/50_mesa.json"
KWIN_DROPIN_TEXT = f"""# asus-tso-helper "Eco without logout": KWin and the Xwayland it starts load only Mesa's EGL,
# so NVIDIA's EGL library does not keep /dev/nvidia0 open inside KWin.
# Turn it off in asus-tso-helper (Extra) or delete this file, then log out once.
[Service]
Environment=__EGL_VENDOR_LIBRARY_FILENAMES={MESA_EGL}
"""
KWIN_ENV_SCRIPT = """# asus-tso-helper "Eco without logout": KWin uses only the GPU that drives the laptop panel,
# so the dGPU can be switched off inside the session. Ports wired to the dGPU do not work.
# Turn it off in asus-tso-helper (Extra) or delete this file, then log out once.
for status in /sys/class/drm/card*-eDP-*/status; do
    [ "$(cat "$status" 2>/dev/null)" = connected ] || continue
    card=${status%/status}
    card=${card##*/}
    export KWIN_DRM_DEVICES="/dev/dri/${card%%-*}"
    break
done
"""


def gfx_no_logind():
    try:
        with open(SUPERGFX_CONF) as f:
            return bool(json.load(f).get("no_logind"))
    except (OSError, ValueError):
        return False


def no_logind_script(on):
    """Root part of Eco without logout: supergfxd stops waiting for a logout."""
    value = "true" if on else "false"
    return (f"sed -i -E 's/(\"no_logind\": *)(true|false)/\\1{value}/' {SUPERGFX_CONF} && "
            "systemctl restart supergfxd")


def eco_in_session_files():
    return os.path.exists(KWIN_ENV) and os.path.exists(KWIN_DROPIN)


def write_kwin_env(on):
    for path, text in ((KWIN_ENV, KWIN_ENV_SCRIPT), (KWIN_DROPIN, KWIN_DROPIN_TEXT)):
        if on:
            if _read(path) == text.strip():
                continue  # unchanged: keep its time, so KWin started since still counts
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
        elif os.path.exists(path):
            os.remove(path)
    run("systemctl", "--user", "daemon-reload", timeout=10)


def _started_at(pid):
    """Start time of a process (epoch seconds); /proc/<pid>/stat is readable even for KWin."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            ticks = int(f.read().rsplit(")", 1)[1].split()[19])
        with open("/proc/stat") as f:
            btime = next(int(line.split()[1]) for line in f if line.startswith("btime "))
    except (OSError, ValueError, IndexError, StopIteration):
        return None
    return btime + ticks / os.sysconf("SC_CLK_TCK")


def kwin_igpu_only():
    """This session's KWin runs limited to the panel's GPU and Mesa's EGL: both files existed
    before KWin started, and the session got KWIN_DRM_DEVICES. KWin's open files cannot be read
    as the user, so this is what makes an in-session Eco switch safe."""
    if not eco_in_session_files():
        return False
    ok, out = run("systemctl", "--user", "show-environment", timeout=5)
    if not (ok and "KWIN_DRM_DEVICES=" in out):
        return False
    written = max(os.path.getmtime(KWIN_ENV), os.path.getmtime(KWIN_DROPIN))
    pids = [p for p in os.listdir("/proc") if p.isdigit() and _read(f"/proc/{p}/comm") == "kwin_wayland"]
    starts = [_started_at(p) for p in pids]
    return bool(starts) and all(t is not None and t > written for t in starts)


def dgpu_ports():
    """External ports wired to the NVIDIA GPU, e.g. ["HDMI"] (empty while it is off)."""
    names = {"HDMI": "HDMI", "DP": "DisplayPort", "DVI": "DVI"}
    ports = []
    for conn in sorted(glob.glob("/sys/class/drm/card*-*")):
        if _read(os.path.join(conn, "device", "device", "vendor")) != "0x10de":  # connector -> card -> PCI
            continue
        kind = os.path.basename(conn).split("-", 1)[1].split("-")[0]
        label = names.get(kind)
        if label and label not in ports:
            ports.append(label)
    return sorted(ports, key=list(names.values()).index)


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


def dgpu_status():
    ok, out = run("supergfxctl", "-S", timeout=5)
    return out if ok else None


def set_gpu_mode(mode):
    return run("supergfxctl", "-m", mode, timeout=60)


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
    if kind == "i":
        return int(value)
    return value


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


# --- screen (KWin via kscreen-doctor) ------------------------------------------

def _internal_output():
    ok, out = run("kscreen-doctor", "-j", timeout=5)
    if not ok:
        return None
    try:
        outputs = json.loads(out[out.index("{"):])["outputs"]
    except (ValueError, KeyError):
        return None
    for o in outputs:
        if o.get("connected") and o.get("enabled") and o["name"].startswith("eDP"):
            return o
    return None


def screen_info():
    """-> (output name, current Hz, sorted list of available Hz at current resolution)."""
    o = _internal_output()
    if not o:
        return None
    modes = {m["id"]: m for m in o["modes"]}
    cur = modes.get(o["currentModeId"])
    if not cur:
        return None
    rates = sorted({round(m["refreshRate"]) for m in o["modes"] if m["size"] == cur["size"]})
    return o["name"], round(cur["refreshRate"]), rates


def set_refresh(hz):
    o = _internal_output()
    if not o:
        return False, "internal display not found"
    modes = {m["id"]: m for m in o["modes"]}
    size = modes[o["currentModeId"]]["size"]
    candidates = [m for m in o["modes"] if m["size"] == size]
    best = min(candidates, key=lambda m: abs(m["refreshRate"] - hz))
    return run("kscreen-doctor", f"output.{o['name']}.mode.{best['id']}")


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
    names = ("asusd", "supergfxd")
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

def dgpu_power():
    """NVIDIA GPU runtime PM state from sysfs, without waking it: "active", "suspended",
    or None when it is not on the bus (Eco)."""
    for vendor in glob.glob("/sys/bus/pci/devices/*/vendor"):
        dev = os.path.dirname(vendor)
        if _read(vendor) == "0x10de" and (_read(os.path.join(dev, "class")) or "").startswith("0x03"):
            return _read(os.path.join(dev, "power", "runtime_status"))
    return None


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
