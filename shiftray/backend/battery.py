"""Battery: charge limit, status, health, history (UPower) and the mode log."""
import glob
import os
import time
import re

from .common import _bus, _cached, _read, _read_int, run


def one_shot_full_charge():
    """asusd charges to 100% once and puts the limit back itself when the charger is unplugged,
    even if this app is not running."""
    return _bus("call", "xyz.ljones.Asusd", "/xyz/ljones", "xyz.ljones.Platform", "OneShotFullCharge")


def _battery():
    return _cached("battery", lambda: next(iter(sorted(glob.glob("/sys/class/power_supply/BAT*"))), None))


def get_charge_limit():
    bat = _battery()
    return _read_int(os.path.join(bat, "charge_control_end_threshold")) if bat else None


# AppConfig.IsChargeLimit6080 in G-Helper: on these models the firmware stops charging only at 60-80% or
# at 100%; anything else charges to full (seen on a TUF A15 FA507NV: 85% kept charging at 95%, 80% stopped)
LIMIT_6080_MODELS = ("GU405", "GU606", "H760", "GA403", "GU605", "GA605", "GA503R")
LIMIT_6080_EXCEPT = ("FX507Z", "FA617", "FA607", "FX607")
LIMIT_6080_STEPS = (60, 80, 100)  # G-Helper also offers 65-75; the three the firmware is known for


def charge_limit_steps(model):
    """The limits the slider offers on this model (Settings.cs: sliderBattery.supportedValues), or None
    when every 5% from 40 to 100 works."""
    tuf = any(t in model for t in ("TUF", "TX Gaming", "TX Air"))
    if any(m in model for m in LIMIT_6080_MODELS) or (tuf and not any(m in model for m in LIMIT_6080_EXCEPT)):
        return LIMIT_6080_STEPS
    return None


def firmware_limit(percent, steps):
    """BatteryControl.SetBatteryChargeLimit: what a wanted limit becomes on a 60/80 model."""
    if not steps:
        return percent
    if percent > 85:
        return 100
    if percent >= 80:
        return 80
    return max(percent, 60)


def set_charge_limit(percent):
    return run("asusctl", "battery", "limit", str(percent))


def _mains():
    for path in glob.glob("/sys/class/power_supply/*/online"):
        if _read(os.path.join(os.path.dirname(path), "type")) == "Mains":
            return path
    return None


def ac_online():
    path = _cached("mains", _mains)
    return _read(path) == "1" if path else None


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


def battery_energy():
    """(Wh now, Wh when full) from sysfs, or None. Batteries that report charge (µAh) instead are
    converted with their voltage."""
    bat = _battery()
    if not bat:
        return None
    now, full = _read_int(os.path.join(bat, "energy_now")), _read_int(os.path.join(bat, "energy_full"))
    if now is None or full is None:
        charge, charge_full = _read_int(os.path.join(bat, "charge_now")), _read_int(os.path.join(bat, "charge_full"))
        volts = _read_int(os.path.join(bat, "voltage_min_design")) or _read_int(os.path.join(bat, "voltage_now"))
        if None in (charge, charge_full, volts):
            return None
        now, full = charge * volts / 1e6, charge_full * volts / 1e6  # µAh x µV -> µWh
    return (now / 1e6, full / 1e6) if full else None


def time_to_limit(limit):
    """Seconds until charging stops at limit %: the energy still missing over the charging power."""
    energy, status = battery_energy(), battery_status()
    if not energy or not status or status["status"] != "Charging" or not status["watts"]:
        return None
    missing = energy[1] * limit / 100 - energy[0]
    return int(missing / status["watts"] * 3600) if missing > 0 else None


def battery_time(limit=100):
    """UPower's smoothed estimate -> ("left" | "to full" | "to limit", seconds), or None. UPower
    counts to 100% even when the charge limit stops earlier: then the time is to the limit."""
    def upower(prop):
        ok, out = run("busctl", "--system", "get-property", "org.freedesktop.UPower",
                      "/org/freedesktop/UPower/devices/DisplayDevice", "org.freedesktop.UPower.Device", prop, timeout=3)
        m = re.match(r"x (\d+)", out) if ok else None
        return int(m.group(1)) if m and int(m.group(1)) > 0 else None
    left = upower("TimeToEmpty")
    if left:
        return "left", left
    if limit < 100:
        secs = time_to_limit(limit)
        return ("to limit", secs) if secs else None
    full = upower("TimeToFull")
    return ("to full", full) if full else None


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


HEALTH_LOG = os.path.expanduser("~/.local/state/shiftray/health.log")


def log_health():
    """Appends "time health%" at most once a day, for the wear over months (Battery window)."""
    cap = battery_capacity()
    if not cap:
        return
    now = int(time.time())
    lines = health_log_lines()
    if lines and now - lines[-1][0] < 86400:
        return
    try:
        os.makedirs(os.path.dirname(HEALTH_LOG), exist_ok=True)
        with open(HEALTH_LOG, "a") as f:
            f.write(f"{now} {cap['health']:.2f}\n")
    except OSError:
        pass


def health_log_lines():
    try:
        with open(HEALTH_LOG) as f:
            return [(int(t), float(h)) for t, h in (l.split() for l in f if len(l.split()) == 2)]
    except (OSError, ValueError):
        return []


def health_change(min_days=14):
    """(change in health points, days) since the first sample, once there are min_days of them; the
    battery's own estimate wobbles a little after each full charge, so the first and the last week's
    averages are compared. None before that."""
    lines = health_log_lines()
    if len(lines) < 2 or lines[-1][0] - lines[0][0] < min_days * 86400:
        return None
    week = 7 * 86400
    first = [h for t, h in lines if t < lines[0][0] + week]
    last = [h for t, h in lines if t > lines[-1][0] - week]
    return sum(last) / len(last) - sum(first) / len(first), (lines[-1][0] - lines[0][0]) // 86400


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
