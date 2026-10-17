"""Battery: charge limit, status, health, history (UPower) and the mode log."""
import glob
import os
import time
import re

from .common import _bus, _read, _read_int, run


def one_shot_full_charge():
    """asusd charges to 100% once and puts the limit back itself when the charger is unplugged,
    even if this app is not running."""
    return _bus("call", "xyz.ljones.Asusd", "/xyz/ljones", "xyz.ljones.Platform", "OneShotFullCharge")


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


def usb_c_charger():
    """True when power comes in over USB-C (UCSI source online)."""
    for path in glob.glob("/sys/class/power_supply/ucsi-source-psy-*/online"):
        if _read(path) == "1":
            return True
    return False


MODE_LOG = os.path.expanduser("~/.local/state/shiftray/modes.log")


def battery_history(kind, seconds, points=400):
    """UPower's own record: [(unix time, value, state)] oldest first, kind "charge" (%) or
    "rate" (W). state: 1 charging, 2 discharging, 4 full; 0 marks a gap (asleep, off)."""
    path = "/org/freedesktop/UPower/devices/" + os.path.basename(_battery() or "BAT0").replace("BAT", "battery_BAT")
    ok, out = run("busctl", "--system", "call", "org.freedesktop.UPower", path, "org.freedesktop.UPower.Device",
                  "GetHistory", "suu", kind, str(seconds), str(points), timeout=5)
    words = out.split() if ok else []
    rows = []
    for i in range(2, len(words) - 2, 3):
        try:
            rows.append((int(words[i]), float(words[i + 1]), int(words[i + 2])))
        except ValueError:
            pass
    return sorted(rows)


def battery_capacity():
    """-> dict(full, design Wh, health %, cycles or None), or None."""
    bat = _battery()
    if not bat:
        return None
    full, design = _read_int(os.path.join(bat, "energy_full")), _read_int(os.path.join(bat, "energy_full_design"))
    if not full or not design:  # batteries that count in µAh: × the design voltage
        volts = (_read_int(os.path.join(bat, "voltage_min_design")) or 0) / 1e6
        full = (_read_int(os.path.join(bat, "charge_full")) or 0) * volts
        design = (_read_int(os.path.join(bat, "charge_full_design")) or 0) * volts
    if not full or not design:
        return None
    cycles = _read_int(os.path.join(bat, "cycle_count"))
    return {"full": full / 1e6, "design": design / 1e6, "health": 100 * full / design, "cycles": cycles or None}


def log_mode(key):
    """Appends "time mode" when the mode changes; a week is kept."""
    now = int(time.time())
    try:
        os.makedirs(os.path.dirname(MODE_LOG), exist_ok=True)
        lines = mode_log_lines()
        if lines and lines[-1][1] == key:
            return
        lines = [l for l in lines if l[0] > now - 8 * 86400] + [(now, key)]
        with open(MODE_LOG, "w") as f:
            f.writelines(f"{t} {k}\n" for t, k in lines)
    except OSError:
        pass


def mode_log_lines():
    try:
        with open(MODE_LOG) as f:
            return [(int(t), k) for t, k in (l.split(None, 1) for l in f.read().split("\n") if " " in l)]
    except (OSError, ValueError):
        return []


def watts_per_mode(seconds):
    """{mode: (average discharge W, hours on battery)} from UPower's rate history and the mode log."""
    log = mode_log_lines()
    if not log:
        return {}
    rows = battery_history("rate", seconds, 2000)
    sums = {}
    for (t, watts, state), nxt in zip(rows, rows[1:] + [None]):
        if state != 2 or watts <= 0:
            continue
        span = min((nxt[0] if nxt else time.time()) - t, 600)  # a gap is sleep, not use
        mode = next((k for lt, k in reversed(log) if lt <= t), None)
        if mode:
            e, s = sums.get(mode, (0.0, 0.0))
            sums[mode] = (e + watts * span, s + span)
    return {m: (e / s, s / 3600) for m, (e, s) in sums.items() if s >= 300}
