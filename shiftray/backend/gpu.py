"""GPU modes (Cardwire, MUX through asusd), who uses the dGPU, games, dGPU sensors."""
import glob
import os
import re
import shlex

from ..log import log
from .common import ARMOURY, _bus_get, _read, run
from .profile import set_armoury


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
    def attempt():
        return run("busctl", "--system", "set-property", CARDWIRE, CARDWIRE_PATH, CARDWIRE + ".Mode",
                   "Mode", "u", str(CARDWIRE_MODES.index(mode)), timeout=30)
    ok, out = attempt()
    if not ok and "discrete GPU" in out:
        # Cardwire looks for the GPUs once, at boot. When the NVIDIA driver comes up late (the first
        # boot of a new kernel, while akmods builds it) it misses the dGPU and refuses Eco: it is
        # asked to look again, then the switch is tried once more.
        log.info("Cardwire missed the dGPU at boot: asking it to look again")
        run("busctl", "--system", "call", CARDWIRE, CARDWIRE_PATH, CARDWIRE + ".Debug", "RefreshGpu", timeout=15)
        ok, out = attempt()
    return ok, out


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


def game_name(pid):
    """The game's name when this process is one (Steam, Proton, Wine, Lutris, Heroic all leave
    their marks in its environment), else None. Browsers and launchers probing the GPUs are not."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            env = dict(v.split(b"=", 1) for v in f.read().split(b"\0") if b"=" in v)
        with open(f"/proc/{pid}/comm") as f:
            comm = f.read().strip()
    except (OSError, ValueError):
        return None
    if comm.lower() in ("steam", "steamwebhelper", "pressure-vessel", "reaper", "wineserver", "lutris", "heroic"):
        return None
    app = env.get(b"SteamAppId") or env.get(b"SteamGameId") or b"0"
    if app not in (b"0", b"") or b"STEAM_COMPAT_DATA_PATH" in env or b"WINEPREFIX" in env \
            or comm.lower().endswith(".exe"):
        return comm
    return None


def cardwire_last_blocked():
    """(pid, name) of the newest process Cardwire kept off the dGPU (Eco), or None."""
    ok, out = run("busctl", "--system", "call", CARDWIRE, CARDWIRE_PATH, CARDWIRE + ".Logger",
                  "ProcessBlocked", timeout=5)
    try:
        words = shlex.split(out) if ok else []
    except ValueError:
        return None
    if len(words) < 7:
        return None  # a((tu)usus) N  then per entry: secs nanos pid comm gpu app_id
    pid, comm = words[-4], words[-3]
    return (int(pid), comm) if pid.isdigit() else None


def dgpu_games():
    """Names of the games now running on the dGPU."""
    return sorted({n for n in (game_name(pid) for pid, _ in gpu_apps()[0]) if n})


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
