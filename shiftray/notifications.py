"""Desktop notifications sent from the app's own D-Bus connection, which stays open.

Plasma drops a notification's buttons when the program that sent it is gone (nothing could answer
them), so a one-off busctl call showed tips without their button. Here the app sends them itself
and gets ActionInvoked back, through dbus-python on GLib, which Qt's event loop drives (as in
shortcuts.py). Without dbus-python the caller falls back to busctl: the tip still shows, without
its button.
"""
from PySide6 import QtCore

try:
    import dbus
    import dbus.mainloop.glib
except ImportError:
    dbus = None

SERVICE = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
IFACE = "org.freedesktop.Notifications"
KEEP = 20  # buttons remembered: the newest tips, also clickable from the notification history


class Notifier(QtCore.QObject):
    def __init__(self, app_name, desktop_entry):
        super().__init__()
        self.app_name, self.desktop_entry = app_name, desktop_entry
        self.actions = {}  # notification id -> what its button does
        self.iface = None
        if dbus is None:
            return
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            self.iface = dbus.Interface(bus.get_object(SERVICE, PATH), IFACE)
            bus.add_signal_receiver(self._invoked, "ActionInvoked", IFACE, path=PATH)
        except dbus.DBusException:
            self.iface = None

    def send(self, icon, title, body, action=None, then=None):
        """A notification, with one button when action is given (a click on it does the same).
        -> False when it could not be sent this way."""
        if self.iface is None:
            return False
        actions = ["run", action, "default", action] if action else []
        try:
            note_id = self.iface.Notify(self.app_name, dbus.UInt32(0), icon, title, body,
                                        dbus.Array(actions, signature="s"),
                                        dbus.Dictionary({"desktop-entry": self.desktop_entry}, signature="sv"),
                                        dbus.Int32(15000))
        except dbus.DBusException:
            return False
        if action and then:
            self.actions[int(note_id)] = then
            for old in list(self.actions)[:-KEEP]:
                del self.actions[old]
        return True

    def _invoked(self, note_id, key):
        if key in ("run", "default"):
            then = self.actions.pop(int(note_id), None)
            if then:
                QtCore.QTimer.singleShot(0, then)  # out of the D-Bus callback
