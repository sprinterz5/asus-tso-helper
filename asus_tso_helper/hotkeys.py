"""Key Bindings: the ASUS hotkey device ("Asus WMI hotkeys"), like G-Helper's InputDispatcher.

The device carries only the special keys (Fn+F4 Aura, brightness, keyboard light, ...), never
normal typing. It is grabbed so a bound key does only what the user picked; every other key is
re-sent unchanged through a virtual device, so KDE keeps handling brightness, volume and so on.
If the app exits, the grab ends with it and the keys go back to normal.
"""
import os
import select
import subprocess
import threading

from PySide6 import QtCore

try:
    import evdev
    from evdev import ecodes as e
except ImportError:  # python3-evdev missing: Key Bindings stay off
    evdev = None

DEVICE_NAME = "Asus WMI hotkeys"
RULE_NAME = "70-asus-tso-helper.rules"
RULE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", RULE_NAME)

# key name in config -> (label, WMI scancode); Extra.cs labels and InputDispatcher codes
KEYS = {
    "fnf4": ("FN+F4", 0xB3),   # Aura
    "fnc": ("FN+C", 0x9E),
    "fnv": ("FN+V", 0x8A),
    "fne": ("FN+Enter", 0xB5),  # numpad enter on TUF
}
SCAN_TO_KEY = {scan: name for name, (_, scan) in KEYS.items()}
DEFAULT_ACTION = {"fnf4": "aura", "fne": "calculator"}  # InputDispatcher.KeyProcess defaults

# Extra.SetKeyCombo actions that have a Linux equivalent (G-Helper's order)
ACTIONS = [
    ("", "--------------"),
    ("volume_down", "Volume Down"),
    ("volume_up", "Volume Up"),
    ("backlight_down", "Keyboard Backlight Down"),
    ("backlight_up", "Keyboard Backlight Up"),
    ("mute", "Volume Mute"),
    ("screenshot", "Screenshot"),
    ("play", "Play / Pause"),
    ("aura", "Toggle Aura"),
    ("performance", "Performance Mode"),
    ("screen", "Toggle Screen"),
    ("lock", "Lock Screen"),
    ("brightness_down", "Brightness Down"),
    ("brightness_up", "Brightness Up"),
    ("touchpad", "Toggle Touchpad"),
    ("micmute", "Mute Mic"),
    ("calculator", "Calculator"),
    ("ghelper", "Open asus-tso-helper"),
    ("custom", "Custom"),
]

# actions done by re-sending a standard key, so KDE shows its usual on-screen display
KEY_ACTIONS = {} if evdev is None else {
    "volume_down": e.KEY_VOLUMEDOWN, "volume_up": e.KEY_VOLUMEUP, "mute": e.KEY_MUTE,
    "backlight_down": e.KEY_KBDILLUMDOWN, "backlight_up": e.KEY_KBDILLUMUP,
    "screenshot": e.KEY_SYSRQ, "play": e.KEY_PLAYPAUSE,
    "brightness_down": e.KEY_BRIGHTNESSDOWN, "brightness_up": e.KEY_BRIGHTNESSUP,
    "touchpad": e.KEY_TOUCHPAD_TOGGLE, "micmute": e.KEY_MICMUTE, "calculator": e.KEY_CALC,
}


def find_device():
    if evdev is None:
        return None
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        if dev.name == DEVICE_NAME:
            return dev
        dev.close()
    return None


def device_present():
    """True if the hotkey device exists, whether or not we may open it."""
    try:
        with open("/proc/bus/input/devices") as f:
            return f'Name="{DEVICE_NAME}"' in f.read()
    except OSError:
        return False


SWAYIDLE_INSTALL = ("command -v swayidle >/dev/null || "
                    "{ command -v dnf >/dev/null && dnf install -y swayidle; } || "
                    "{ command -v pacman >/dev/null && pacman -S --noconfirm swayidle; } || "
                    "{ command -v apt-get >/dev/null && apt-get install -y swayidle; }")


