"""'Extra Settings' window: the G-Helper Extra form (app/Extra.Designer.cs, app/Extra.cs).

Only the parts that have a Linux backend on this hardware are shown, the same way G-Helper
hides sections a model does not support. Backlight timeout and hibernation are not ported yet.
"""
from PySide6 import QtCore, QtGui, QtWidgets

from . import backend as hw
from . import hotkeys
from . import widgets as w
from .widgets import ECO, STANDARD

SPEEDS = [("low", "Slow"), ("med", "Normal"), ("high", "Fast")]


class HeaderPanel(QtWidgets.QWidget):
    """panel*Header: ButtonSecond strip, Padding(11, 5, 11, 5), icon at 21, bold title at 56."""

    def __init__(self, icon_name, title):
        super().__init__()
        self.icon_name = icon_name
        self.setObjectName("header")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setFixedHeight(25)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(28, 0, 6, 0)
        lay.setSpacing(0)
        self.title = QtWidgets.QLabel(title)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        lay.addWidget(self.title)
        lay.addStretch()
        self.right = lay

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), w.THEME.button_second)
        p.drawPixmap(QtCore.QPointF(10, (self.height() - 16) / 2), w.icon(self.icon_name))


def check(text, left=8):
    c = QtWidgets.QCheckBox(text)
    c.setFixedHeight(21)
    c.setContentsMargins(left, 0, 0, 0)
    c.setStyleSheet(f"QCheckBox {{ padding-left: {left}px; }}")
    return c


