"""Keyboard shortcuts on any keys, through the desktop's GlobalShortcuts portal.

The app never sees the keyboard: it asks the desktop (KDE) for named shortcuts, KDE lets the
user pick the keys in its own dialog, and only tells the app when one is pressed. No root,
no access to typing. Signals arrive through dbus-python on GLib, which Qt's event loop drives.
"""
import secrets

from PySide6 import QtCore

try:
    import dbus
    import dbus.mainloop.glib
except ImportError:
    dbus = None

APP_ID = "asus-tso-helper"
PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.GlobalShortcuts"


class PortalShortcuts(QtCore.QObject):
    activated = QtCore.Signal(str)      # shortcut id
    bound = QtCore.Signal(dict)         # id -> trigger description ("Meta+F1"), after binding
    failed = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.session = None
        self.pending = None
        self.ok = False
        if dbus is None:
            return
        try:
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self.bus = dbus.SessionBus()
            obj = self.bus.get_object(PORTAL, PORTAL_PATH)
            self.iface = dbus.Interface(obj, IFACE)
            try:  # name the app for the portal (xdg-desktop-portal >= 1.19), needs the .desktop file
                dbus.Interface(obj, "org.freedesktop.host.portal.Registry").Register(APP_ID, {})
            except dbus.DBusException:
                pass
            self.bus.add_signal_receiver(self._on_activated, "Activated", IFACE, path=PORTAL_PATH)
            self.bus.add_signal_receiver(self._on_changed, "ShortcutsChanged", IFACE, path=PORTAL_PATH)
            self.ok = True
        except dbus.DBusException:
            self.ok = False

    def _request(self, call, *args, then):
        """Portal methods answer through a Request object's Response signal."""
        token = "tso" + secrets.token_hex(4)
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        path = f"{PORTAL_PATH}/request/{sender}/{token}"
        match = None

        def on_response(code, results):
            match.remove()
            if code == 0:
                then(results)
            else:
                self.failed.emit("cancelled" if code == 1 else "the desktop refused the request")

        match = self.bus.add_signal_receiver(on_response, "Response", "org.freedesktop.portal.Request", path=path)
        try:
            call(*args, {"handle_token": token})
        except dbus.DBusException as err:
            match.remove()
            self.failed.emit(str(err))

    def bind(self, shortcuts):
        """shortcuts: [(id, description[, preferred trigger like "CTRL+SHIFT+F12"])]."""
        if not self.ok:
            self.failed.emit("the GlobalShortcuts portal is not available")
            return
        def entry(sid, desc, trigger=""):
            props = {"description": desc}
            if trigger:
                props["preferred_trigger"] = trigger
            return dbus.Struct((sid, dbus.Dictionary(props, signature="sv")))
        spec = dbus.Array([entry(*s) for s in shortcuts], signature="(sa{sv})")

        def do_bind(_=None):
            self._request(self.iface.BindShortcuts, self.session, spec, "",
                          then=lambda r: self.bound.emit(self._triggers(r)))

        if self.session:
            do_bind()
            return

        def created(results):
            self.session = results["session_handle"]
            do_bind()
        token = "tso" + secrets.token_hex(4)
        self._request(lambda opts: self.iface.CreateSession({**opts, "session_handle_token": token}),
                      then=created)

    def configure(self):
        """Open the desktop's shortcut settings for this app (portal version 2)."""
        if self.ok and self.session:
            try:
                self.iface.ConfigureShortcuts(self.session, "", {})
            except dbus.DBusException as err:
                self.failed.emit(str(err))

    @staticmethod
    def _triggers(results):
        return {str(sid): str(info.get("trigger_description", "")) for sid, info in results.get("shortcuts", [])}

    def _on_activated(self, session, sid, timestamp, options):
        if session == self.session:
            self.activated.emit(str(sid))

    def _on_changed(self, session, shortcuts):
        if session == self.session:
            self.bound.emit({str(sid): str(info.get("trigger_description", "")) for sid, info in shortcuts})
