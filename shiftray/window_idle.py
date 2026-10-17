"""Main window, part: keyboard backlight timeout (swayidle runs `shiftray --kbd-idle off/on`).

A mixin: its methods run as MainWindow methods (self is the main window).
"""
import shutil

from PySide6 import QtCore

from . import backend as hw
from . import hotkeys
from .i18n import tr


class IdleMixin:
    # -- keyboard backlight timeout (swayidle) -----------------------------------------
    def apply_idle(self):
        """Extra 'Timeout when plugged / on battery': swayidle tells us when the session idles."""
        self.stop_idle()
        timeout = int(self.cfg.get("kbd_timeout_ac" if hw.ac_online() else "kbd_timeout_bat", 0))
        if timeout <= 0 or not self.idle_available:
            return
        me = hw.launcher()
        self.idle_proc = QtCore.QProcess(self)
        self.idle_proc.start("swayidle", ["-w", "timeout", str(timeout), f"'{me}' --kbd-idle off",
                                          "resume", f"'{me}' --kbd-idle on"])

    def install_idle(self):
        def done(result):
            self.report(result, tr("Installing swayidle"))
            self.idle_available = bool(shutil.which("swayidle"))
            if self.extra:
                self.extra.show_idle_state(self.idle_available)
            self.apply_idle()
        self.bg(hotkeys.install_swayidle, then=done)

    def stop_idle(self):
        if self.idle_proc:
            self.idle_proc.terminate()
            self.idle_proc.waitForFinished(1000)
            self.idle_proc = None
            hw.kbd_idle("on")  # do not leave the light off if we stop while idle
