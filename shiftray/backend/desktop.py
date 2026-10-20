"""Desktop integration: menu entry, KWin script, theme, OSD, notifications, KDE settings."""
import os
import shutil
import sys

from .common import run


def osd(icon, text):
    """The desktop's on-screen display (KDE), like G-Helper's toast; False if there is none."""
    ok, _ = run("gdbus", "call", "--session", "-d", "org.kde.plasmashell", "-o", "/org/kde/osdService",
                "-m", "org.kde.osdService.showText", icon, text, timeout=3)
    return ok


ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
KWIN_PLACE = os.path.join(ASSETS, "kwin", "place.js")
APPIMAGE = os.environ.get("APPIMAGE")  # set by the AppImage runtime: the .AppImage file itself


def launcher():
    """Command that starts this app: the AppImage file, the installed command, or the launcher
    of a source checkout. Inside an AppImage the code lives in a temporary mount instead."""
    if APPIMAGE:
        return APPIMAGE
    return shutil.which("shiftray") or os.path.abspath(sys.argv[0])


def autostart_entry():
    """The autostart .desktop file: the AppImage file or the installed command, so autostart
    survives moving the source checkout."""
    icon = "shiftray" if APPIMAGE else os.path.join(ASSETS, "shiftray.png")
    return ("[Desktop Entry]\nType=Application\nName=Shiftray\n"
            f"Exec=\"{launcher()}\" --minimized\nIcon={icon}\n"
            "X-GNOME-Autostart-enabled=true\n")


DESKTOP_FILE = os.path.expanduser("~/.local/share/applications/shiftray.desktop")
ICON_FILE = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/shiftray.png")


def integrate_desktop():
    """AppImage: a menu entry and icon pointing at the .AppImage file, like an installed app
    (the GlobalShortcuts portal and notifications also need the .desktop file). Rewritten only
    when something changed, e.g. the file was moved."""
    if not APPIMAGE:
        return
    with open(os.path.join(ASSETS, "shiftray.png"), "rb") as f:
        icon = f.read()
    with open(os.path.join(ASSETS, "shiftray.desktop")) as f:
        entry = f.read().replace("@EXEC@", f'"{APPIMAGE}"').replace("@ICON@", "shiftray")
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


def kwin_place_window(keep_above=False):
    """Loads (again, so an updated script counts) the KWin script that opens the main window
    next to the cursor, i.e. the tray icon, and keeps the app's windows above others when asked:
    Wayland ignores Qt's stays-on-top hint, KWin does not. KDE only; elsewhere the desktop places it."""
    def call(*args):
        return run("busctl", "--user", "call", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting",
                   *args, timeout=5)
    name = "shiftray-place"
    with open(KWIN_PLACE) as f:
        script = f"var KEEP_ABOVE = {'true' if keep_above else 'false'};\n" + f.read()
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "shiftray-place.js")
    with open(path, "w") as f:
        f.write(script)
    call("unloadScript", "s", name)
    ok, out = call("loadScript", "ss", path, name)
    return call("start") if ok else (ok, out)


def os_dark():
    """The desktop's light / dark preference: True / False, or None when it says nothing.
    For Qt without the desktop's platform plugin (the AppImage), which reports no scheme. The
    XDG portal answers on KDE, GNOME and most others; GNOME's setting is the fallback."""
    ok, out = run("busctl", "--user", "call", "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                  "org.freedesktop.portal.Settings", "ReadOne", "ss", "org.freedesktop.appearance", "color-scheme",
                  timeout=3)
    if ok and out.split()[-1:] in (["1"], ["2"]):  # "v u 1": 1 dark, 2 light, 0 no preference
        return out.split()[-1] == "1"
    ok, out = run("gsettings", "get", "org.gnome.desktop.interface", "color-scheme", timeout=3)
    if ok and "dark" in out:
        return True
    if ok and "light" in out:
        return False
    return None


def os_accent():
    """The desktop's accent colour as (r, g, b), or None (not set, or no portal)."""
    ok, out = run("busctl", "--user", "call", "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                  "org.freedesktop.portal.Settings", "ReadOne", "ss", "org.freedesktop.appearance", "accent-color",
                  timeout=3)
    try:
        rgb = [float(x) for x in out.split()[-3:]] if ok else []  # "v (ddd) 0.79 0.65 0.97"
    except ValueError:
        return None
    if len(rgb) != 3 or not all(0 <= x <= 1 for x in rgb):  # out of range means "not set"
        return None
    return tuple(round(x * 255) for x in rgb)


POWERDEVIL_SOURCES = ("AC", "Battery")  # LowBattery keeps KDE's power-saver