class ExtraWindow(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__(main, QtCore.Qt.Window)
        self.main = main
        self.cfg = main.cfg
        self.setWindowTitle("Extra Settings")
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setFixedWidth(506)  # ClientSize 1013 at 192 DPI
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(7, 7, 8, 8)  # Padding(15)
        root.setSpacing(0)

        # Key Bindings
        self.bind_head = HeaderPanel("keyboard", "Key Bindings")
        add_key = w.RButton("Add", secondary=True, radius=2)
        add_key.setFixedSize(60, 20)
        add_key.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        add_key.clicked.connect(lambda: self.on_add_key(add_key))
        self.bind_head.right.addWidget(add_key)
        self.bind_head.right.addSpacing(4)
        self.add_key = add_key
        reset_keys = w.RButton("Reset", secondary=True, radius=2)
        reset_keys.setFixedSize(75, 20)
        reset_keys.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        reset_keys.clicked.connect(self.on_reset_bindings)
        self.bind_head.right.addWidget(reset_keys)
        self.bind_head.right.addSpacing(6)
        help_icon = QtWidgets.QLabel()  # pictureHelp
        help_icon.setPixmap(w.icon("circle-help"))
        help_icon.setCursor(QtCore.Qt.PointingHandCursor)
        help_icon.setToolTip("How Key Bindings work")
        help_icon.mousePressEvent = lambda _: QtGui.QDesktopServices.openUrl(
            QtCore.QUrl("https://github.com/sprinterz5/asus-tso-helper#key-bindings"))
        self.bind_head.right.addWidget(help_icon)
        self.help_icon = help_icon
        root.addWidget(self.bind_head)
        self.bindings = QtWidgets.QWidget()
        self.bind_grid = QtWidgets.QGridLayout(self.bindings)
        self.bind_grid.setContentsMargins(8, 4, 6, 4)
        self.bind_grid.setHorizontalSpacing(6)
        self.bind_grid.setVerticalSpacing(4)
        self.bind_grid.setColumnStretch(0, 1)
        self.bind_grid.setColumnStretch(1, 2)
        self.bind_grid.setColumnStretch(2, 2)
        self.bind_grid.setColumnStretch(3, 0)
        root.addWidget(self.bindings)
        self.bind_rows = {}

        # Laptop Backlight
        head = HeaderPanel("sunrise", "Laptop Backlight")
        self.brightness = w.Slider(0, 3, 1)
        self.brightness.setFixedWidth(250)
        self.brightness.released.connect(self.on_brightness)
        head.right.addWidget(self.brightness)
        root.addWidget(head)

        body = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(body)
        bl.setContentsMargins(2, 2, 0, 2)
        bl.setSpacing(0)
        self.awake = check("Awake")
        self.boot = check("Boot/Shutdown")
        self.sleep = check("Sleep")
        for c in (self.awake, self.boot, self.sleep):
            c.toggled.connect(self.on_power)
            bl.addWidget(c)
        speed_row = QtWidgets.QHBoxLayout()
        speed_row.setContentsMargins(6, 6, 6, 2)
        speed_label = QtWidgets.QLabel("Animation Speed")
        self.speed = w.RComboBox()
        self.speed.setFixedWidth(146)
        self.speed.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        for key, label in SPEEDS:
            self.speed.addItem(label, key)
        self.speed.activated.connect(self.on_speed)
        speed_row.addWidget(speed_label)
        speed_row.addStretch()
        speed_row.addWidget(self.speed)
        bl.addLayout(speed_row)

        # Extra.panelBacklightExtra: "Timeout when plugged / on battery"
        timeout_row = QtWidgets.QHBoxLayout()
        timeout_row.setContentsMargins(6, 4, 6, 2)
        self.timeout_label = QtWidgets.QLabel("Backlight timeout plugged / on battery")
        timeout_row.addWidget(self.timeout_label)
        timeout_row.addStretch()
        self.timeout_ac = QtWidgets.QSpinBox()
        self.timeout_bat = QtWidgets.QSpinBox()
        for box, key in ((self.timeout_ac, "kbd_timeout_ac"), (self.timeout_bat, "kbd_timeout_bat")):
            box.setRange(0, 3600)
            box.setSuffix(" sec")
            box.setToolTip("0 = backlight always on")
            box.setFixedSize(70, 20)
            box.setValue(int(self.cfg.get(key, 0)))
            box.editingFinished.connect(self.on_timeout)
            timeout_row.addWidget(box)
        bl.addLayout(timeout_row)
        note_row = QtWidgets.QHBoxLayout()
        note_row.setContentsMargins(6, 0, 6, 0)
        self.timeout_note = QtWidgets.QLabel("Backlight timeout needs the small swayidle tool.")
        self.timeout_note.setObjectName("tip")
        self.install_idle = w.RButton("Install", secondary=True, radius=2)
        self.install_idle.setFixedSize(70, 20)
        self.install_idle.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.install_idle.clicked.connect(self.main.install_idle)
        note_row.addWidget(self.timeout_note)
        note_row.addStretch()
        note_row.addWidget(self.install_idle)
        bl.addLayout(note_row)
        root.addWidget(body)

        # Other
        root.addWidget(HeaderPanel("settings", "Other"))
        other = QtWidgets.QWidget()
        ol = QtWidgets.QVBoxLayout(other)
        ol.setContentsMargins(10, 2, 5, 2)  # Padding(21, 5, 11, 5)
        ol.setSpacing(0)
        self.topmost = check("Keep app window always on top", 2)
        self.topmost.setChecked(bool(self.cfg.get("topmost")))
        self.topmost.toggled.connect(self.on_topmost)
        ol.addWidget(self.topmost)
        self.no_overdrive = None
        if hw.get_overdrive() is not None:
            self.no_overdrive = check("Disable screen overdrive", 2)
            self.no_overdrive.setChecked(bool(self.cfg.get("no_overdrive")))
            self.no_overdrive.toggled.connect(self.on_no_overdrive)
            ol.addWidget(self.no_overdrive)
        if main.optimized:
            self.usbc = check("Keep GPU disabled on USB-C charger in Optimized mode", 2)
            self.usbc.setChecked(bool(self.cfg.get("optimized_usbc")))
            self.usbc.toggled.connect(self.on_usbc)
            ol.addWidget(self.usbc)
            # Extra.checkGpuApps: Eco blocks new users of the dGPU; running ones keep it awake
            self.gpu_apps = check("Stop all apps using GPU when switching to Eco", 2)
            self.gpu_apps.setChecked(bool(self.cfg.get("kill_gpu_apps")))
            self.gpu_apps.setToolTip("Programs already using the NVIDIA GPU keep it powered on until they "
                                     "quit. Without this option you are asked first.")
            self.gpu_apps.toggled.connect(lambda on: (self.cfg.__setitem__("kill_gpu_apps", on), self.main.save()))
            ol.addWidget(self.gpu_apps)
        # rows that exist only when this laptop's firmware has the setting (asus-armoury)
        if hw.armoury_range("boot_sound") is not None or hw._read(f"{hw.ARMOURY}/boot_sound/current_value"):
            self.boot_sound = check("Boot Sound", 2)
            self.boot_sound.setChecked(hw._read(f"{hw.ARMOURY}/boot_sound/current_value") == "1")
            self.boot_sound.toggled.connect(lambda on: self.main.bg(
                hw.run, "asusctl", "armoury", "set", "boot_sound", "1" if on else "0",
                then=lambda r: self.main.report(r, "Boot sound")))
            ol.addWidget(self.boot_sound)
        apu = hw.armoury_choices("apu_mem")
        if apu:
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(2, 4, 0, 2)
            row.addWidget(QtWidgets.QLabel("Memory Assigned to GPU"))
            row.addStretch()
            self.apu = w.RComboBox()
            self.apu.setFixedWidth(146)
            self.apu.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            for value in apu:
                self.apu.addItem("Auto" if value == "0" else f"{value} GB", value)
            self.apu.setCurrentIndex(max(0, self.apu.findData(hw._read(f"{hw.ARMOURY}/apu_mem/current_value"))))
            self.apu.activated.connect(lambda _: self.main.bg(
                hw.run, "asusctl", "armoury", "set", "apu_mem", self.apu.currentData(),
                then=lambda r: (self.main.report(r, "GPU memory"), QtWidgets.QMessageBox.information(
                    self, "Memory Assigned to GPU", "Takes effect after a restart."))))
            row.addWidget(self.apu)
            ol.addLayout(row)
        root.addWidget(other)

        # Services
        services = QtWidgets.QWidget()
        sl = QtWidgets.QHBoxLayout(services)
        sl.setContentsMargins(10, 8, 6, 8)
        sl.setSpacing(4)
        self.services_icon = QtWidgets.QLabel()
        self.services_label = QtWidgets.QLabel("")
        f = self.services_label.font()
        f.setBold(True)
        self.services_label.setFont(f)
        sl.addWidget(self.services_icon)
        sl.addWidget(self.services_label)
        sl.addStretch()
        self.services_start = w.RButton("Start", secondary=True, radius=2)  # buttonServices
        self.services_start.setFixedSize(128, 26)
        self.services_start.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.services_start.clicked.connect(lambda: (self.main.start_services(), QtCore.QTimer.singleShot(3000, self.refresh)))
        sl.addWidget(self.services_start)
        self.setup_button = w.RButton("Setup", "cog", secondary=True, radius=2)
        self.setup_button.setFixedSize(90, 26)
        self.setup_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.setup_button.setToolTip("Check and install what this laptop needs (one password)")
        self.setup_button.clicked.connect(self.main.on_setup)
        sl.addWidget(self.setup_button)
        root.addWidget(services)

        self.root = root
        self.build_bindings()
        self.refresh()

    # -- key bindings (Extra.SetKeyCombo) -------------------------------------------
    def build_bindings(self):
        """FN+F4 always, G-Helper's other rows once seen, then the keys the user added."""
        while self.bind_grid.count():
            item = self.bind_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.bind_rows = {}
        state = getattr(self.main, "hotkeys_state", "")
        rows = []
        if state not in ("no-device", "no-access", "no-evdev"):
            seen = set(self.cfg.get("seen_keys", [])) | {"fnf4"}
            rows += [(key, label, False) for key, (label, _) in hotkeys.KEYS.items() if key in seen]
            rows += [(key, info["label"], True) for key, info in self.cfg.get("custom_keys", {}).items()]
        rows += [(sid, info.get("trigger") or "(no keys set)", True)
                 for sid, info in self.cfg.get("shortcuts", {}).items()]

        r = 0
        if state in ("no-access", "no-evdev"):
            note = QtWidgets.QLabel(
                "Laptop keys need permission to read the ASUS keys (one password prompt)."
                if state == "no-access" else "Laptop keys need the python3-evdev package.")
            note.setObjectName("tip")
            note.setWordWrap(True)
            self.bind_grid.addWidget(note, r, 0, 1, 2)
            if state == "no-access":
                enable = w.RButton("Enable", secondary=True, radius=2)
                enable.setFixedHeight(22)
                enable.clicked.connect(self.main.enable_hotkeys)
                self.bind_grid.addWidget(enable, r, 2, 1, 2)
            r += 1
        for key, label, removable in rows:
            name = QtWidgets.QLabel(label + ":")
            combo = w.RComboBox()
            for action, text in hotkeys.ACTIONS:
                combo.addItem(text, action)
            stored = self.cfg.get(f"key_{key}")
            current = "" if stored == "none" else (stored or hotkeys.DEFAULT_ACTION.get(key, ""))
            combo.setCurrentIndex(max(0, combo.findData(current)))
            command = QtWidgets.QLineEdit(self.cfg.get(f"key_{key}_cmd", ""))
            command.setPlaceholderText("action")
            command.setToolTip("Command to run when the action is Custom")
            command.setFixedHeight(20)
            command.setEnabled(current == "custom")
            combo.activated.connect(lambda _=0, k=key: self.on_binding(k))
            command.editingFinished.connect(lambda k=key: self.on_binding(k))
            self.bind_grid.addWidget(name, r, 0)
            self.bind_grid.addWidget(combo, r, 1)
            self.bind_grid.addWidget(command, r, 2)
            if removable:
                remove = w.RButton("", "circle-minus", secondary=True, radius=2)
                remove.setFixedSize(20, 20)
                remove.setToolTip("Remove this key")
                remove.clicked.connect(lambda _=False, k=key: self.on_remove_key(k))
                self.bind_grid.addWidget(remove, r, 3)
            self.bind_rows[key] = (combo, command)
            r += 1
        self.add_key.setEnabled(state != "no-device" or bool(self.main.portal and self.main.portal.ok))
        self.fit()

    def fit(self):
        self.setFixedHeight(self.root.sizeHint().height())

    def on_binding(self, key):
        combo, command = self.bind_rows[key]
        action = combo.currentData()
        command.setEnabled(action == "custom")
        default = hotkeys.DEFAULT_ACTION.get(key, "")
        if action == default:
            self.cfg.pop(f"key_{key}", None)
        else:
            self.cfg[f"key_{key}"] = action or "none"
        self.cfg[f"key_{key}_cmd"] = command.text().strip()
        self.main.save()

    def on_add_key(self, button):
        menu = QtWidgets.QMenu(self)
        laptop = menu.addAction("Laptop key (Fn + ...)")
        laptop.setEnabled(getattr(self.main, "hotkeys_state", "") == "running")
        laptop.triggered.connect(self.main.capture_laptop_key)
        combo = menu.addAction("Keyboard shortcut (any keys) ...")
        combo.setEnabled(bool(self.main.portal and self.main.portal.ok))
        combo.triggered.connect(self.main.add_shortcut)
        menu.exec(button.mapToGlobal(QtCore.QPoint(0, button.height())))

    def on_remove_key(self, key):
        self.main.remove_key(key)

    def on_reset_bindings(self):
        for key in list(hotkeys.KEYS) + list(self.cfg.get("custom_keys", {})) + list(self.cfg.get("shortcuts", {})):
            self.cfg.pop(f"key_{key}", None)
            self.cfg.pop(f"key_{key}_cmd", None)
        self.main.save()
        self.build_bindings()

    def on_timeout(self):
        self.cfg["kbd_timeout_ac"] = self.timeout_ac.value()
        self.cfg["kbd_timeout_bat"] = self.timeout_bat.value()
        self.main.save()
        self.main.apply_idle()

    def show_idle_state(self, available):
        for box in (self.timeout_ac, self.timeout_bat):
            box.setEnabled(available)
        self.timeout_note.setVisible(not available)
        self.install_idle.setVisible(not available)
        self.fit()

    def refresh(self):
        self.help_icon.setPixmap(w.icon("circle-help"))
        self.show_idle_state(self.main.idle_available)
        self.services_icon.setPixmap(w.icon("cog"))
        level = hw.get_kbd_level()
        if level in hw.KBD_LEVELS:
            self.brightness.set_value(hw.KBD_LEVELS.index(level))
        state = hw.get_aura_power() or {}
        for c, key in ((self.awake, "awake"), (self.boot, "boot"), (self.sleep, "sleep")):
            c.blockSignals(True)
            c.setChecked(state.get(key, True))
            c.blockSignals(False)
        idx = self.speed.findData(hw.get_aura_speed() or self.cfg.get("aura_speed", "med"))
        self.speed.setCurrentIndex(max(idx, 0))
        running = hw.services_running()
        self.services_label.setText(f"asusd / cardwired running:  {len(running)}")
        self.services_start.setVisible(len(running) < 2)
        colour = (ECO if len(running) == 2 else STANDARD).name()
        self.services_label.setStyleSheet(f"color: {colour};")

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    # -- actions ----------------------------------------------------------------
    def on_brightness(self, value):
        self.main.bg(hw.set_kbd_level, hw.KBD_LEVELS[value],
                     then=lambda r: self.main.report(r, "Keyboard backlight"))

    def on_power(self):
        self.main.bg(hw.set_aura_power, self.awake.isChecked(), self.boot.isChecked(),
                     self.sleep.isChecked(), then=lambda r: self.main.report(r, "Backlight power"))

    def on_speed(self):
        self.cfg["aura_speed"] = self.speed.currentData()
        self.main.apply_aura()

    def on_topmost(self, on):
        self.cfg["topmost"] = on
        self.main.save()
        self.main.apply_topmost()

    def on_no_overdrive(self, on):
        self.cfg["no_overdrive"] = on
        self.main.save()
        if on and hw.get_overdrive():
            self.main.bg(hw.set_overdrive, False, then=lambda r: (self.main.report(r, "Overdrive"),
                                                                  self.main.refresh_slow()))
        else:
            self.main.refresh_slow()

    def on_usbc(self, on):
        self.cfg["optimized_usbc"] = on
        self.main.save()
        if self.cfg.get("gpu_auto"):
            self.main.apply_gpu_auto()
