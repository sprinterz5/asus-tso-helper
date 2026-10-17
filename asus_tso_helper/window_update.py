"""Main window, part: the app's own update (AppImage) and the Updates window.

A mixin: its methods run as MainWindow methods (self is the main window).
"""
from PySide6 import QtCore, QtGui, QtWidgets

from . import selfupdate
from . import updates
from . import widgets as w
from .i18n import tr
from .config import APP, HOMEPAGE, VERSION, quit_app


class UpdateMixin:
    # -- self-update (AppImage) ------------------------------------------------------------
    def on_version_clicked(self):
        if self.can_self_update():
            self.self_update()
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.release_url))

    def can_self_update(self):
        return bool(self.latest_release and selfupdate.possible()
                    and selfupdate.asset_of(self.latest_release))

    def self_update(self):
        """AutoUpdateControl.AutoUpdate: download, swap the AppImage, restart."""
        version = self.latest_release["version"]
        answer = QtWidgets.QMessageBox.question(
            self, tr("Update"), tr("Update to {version} now? The app restarts by itself.", version=version) + "\n\n"
            + tr("What changed: {url}", url=self.release_url))
        if answer != QtWidgets.QMessageBox.Yes:
            return
        asset = selfupdate.asset_of(self.latest_release)
        label = self.version_label
        label.setText(tr("Downloading update ..."))

        def progress(percent):
            self.bridge.done.emit(lambda p: label.setText(tr("Downloading update: {percent}%", percent=p)), percent)

        def job():
            ok, path = selfupdate.download(asset, progress)
            return selfupdate.install(path) if ok else (ok, path)

        def done(result):
            if not result[0]:
                label.setText(tr("Download Update: {version}", version=version))
                QtWidgets.QMessageBox.warning(self, tr("Update"), result[1])
                return
            selfupdate.restart()
            quit_app()
        self.bg(job, then=done)

    def check_app_update(self):
        """AutoUpdateCheck: a newer GitHub release turns the version label into a red
        'Download Update' link, like G-Helper's labelVersion."""
        def done(latest):
            if latest and updates.newer(latest["version"], VERSION):
                self.latest_release = latest
                self.release_url = latest["url"] or HOMEPAGE + "/releases"
                self.version_label.setText(tr("Download Update: {version}", version=latest['version']))
                f = self.version_label.font()
                f.setBold(True)
                f.setUnderline(True)
                self.version_label.setFont(f)
                self.version_label.setStyleSheet(f"color: {w.TURBO.name()};")
                if self.tray and not self.isVisible() and self.cfg.get("update_toast") != latest["version"]:
                    self.cfg["update_toast"] = latest["version"]
                    self.save()
                    self.tray.showMessage(APP, tr("Version {version} is available.", version=latest['version']),
                                          QtGui.QIcon(w.APP_ICON), 8000)
        self.bg(updates.app_latest, then=done)

    def on_updates(self):
        if self.updates is None:
            self.updates = updates.UpdatesWindow(self, VERSION)
        self.updates.show()
        self.updates.raise_()
        self.updates.activateWindow()
        if self.updates.proc is None:  # an install still running keeps its rows and bars
            self.updates.load()
