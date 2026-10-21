"""Diagnostics report: one text file a user can attach to a bug report.

Versions, hardware, services and the state of asusd / Cardwire. Serial numbers, the host name and
the user's own commands are left out.
"""
import glob
import json
import os
import platform
import re
import shutil

from . import log as applog
from . import system_changes

from . import backend as hw

SERVICES = ("asusd", "cardwired", "supergfxd", "power-profiles-daemon", "tuned", "nvidia-powerd",
            "switcheroo-control")
JOURNAL_UNITS = ("asusd", "cardwired")


def _cmd(*args, timeout=10):
    ok, out = hw.run(*args, timeout=timeout)
    return out.strip() if out else ("" if ok else "(failed)")


def _section(title, lines):
    return [f"## {title}"] + [str(line) for line in lines] + [""]


def _package(name):
    for cmd in (["rpm", "-q", name], ["pacman", "-Q", name], ["dpkg-query", "-W", name]):
        if shutil.which(cmd[0]):
            ok, out = hw.run(*cmd, timeout=5)
            return out.strip() if ok else "not installed"
    return "?"


def _redact(text):
    """Home paths and the host name out of free text."""
    text = text.replace(os.path.expanduser("~"), "~")
    host = platform.node()
    return text.replace(host, "<host>") if host else text


def report(cfg, version):
    out = [f"# Shiftray {version} diagnostics", ""]
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    commit = _cmd("git", "-C", app_dir, "describe", "--always", "--dirty", "--tags") \
        if os.path.isdir(os.path.join(app_dir, ".git")) else ""
    rel = {}
    try:
        with open("/etc/os-release") as f:
            rel = dict(line.strip().split("=", 1) for line in f if "=" in line)
    except OSError:
        pass
    dmi = "/sys/class/dmi/id"
    out += _section("System", [
        f"app: {version} {commit}".rstrip(),
        f"distro: {rel.get('PRETTY_NAME', '?').strip(chr(34))}",
        f"kernel: {platform.release()}",
        f"desktop: {os.environ.get('XDG_CURRENT_DESKTOP', '?')} ({os.environ.get('XDG_SESSION_TYPE', '?')})",
        f"model: {hw._read(f'{dmi}/product_name')} / board {hw._read(f'{dmi}/board_name')}",
        f"bios: {hw._read(f'{dmi}/bios_version')} ({hw._read(f'{dmi}/bios_date')})",
        f"cpu: {hw.cpu_name()}",
        f"lockdown: {hw._read('/sys/kernel/security/lockdown')}",
        f"lsm: {hw._read('/sys/kernel/security/lsm')}",
        f"nvidia driver: {hw._read('/sys/module/nvidia/version') or 'not loaded'}",
        f"libddcutil: {hw.ddcutil_version()}; powerdevil: "
        f"{_cmd('systemctl', '--user', 'show', 'plasma-powerdevil.service', '-p', 'ActiveState,Result', '--value')}"
        .replace("\n", " "),
        f"gnome tray: {hw.gnome_tray()}",
    ])
    out += _section("Packages", [f"{p}: {_package(p)}" for p in
                                 ("asusctl", "cardwire", "supergfxctl", "power-profiles-daemon",
                                  "tuned-ppd", "python3-pyside6", "python3-evdev", "swayidle")])
    out += _section("Services", [f"{s}: {_cmd('systemctl', 'is-active', s)} / {_cmd('systemctl', 'is-enabled', s)}"
                                 for s in SERVICES])

    platform_props = _cmd("busctl", "--system", "introspect", "xyz.ljones.Asusd", "/xyz/ljones",
                          "xyz.ljones.Platform")
    out += _section("asusd platform", [line for line in platform_props.splitlines() if " property " in line])
    attrs = []
    for path in sorted(glob.glob(f"{hw.ARMOURY}/*")):
        value = hw._read(os.path.join(path, "current_value"))
        attrs.append(f"{os.path.basename(path)} = {value if value is not None else hw._read(path)}")
    out += _section("Firmware attributes (asus-armoury)", attrs)
    profile = hw.get_profile()
    out += _section("Fan curves", [f"profile: {profile}",
                                   _cmd("asusctl", "fan-curve", "--mod-profile", profile or "balanced")])

    out += _section("GPU", [f"mode: {hw.gpu_mode()}", f"pending: {hw.gpu_pending()}",
                            f"dGPU power: {hw.dgpu_power(blocked=hw.cardwire_mode() == 'Integrated')}",
                            _cmd("cardwire", "list") if shutil.which("cardwire") else "cardwire: not installed"])
    bat = hw.battery_status() or {}
    health = hw.battery_health()
    out += _section("Battery", [f"charge: {bat.get('percent')}% {bat.get('status')} {bat.get('watts')} W",
                                f"limit: {hw.get_charge_limit()}",
                                f"health: {health:.1f}%" if health else "health: ?",
                                f"cycles: {hw.battery_cycles()}"])

    out += _section("System changes (system_changes.py)", system_changes.report())
    # the app's settings, without the user's own commands
    safe = {k: ("<set>" if k.endswith("_cmd") and v else v) for k, v in cfg.items()}
    out += _section("App settings", [json.dumps(safe, indent=1, sort_keys=True, default=str)])

    out += _section("App log (last lines; start with --debug for every command)", applog.tail(150) or ["(empty)"])
    for unit in JOURNAL_UNITS:
        log = _cmd("journalctl", "-u", unit, "-b", "-n", "400", "-o", "cat", "--no-pager", timeout=15)
        lines = [line for line in log.splitlines() if not re.search(r"dispatch_call|zbus::", line)]
        out += _section(f"journal: {unit} (this boot, last lines)", lines[-40:] or ["(empty or not readable)"])
    return _redact("\n".join(out)) + "\n"
