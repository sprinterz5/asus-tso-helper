"""Performance modes: asusd profiles, EPP, CPU boost, fan curves, power limits (PPT)."""
import os
import re

from .common import ARMOURY, PROFILES, PROFILE_SYSFS, _bus, _bus_get, _read, _read_int, platform_get, platform_set, run


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


# G-Helper's "CPU Boost" per mode. One global switch in cpufreq (amd-pstate, intel_pstate's
# no_turbo is the inverse and not covered); root-owned, so Setup lets the user's group write it.
BOOST = "/sys/devices/system/cpu/cpufreq/boost"
BOOST_TMPFILES = "/etc/tmpfiles.d/shiftray.conf"
LEGACY_BOOST_TMPFILES = "/etc/tmpfiles.d/asus-tso-helper.conf"  # the old name


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


def armoury_choices(name):
    """possible_values of an enumeration firmware attribute (e.g. apu_mem), or None."""
    raw = _read(os.path.join(ARMOURY, name, "possible_values"))
    if not raw:
        return None
    return [v for v in re.split(r"[;,\s]+", raw) if v]


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