def stop_kde_power_profiles():
    """KDE's powerdevil sets the power profile on plug / unplug, a moment before the app brings
    back the mode remembered for that source: the mode flickers, and with quick plugging KDE's
    one stays. Sets KDE's choice for AC and battery to "leave unchanged", as G-Helper is the only
    one switching on Windows. -> {source: the value it had} for what was changed (empty if
    nothing), kept in the system changes journal so Undo can put it back."""
    before = {}
    for source in POWERDEVIL_SOURCES:
        key = ("--file", "powerdevilrc", "--group", source, "--group", "Performance", "--key", "PowerProfile")
        ok, value = run("kreadconfig6", *key, "--default", "unset", timeout=5)
        if ok and value and run("kwriteconfig6", *key, "", timeout=5)[0]:  # unset is KDE's default, which may switch
            before[source] = value
    if before:
        _powerdevil_reload()
    return before


def _powerdevil_reload():
    run("busctl", "--user", "call", "org.kde.Solid.PowerManagement", "/org/kde/Solid/PowerManagement",
        "org.kde.Solid.PowerManagement", "reparseConfiguration", timeout=5)


# PowerDevil 6 with libddcutil 2.x crashes at start while Cardwire's Eco hides the NVIDIA GPU: under
# Secure Boot (kernel lockdown) Cardwire blocks the card but leaves its /sys/class/drm entries listed,
# and ddcutil 2.x dereferences the connector it cannot read (rockowitz/ddcutil#641, fixed in 3.0).
# Without PowerDevil KDE has no battery icon, dimming or lid action. Its POWERDEVIL_NO_DDCUTIL skips
# ddcutil; only DDC brightness of external monitors is lost.
POWERDEVIL_DIR = os.path.expanduser("~/.config/systemd/user/plasma-powerdevil.service.d")
POWERDEVIL_DROPIN = os.path.join(POWERDEVIL_DIR, "shiftray-no-ddcutil.conf")
POWERDEVIL_DROPINS = [POWERDEVIL_DROPIN, os.path.join(POWERDEVIL_DIR, "no-ddcutil.conf")]  # + a hand-made one


def ddcutil_version():
    """libddcutil's version from the package manager as (major, minor), or None."""
    for cmd in (("rpm", "-q", "--qf", "%{VERSION}", "libddcutil"), ("pacman", "-Q", "ddcutil"),
                ("dpkg-query", "-W", "-f", "${Version}", "libddcutil5")):
        if shutil.which(cmd[0]):
            ok, out = run(*cmd, timeout=5)
            parts = out.split()[-1].split(".") if ok and out.split() else []
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
    return None


def powerdevil_ddcutil_crash():
    """True when this KDE session is open to the crash: PowerDevil links libddcutil 2.x, Cardwire
    runs, and the kernel is locked down (Secure Boot) so Cardwire blocks cards without unbinding
    them. Also True when PowerDevil already died of a crash. None off KDE."""
    if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        return None
    ok, out = run("systemctl", "--user", "show", "plasma-powerdevil.service", "-p", "Result", "--value", timeout=5)
    if ok and out.strip() == "core-dump":
        return True
    version = ddcutil_version()
    locked = "[none]" not in (_read_lockdown() or "[none]")
    cardwire = run("systemctl", "is-active", "--quiet", "cardwired", timeout=5)[0]
    return bool(version and version < (3, 0) and locked and cardwire)


def _read_lockdown():
    try:
        with open("/sys/kernel/security/lockdown") as f:
            return f.read()
    except OSError:
        return None


def set_powerdevil_ddcutil(skip):
    """skip: PowerDevil starts without ddcutil (a drop-in in the home folder), and is started again."""
    if skip:
        os.makedirs(POWERDEVIL_DIR, exist_ok=True)
        with open(POWERDEVIL_DROPIN, "w") as f:
            f.write("# Shiftray: PowerDevil without ddcutil, which crashes while Cardwire's Eco hides the NVIDIA\n"
                    "# GPU (rockowitz/ddcutil#641, fixed in ddcutil 3.0). Undo in Shiftray: Extra -> Changes.\n"
                    "[Service]\nEnvironment=POWERDEVIL_NO_DDCUTIL=1\n")
    else:
        for path in POWERDEVIL_DROPINS:
            try:
                os.remove(path)
            except OSError:
                pass
    run("systemctl", "--user", "daemon-reload", timeout=10)
    run("systemctl", "--user", "reset-failed", "plasma-powerdevil.service", timeout=5)
    return run("systemctl", "--user", "restart", "plasma-powerdevil.service", timeout=20)


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


def notify(icon, title, body):
    """A desktop notification without buttons."""
    return run("busctl", "--user", "call", "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
               "org.freedesktop.Notifications", "Notify", "susssasa{sv}i", "Shiftray", "0", icon,
               title, body, "0", "0", "15000", timeout=5)


def notify_action(icon, title, body, action):
    """A desktop notification with one button -> its id (for ActionInvoked), or None."""
    ok, out = run("busctl", "--user", "call", "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                  "org.freedesktop.Notifications", "Notify", "susssasa{sv}i", "Shiftray", "0", icon,
                  title, body, "2", "default", action, "0", "15000", timeout=5)
    words = out.split() if ok else []
    return int(words[1]) if len(words) == 2 and words[1].isdigit() else None