def run_as_root(script):
    """One polkit password prompt for a whole setup step."""
    try:
        p = subprocess.run(["pkexec", "sh", "-c", script], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as err:
        return False, str(err)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def install_swayidle():
    return run_as_root(SWAYIDLE_INSTALL)


def rule_script():
    """Root shell lines that write the udev rule. Its text goes inline: an AppImage's files sit
    in a FUSE mount that root cannot read."""
    with open(RULE_SRC) as f:
        text = f.read()
    if not text.endswith("\n"):
        text += "\n"
    return (f"cat > /etc/udev/rules.d/{RULE_NAME} <<'ASUS_TSO_RULE' && chmod 644 /etc/udev/rules.d/{RULE_NAME} && "
            f"udevadm control --reload && udevadm trigger -s input || exit 1\n{text}ASUS_TSO_RULE\n")


def install_rule():
    """Let the logged-in user read the hotkey device; installs swayidle in the same prompt."""
    return run_as_root(rule_script() + "{ " + SWAYIDLE_INSTALL + "; } || true\n")


# friendlier names for keys the user adds themselves (evdev name otherwise)
KEY_LABELS = {
    "KEY_KBDILLUMUP": "Keyboard light up", "KEY_KBDILLUMDOWN": "Keyboard light down",
    "KEY_BRIGHTNESSUP": "Brightness up", "KEY_BRIGHTNESSDOWN": "Brightness down",
    "KEY_TOUCHPAD_TOGGLE": "Touchpad key", "KEY_MICMUTE": "Mic mute key", "KEY_RFKILL": "Airplane key",
    "KEY_PROG1": "Fn key PROG1", "KEY_PROG2": "Fn key PROG2", "KEY_PROG3": "Armoury key",
    "KEY_PROG4": "Aura key", "KEY_CALC": "Calculator key", "KEY_CAMERA": "Camera key",
    "KEY_SWITCHVIDEOMODE": "Display key", "KEY_SELECTIVE_SCREENSHOT": "Screenshot key",
}


def key_label(code, scan):
    name = e.KEY.get(code, f"0x{scan:02X}") if evdev else f"0x{scan:02X}"
    if isinstance(name, list):
        name = name[0]
    return KEY_LABELS.get(name, name.replace("KEY_", "Fn key ").replace("_", " ").title())


class Hotkeys(QtCore.QObject):
    """Runs in a thread; emits `action(name, key)` on the GUI thread for keys that are bound."""

    action = QtCore.Signal(str, str)
    seen = QtCore.Signal(str)
    captured = QtCore.Signal(int, str)  # scancode, label: the next key press while capturing
    state = QtCore.Signal(str)  # "running" | "no-access" | "no-device" | "no-evdev"

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.thread = None
        self.out = None
        self.spare = None
        self.capturing = False
        self.stop_flag = threading.Event()

    def binding(self, key):
        """Bound action; "none" means the user picked "nothing" and the key passes through."""
        value = self.cfg.get(f"key_{key}")
        if value == "none":
            return ""
        return value or DEFAULT_ACTION.get(key, "")

    def scan_map(self):
        """Built-in G-Helper keys plus the laptop keys the user added (Add -> Laptop key)."""
        mapping = dict(SCAN_TO_KEY)
        for name, info in self.cfg.get("custom_keys", {}).items():
            mapping[info["scan"]] = name
        return mapping

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        if evdev is None:
            self.state.emit("no-evdev")
            return
        if not device_present():
            self.state.emit("no-device")
            return
        dev = find_device()
        if dev is None:
            self.state.emit("no-access")
            return
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self.run, args=(dev,), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    def run(self, dev):
        try:
            out = evdev.UInput.from_device(dev, name="asus-tso-helper hotkeys")
            dev.grab()
        except OSError:
            self.state.emit("no-access")
            dev.close()
            return
        self.out = out
        self.state.emit("running")
        scan = None
        try:
            while not self.stop_flag.is_set():
                ready, _, _ = select.select([dev.fd], [], [], 0.5)
                if not ready:
                    continue
                mapping = self.scan_map()
                for ev in dev.read():
                    if ev.type == e.EV_MSC and ev.code == e.MSC_SCAN:
                        scan = ev.value
                        continue
                    if self.capturing and ev.type == e.EV_KEY and scan is not None:
                        if ev.value == 1:
                            self.capturing = False
                            self.captured.emit(scan, key_label(ev.code, scan))
                        continue  # the key pressed to capture does nothing else
                    key = mapping.get(scan) if ev.type == e.EV_KEY else None
                    if key and ev.value == 1:
                        self.seen.emit(key)
                    if key and self.binding(key):
                        if ev.value == 1:
                            self.press(self.binding(key), key)
                        continue  # swallow the original key: it is bound
                    if ev.type == e.EV_KEY:
                        scan = None
                    out.write_event(ev)
        except OSError:
            pass  # device gone (suspend, unplug): the grab is released with it
        finally:
            self.out = None
            try:
                dev.ungrab()
            except OSError:
                pass
            dev.close()
            out.close()

    def send_key(self, code):
        """Tap a standard key through a virtual device; False if it cannot send that key.
        The grabbed device's twin is used when it has the key, else a small spare keyboard."""
        out = self.out
        if out is None or code not in out.capabilities().get(e.EV_KEY, []):
            if evdev is None:
                return False
            if self.spare is None:
                try:
                    self.spare = evdev.UInput({e.EV_KEY: sorted(set(KEY_ACTIONS.values()))},
                                              name="asus-tso-helper keys")
                except OSError:
                    return False
            out = self.spare
            if code not in out.capabilities().get(e.EV_KEY, []):
                return False
        out.write(e.EV_KEY, code, 1)
        out.syn()
        out.write(e.EV_KEY, code, 0)
        out.syn()
        return True

    def press(self, action, key):
        code = KEY_ACTIONS.get(action)
        if code is not None and self.send_key(code):
            return
        self.action.emit(action, key)


def to_portal_trigger(sequence):
    """Qt "Ctrl+Shift+F12" -> XDG shortcuts "CTRL+SHIFT+F12" (Meta is LOGO)."""
    names = {"ctrl": "CTRL", "shift": "SHIFT", "alt": "ALT", "meta": "LOGO"}
    return "+".join(names.get(part.lower(), part) for part in sequence.split("+"))
