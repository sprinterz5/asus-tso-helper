"""Other tools that change the same things as asusd or Cardwire. Two programs setting the power
mode, the charge limit or the GPU at once give modes that change by themselves, a dGPU that never
sleeps, or one that never comes back.

Each found one is a row in Setup (and a yellow line in the main window). The app only ever stops
a service (`systemctl disable --now`), never removes anything; that is listed in System changes and
Undo starts it again. Tools with their own install (g-helper-linux, envycontrol) get their own
uninstall command shown instead.
"""
import glob
import os

from . import backend as hw
from .i18n import tr

GHELPER_LINUX = "https://github.com/utajum/g-helper-linux#-quick-uninstall-"


class Conflict:
    """service: a systemd unit the app may stop. manual: the command to run instead."""

    def __init__(self, key, title, why, found, service=None, manual=None, link=None):
        self.key, self.title, self.why, self.found = key, title, why, found
        self.service, self.manual, self.link = service, manual, link


def _active(unit):
    return hw.run("systemctl", "is-active", "--quiet", unit, timeout=5)[0]


def _enabled(unit):
    return hw.run("systemctl", "is-enabled", "--quiet", unit, timeout=5)[0]


def _running(unit):
    """Running now or starting at boot: either way it will interfere."""
    return _active(unit) or _enabled(unit)


def _cardwire():
    return _running("cardwired")


def _envycontrol():
    for path in glob.glob("/etc/X11/xorg.conf.d/*.conf") + glob.glob("/etc/modprobe.d/*.conf"):
        try:
            with open(path, errors="replace") as f:
                if "EnvyControl" in f.read(4096):
                    return True
        except OSError:
            pass
    return False


def _ghelper_linux():
    return any(os.path.exists(p) for p in ("/opt/ghelper", "/etc/udev/rules.d/90-ghelper.rules",
                                           "/etc/modprobe.d/ghelper-gpu-block.conf",
                                           "/etc/systemd/system/ghelper-gpu-boot.service"))


def _upower_limit():
    """UPower's own charge limit (GNOME's "Preserve Battery Health", or any desktop through UPower)
    is on and stops at another value than asusd's: each writes its own at boot or on a change."""
    ok, out = hw.run("upower", "-e", timeout=5)
    for path in (out.split() if ok else []):
        if "/battery_" not in path:
            continue
        def prop(name):
            return hw.run("busctl", "--system", "get-property", "org.freedesktop.UPower", path,
                          "org.freedesktop.UPower.Device", name, timeout=5)[1].split()[-1:]
        if prop("ChargeThresholdEnabled") == ["true"]:
            end = prop("ChargeEndThreshold")
            limit = hw.get_charge_limit()
            return not (end and limit and end[0] == str(limit))
    return False


CONFLICTS = [
    Conflict("supergfxd", "supergfxd",
             tr("Switches the GPU too, so it fights Cardwire: the dGPU may stay on or not come back."),
             lambda: _cardwire() and _running("supergfxd"), service="supergfxd"),
    Conflict("tlp", "TLP",
             tr("Sets the power mode, CPU boost and the battery charge limit behind asusd's back, so modes "
             "and the limit change by themselves."),
             lambda: _running("tlp"), service="tlp"),
    Conflict("auto-cpufreq", "auto-cpufreq",
             tr("Changes the CPU's power mode and boost on its own, so the mode you pick does not stick."),
             lambda: _running("auto-cpufreq"), service="auto-cpufreq"),
    Conflict("tuned", "TuneD",
             tr("Applies its own power profiles (CPU power mode, boost) on top of asusd's."),
             lambda: _running("tuned") and not hw.run("rpm", "-q", "tuned-ppd", timeout=5)[0], service="tuned"),
    Conflict("optimus-manager", "optimus-manager",
             tr("Switches the GPU too, so it fights Cardwire."),
             lambda: _cardwire() and _running("optimus-manager"), service="optimus-manager"),
    Conflict("system76-power", "system76-power",
             tr("Switches the GPU and power profiles too."),
             lambda: _running("com.system76.PowerDaemon"), service="com.system76.PowerDaemon"),
    Conflict("upower-limit", tr("The desktop's own charge limit"),
             tr("UPower keeps another charge limit than this app's (on GNOME: Settings → Power → Battery "
                "Charging), so the limit changes after a restart or a change in either."),
             _upower_limit, manual=tr("turn the desktop's charge limit off, or set it to the same value")),
    Conflict("envycontrol", "EnvyControl",
             tr("Its GPU setting (Xorg or modprobe files) can keep the NVIDIA driver from loading, so "
             "Cardwire cannot turn the dGPU on."),
             _envycontrol, manual="sudo envycontrol --reset"),
    Conflict("g-helper-linux", "g-helper-linux",
             tr("Writes the same hardware settings as asusd itself, and its GPU block keeps the NVIDIA driver "
             "from loading. Both installed means two programs changing the same things."),
             _ghelper_linux, link=GHELPER_LINUX,
             manual=tr("its own uninstaller (see its README)")),
]


def found():
    """The conflicts present now (each check is a systemctl call or two; run it off the GUI thread)."""
    out = []
    for c in CONFLICTS:
        try:
            if c.found():
                out.append(c)
        except Exception:  # one broken check must not hide the rest
            pass
    return out


def stop_script(conflicts):
    """Root lines that stop these services (Setup runs them with its other steps)."""
    lines = []
    for c in conflicts:
        if not c.service:
            continue
        if c.key == "supergfxd":  # back to Hybrid first, so the dGPU is on the bus with its driver
            lines.append("command -v supergfxctl >/dev/null && { supergfxctl -g | grep -q Hybrid || "
                         "supergfxctl -m Hybrid; }")
        lines.append(f"systemctl disable --now {c.service}")
    return lines

