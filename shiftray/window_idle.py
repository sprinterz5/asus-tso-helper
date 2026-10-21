"""Main window, part: keyboard backlight timeout (swayidle runs `shiftray --kbd-idle off/on`; GNOME,
whose Mutter has no idle protocol for swayidle, tells the app itself through its IdleMonitor).

A mixin: its methods run as MainWindow methods (self is the main window).
"""
import shutil

from PySide6 import QtCore

from . import backend as hw
from . import hotkeys
from .i18n import tr

try:
    import dbus
    import dbus.mainloop.glib
except ImportError:
    dbus = None

MUTTER_IDLE = ("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core")


def gnome_idle_monitor():
    """GNOME's idle monitor, or None (another desktop, or no dbus-python). Its WatchFired signal comes
    through the GLib main loop that notifications.py set up."""
    if dbus is None or not hw.is_gnome():
        return None
    try:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        return dbus.Interface(bus.get_object(*MUTTER_IDLE), MUTTER_IDLE[0]), bus
    except dbus.DBusException:
        return None


def idle_available():
    return bool(shutil.which("swayidle")) or gnome_idle_monitor() is not None


class IdleMixin:
    # -- keyboard backlight timeout (swayidle) -----------------------------------------
    def apply_idle(self):
        """Extra 'Timeout when plugged / on battery': swayidle tells us when the session idles."""
        self.stop_idle()
        timeout = int(self.cfg.get("kbd_timeout_ac" if hw.ac_online() else "kbd_timeout_bat", 0))
        if timeout <= 0 or not self.idle_available:
            return
        gnome = gnome_idle_monitor()
        if gnome:
            self.watch_gnome_idle(*gnome, timeout)
            return
        me = hw.launcher()
        self.idle_proc = QtCore.QProcess(self)
        self.idle_proc.start("swayidle", ["-w", "timeout", str(timeout), f"'{me}' --kbd-idle off",
                                          "resume", f"'{me}' --kbd-idle on"])

    def install_idle(self):
        def done(result):
            self.report(result, tr("Installing swayidle"))
            self.idle_available = idle_available()
            if self.extra:
                self.extra.show_idle_state(self.idle_available)
            self.apply_idle()
        self.bg(hotkeys.install_swayidle, then=done)

    def watch_gnome_idle(self, monitor, bus, timeout):
        """The light goes off after timeout seconds idle and on at the first input, like swayidle's
        timeout / resume."""
        def fired(watch_id):
            if watch_id == self.idle_watch:  # idle: wait for input
                self.bg(hw.kbd_idle, "off")
                self.idle_watch = None
                self.active_watch = int(monitor.AddUserActiveWatch())
            elif watch_id == self.active_watch:  # back: arm the timeout again
                self.bg(hw.kbd_idle, "on")
                self.active_watch = None
                self.idle_watch = int(monitor.AddIdleWatch(dbus.UInt64(timeout * 1000)))
        self.gnome_idle = (monitor, bus.add_signal_receiver(
            lambda watch_id: QtCore.QTimer.singleShot(0, lambda: fired(int(watch_id))),
            "WatchFired", MUTTER_IDLE[0], path=MUTTER_IDLE[1]))
        self.active_watch = None
        self.idle_watch = int(monitor.AddIdleWatch(dbus.UInt64(timeout * 1000)))

    def stop_idle(self):
        gnome = getattr(self, "gnome_idle", None)
        if gnome:
            monitor, match = gnome
            match.remove()
            for watch in (self.idle_watch, self.active_watch):
                if watch is not None:
                    try:
                        monitor.RemoveWatch(dbus.UInt32(watch))
                    except dbus.DBusException:
                        pass
            self.gnome_idle = None
            hw.kbd_idle("on")
        if self.idle_proc:
            self.idle_proc.terminate()
            self.idle_proc.waitForFinished(1000)
            self.idle_proc = None
            hw.kbd_idle("on")  # do not leave the light off if we stop while idle
