"""Extra -> System changes: everything the app changed outside its own files (system_changes.py),
whether it is in place, and Undo for each or for all. What the app should not undo itself
(removing a repository or a package others may depend on) shows the command to do it by hand."""
from PySide6 import QtCore, QtGui, QtWidgets

from . import system_changes as sc
from . import widgets as w
from .i18n import tr
from .widgets import ECO, TURBO, CUSTOM


def button(text, width):
    b = w.RButton(text, secondary=True, radius=2)
    b.setFixedSize(width, 24)
    b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)  # RButton's own is Ignored
    return b

RISK = {sc.LOW: ("low", ECO), sc.MEDIUM: ("medium", CUSTOM), sc.HIGH: ("high", TURBO)}


class ChangesWindow(QtWidgets.QWidget):
    loaded = QtCore.Signal(object)

    def __init__(self, main):
        super().__init__(main, QtCore.Qt.Window)
        self.main = main
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setWindowTitle(tr("System changes"))
        self.resize(560, 480)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)
        root.addWidget(w.Header("settings", tr("System changes"), height=22))
        intro = QtWidgets.QLabel(tr("What this app changed on your system besides its own settings. Undo puts "
                                    "each back; the ones with a password are done together, with one prompt."))
        intro.setWordWrap(True)
        intro.setObjectName("tip")
        root.addWidget(intro)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.list_widget = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(self.list_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setVerticalSpacing(10)
        self.grid.setColumnStretch(0, 1)
        scroll.setWidget(self.list_widget)
        root.addWidget(scroll, 1)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch()
        self.undo_all = button(tr("Undo all"), 110)
        self.undo_all.clicked.connect(lambda: self.undo([c.key for c, on in self.rows if on and c.can_undo]))
        bottom.addWidget(self.undo_all)
        root.addLayout(bottom)
        self.rows = []
        self.loaded.connect(self.fill)

    def load(self):
        def job():
            rows = []
            for c in sc.changes():
                try:
                    rows.append((c, bool(c.applied())))
                except Exception:  # a broken check must not hide the others
                    rows.append((c, False))
            rows.sort(key=lambda r: not r[1])  # what is in place first
            self.loaded.emit(rows)
        self.main.bg(job)

    def fill(self, rows):
        self.rows = rows
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        gray = w.THEME.gray_text.name()
        for i, (c, on) in enumerate(rows):
            risk, colour = RISK[c.risk]
            state = tr("in place") if on else tr("not made")
            text = (f"<b>{c.title}</b> &nbsp;<span style='color:{colour.name()}'>{tr(risk)}</span>"
                    f" &nbsp;<span style='color:{gray}'>· {state}"
                    + (f" · {tr('password')}" if c.root else "") + f"</span><br>"
                    f"<span style='color:{gray}'>{c.why}</span>")
            label = QtWidgets.QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            # wrap to the window's width instead of widening the list past the buttons
            label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
            self.grid.addWidget(label, i, 0)
            if on and c.can_undo:
                b = button(tr("Undo"), 90)
                b.clicked.connect(lambda _=False, k=c.key: self.undo([k]))
                self.grid.addWidget(b, i, 1, QtCore.Qt.AlignTop)
            elif on and c.manual:
                b = button(tr("How to undo"), 90)
                b.clicked.connect(lambda _=False, ch=c: self.show_manual(ch))
                self.grid.addWidget(b, i, 1, QtCore.Qt.AlignTop)
        self.grid.setRowStretch(len(rows), 1)
        self.undo_all.setEnabled(any(on and c.can_undo for c, on in rows))

    def show_manual(self, change):
        command = sc.manual_text(change)
        QtGui.QGuiApplication.clipboard().setText(command)
        QtWidgets.QMessageBox.information(
            self, change.title,
            tr("The app does not undo this itself, because other software may rely on it. To undo it, run "
               "in a terminal (copied to the clipboard):") + f"\n\n{command}")

    def undo(self, keys):
        titles = [c.title for c, _ in self.rows if c.key in keys]
        if not titles:
            return
        text = tr("Undo these changes?") + "\n\n" + "\n".join(f"• {t}" for t in titles)
        if QtWidgets.QMessageBox.question(self, tr("System changes"), text) != QtWidgets.QMessageBox.Yes:
            return
        self.undo_all.setEnabled(False)

        def done(result):
            ok, out = result
            if not ok:
                QtWidgets.QMessageBox.warning(self, tr("System changes"),
                                              tr("Undo did not finish:") + f"\n\n{out[-1500:]}")
            self.load()
            self.main.after_setup()  # services, rules and settings were changed: pick them up
        self.main.bg(sc.undo, keys, then=done)
