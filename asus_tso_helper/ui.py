"""Main window and tray icon: the G-Helper (seerge/g-helper) layout, on top of asusd / Cardwire.

Panel order, sizes, texts and colours follow app/Settings.Designer.cs and app/Settings.cs.
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

from . import backend as hw
from .i18n import tr
from .extra import ExtraWindow
from . import hotkeys
from . import modes
from . import shortcuts
from . import updates
from . import setup
from . import selfupdate
from .fans import FansWindow, fan_max, restore_after_calibration, snapshot_factory_curves, INADEQUATE_RPM
from . import widgets as w
from .widgets import ECO, STANDARD, TURBO, CUSTOM, GRAY

APP = "asus-tso-helper"
VERSION = "0.4.0"
HOMEPAGE = "https://github.com/sprinterz5/asus-tso-helper"
DONATE_URL = ""  # PayPal donation link; Credits shows a support link once it is set
CONFIG_DIR = os.path.join(os.path.expanduser("~/.config"), APP)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
AUTOSTART = os.path.expanduser(f"~/.config/autostart/{APP}.desktop")


MODES = [("quiet", tr("Silent"), "bike", ECO),
         ("balanced", tr("Balanced"), "car", STANDARD),
         ("performance", tr("Turbo"), "rocket", TURBO)]
GPU_MODES = [("Integrated", tr("Eco"), "leaf", ECO, tr("iGPU only"),
              tr("Disables dGPU to save battery")),
             ("Hybrid", tr("Standard"), "flower-2", STANDARD, tr("iGPU + dGPU"),
              tr("Enables dGPU for standard use")),
             ("AsusMuxDgpu", tr("Ultimate"), "gamepad-2", TURBO, tr("dGPU exclusive"),
              tr("Routes laptop screen to dGPU, maximizing FPS"))]
# nvidia-smi keeps the dGPU awake for a few seconds (it sleeps ~5 s after the last use); asking
# every 2 s kept it awake forever. G-Helper falls back to the EC's GPU sensor, which Linux lacks.
DGPU_TEMP_EVERY = 12
SERVICE_TOOLS = {"asusd": "asusctl", "cardwired": "cardwire"}
OPTIMIZED_TIP = tr("Switch to Eco on battery and to Standard when plugged in")
AURA = [("static", tr("Static")), ("breathe", tr("Breathe")), ("rainbow-cycle", tr("Rainbow")), ("pulse", tr("Strobe"))]


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def stylesheet():
    t = w.THEME
    return f"""
    QWidget#root, QWidget#panel {{ background: {t.form_back.name()}; }}
    QLabel {{ color: {t.fore.name()}; background: transparent; }}
    QLabel#tip {{ color: {t.gray_text.name()}; }}
    QLabel#dim {{ color: {t.control_dark.name()}; }}
    QLabel#version {{ color: rgba(128,128,128,128); text-decoration: underline; }}
    QCheckBox {{ color: {t.fore.name()}; spacing: 6px; background: transparent; }}
    QCheckBox::indicator {{ width: 12px; height: 12px; border-radius: 2px;
        border: 1px solid {t.control_dark.name()}; background: {t.form_back.name()}; }}
    QCheckBox::indicator:hover {{ border-color: {t.fore.name()}; }}
    QCheckBox::indicator:checked {{ background: {STANDARD.name()}; border-color: {STANDARD.name()};
        image: url({os.path.join(w.ASSETS, 'check.svg')}); }}
    QComboBox QAbstractItemView {{ background: {t.button_main.name()}; color: {t.fore.name()};
        selection-background-color: {t.border_main.name()}; border: 1px solid {t.border_main.name()};
        outline: 0; }}
    QMenu {{ background: {t.form_back.name()}; color: {t.fore.name()}; border: 1px solid {t.border_main.name()}; }}
    QMenu::item {{ padding: 4px 20px 4px 24px; }}
    QMenu::item:selected {{ background: {t.button_main.name()}; }}
    QMenu::item:disabled {{ color: {t.gray_text.name()}; }}
    QMenu::separator {{ height: 1px; background: {t.border_main.name()}; margin: 3px 0; }}
    QCheckBox#apply {{ background: {t.button_second.name()}; padding: 0 8px; border-radius: 2px; }}
    QLineEdit {{ background: {t.button_main.name()}; color: {t.fore.name()};
        border: 1px solid {t.border_main.name()}; border-radius: 2px; padding: 0 4px; }}
    QSpinBox, QKeySequenceEdit {{ background: {t.button_main.name()}; color: {t.fore.name()};
        border: 1px solid {t.border_main.name()}; border-radius: 2px; }}
    QLineEdit:disabled {{ color: {t.gray_text.name()}; }}
    QLabel#pending {{ color: {STANDARD.name()}; }}
    QLabel#banner {{ color: {TURBO.name()}; }}
    QToolTip {{ background: {t.button_main.name()}; color: {t.fore.name()}; border: 1px solid {t.border_main.name()}; }}
    """


def panel(left, top, right, bottom):
    p = QtWidgets.QWidget()
    p.setObjectName("panel")
    lay = QtWidgets.QVBoxLayout(p)
    lay.setContentsMargins(left, top, right, bottom)
    lay.setSpacing(0)
    return p, lay


def grid(columns, row_height, cell_margin=2):
    """TableLayoutPanel with equal Percent columns; each control has Margin(cell_margin)."""
    holder = QtWidgets.QWidget()
    g = QtWidgets.QGridLayout(holder)
    g.setContentsMargins(cell_margin, cell_margin, cell_margin, cell_margin)
    g.setHorizontalSpacing(2 * cell_margin)
    g.setVerticalSpacing(2 * cell_margin)
    for c in range(columns):
        g.setColumnStretch(c, 1)
    g.setRowMinimumHeight(0, row_height - 2 * cell_margin)
    return holder, g


class Bridge(QtCore.QObject):
    """Delivers worker-thread results back on the GUI thread."""
    done = QtCore.Signal(object, object)


class HoverTip(QtCore.QObject):
    """Settings.cs shows a button's explanation in the grey tip label while hovering it."""

    def __init__(self, label, texts):
        super().__init__()
        self.label, self.texts = label, texts
        self.rest = ""  # shown when not hovering (e.g. a pending GPU switch)

    def set_rest(self, text):
        self.rest = text
        self.label.setText(text)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Enter and obj in self.texts:
            self.label.setText(self.texts[obj])
        elif event.type() == QtCore.QEvent.Leave and obj in self.texts:
            self.label.setText(self.rest)
        return False


class MainWindow(QtWidgets.QWidget):
    def __init__(self, tray_available):
        super().__init__()
        self.cfg = load_config()
        self.tray_available = tray_available
        self.tray = None
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.bridge = Bridge()
        self.bridge.done.connect(lambda cb, result: cb(result))
        self.last_ac = None
        self.dgpu_awake = False
        self.bat_time = None
        self.kbd_restoring = 0.0
        self.dgpu_temp = None
        self.dgpu_temp_at = 0.0
        self.gpu_current = None
        self.gpu_busy = False
        self.battery_hover = False
        self.extra = None
        self.fans = None
        self.updates = None
        self.setup = None
        self.version = VERSION
        self.mode_busy = False
        self.last_profile = None
        self.full_hover = False

        model = hw.model_name()
        self.setWindowTitle(f"{APP} - {model}" if model else APP)
        self.setWindowIcon(QtGui.QIcon(w.APP_ICON))
        self.setFixedWidth(425)  # ClientSize 849 at 192 DPI
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(5, 5, 6, 6)  # Padding(11)
        root.setSpacing(0)

        # shown only when asusd / cardwired are not running: one clear line instead of errors
        self.banner = QtWidgets.QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setCursor(QtCore.Qt.PointingHandCursor)
        self.banner.setContentsMargins(10, 6, 10, 2)
        self.banner.mousePressEvent = lambda _: self.start_services()
        self.banner.hide()
        self.services_missing = []
        root.addWidget(self.banner)
        self.root_layout = root

        root.addWidget(self.build_performance())
        root.addWidget(self.build_gpu())
        root.addWidget(self.build_screen())
        root.addWidget(self.build_keyboard())
        root.addWidget(self.build_battery())
        root.addWidget(self.build_startup())
        root.addWidget(self.build_version())
        root.addWidget(self.build_footer())
        self.setFixedHeight(root.sizeHint().height())

        if self.cfg.get("calibration_backup"):
            # the app quit mid-calibration: undo the 100% Turbo curves first
            self.bg(restore_after_calibration, self.cfg,
                    then=lambda r: (self.cfg.pop("calibration_backup", None), self.save()))
        elif not self.cfg.get("factory_curves"):
            self.bg(snapshot_factory_curves, self.cfg, then=lambda saved: saved and self.save())
        self.hotkeys_state = ""
        self.hotkeys = hotkeys.Hotkeys(self.cfg)
        self.hotkeys.action.connect(self.on_hotkey)
        self.hotkeys.seen.connect(self.on_hotkey_seen)
        self.hotkeys.state.connect(self.on_hotkeys_state)
        self.hotkeys.captured.connect(self.on_key_captured)
        self.hotkeys.start()
        self.capture_box = None
        self.portal = shortcuts.PortalShortcuts()
        self.portal.activated.connect(self.on_shortcut)
        self.portal.bound.connect(self.on_shortcuts_bound)
        self.portal.failed.connect(lambda msg: self.portal_busy and QtWidgets.QMessageBox.warning(
            self, APP, tr("Keyboard shortcut was not added: {msg}", msg=msg)))
        self.portal_busy = False
        if self.cfg.get("shortcuts") and self.portal.ok:
            self.portal.bind([(sid, self.shortcut_description(sid)) for sid in self.cfg["shortcuts"]])
        self.idle_available = bool(shutil.which("swayidle"))
        self.idle_proc = None
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.stop_idle)
        self.apply_theme()
        self.apply_topmost()
        hints = QtGui.QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _: self.apply_theme())

        self.fast = QtCore.QTimer(self, interval=2000, timeout=self.refresh_fast)
        self.slow = QtCore.QTimer(self, interval=5000, timeout=self.refresh_slow)
        self.fast.start()
        self.slow.start()
        # new app version: shortly after start, then once a day
        self.update_timer = QtCore.QTimer(self, interval=24 * 3600 * 1000, timeout=self.check_app_update)
        self.update_timer.start()
        QtCore.QTimer.singleShot(10000, self.check_app_update)
        self.refresh_fast()
        self.refresh_slow()

    # -- layout -----------------------------------------------------------------
    def build_performance(self):
        p, lay = panel(10, 10, 10, 10)  # Padding(20)
        self.perf_head = w.Header("gauge", tr("Mode"))
        lay.addWidget(self.perf_head)
        holder, g = grid(4, 64)
        self.mode_buttons = {}
        for col, (key, label, icon_name, colour) in enumerate(MODES):
            b = w.RButton(label, icon_name, accent=colour, vertical=True)
            b.setFixedHeight(60)
            b.clicked.connect(lambda _=False, k=key: self.on_profile(k))
            g.addWidget(b, 0, col)
            self.mode_buttons[key] = b
        self.fans_button = w.RButton(tr("Fans + Power"), "fan", secondary=True, accent=CUSTOM, vertical=True)
        self.fans_button.setFixedHeight(60)
        self.fans_button.clicked.connect(self.on_fans)
        g.addWidget(self.fans_button, 0, 3)
        lay.addWidget(holder)
        return p

    def build_gpu(self):
        p, lay = panel(10, 10, 10, 0)  # Padding(20, 20, 20, 0)
        self.gpu_head = w.Header("gpu", tr("GPU Mode"))
        lay.addWidget(self.gpu_head)
        holder, g = grid(4, 64)
        self.gpu_tip = QtWidgets.QLabel("")
        self.gpu_tip.setObjectName("tip")
        self.gpu_tip.setFixedHeight(18)
        self.gpu_tip.setWordWrap(True)
        self.gpu_tip.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        supported = hw.gpu_supported() or [m[0] for m in GPU_MODES]
        self.gpu_buttons = {}
        tips = {}
        col = 0
        for key, label, icon_name, colour, _, tip in GPU_MODES:
            if key not in supported:
                continue
            b = w.RButton(label, icon_name, accent=colour, vertical=True)
            b.setFixedHeight(60)
            b.clicked.connect(lambda _=False, k=key: self.on_gpu(k))
            g.addWidget(b, 0, col)
            col += 1
            self.gpu_buttons[key] = b
            tips[b] = tip
        self.optimized = None
        if "Integrated" in supported and "Hybrid" in supported:
            self.optimized = w.RButton(tr("Optimized"), "sparkles", accent=ECO, vertical=True)
            self.optimized.setFixedHeight(60)
            self.optimized.clicked.connect(self.on_optimized)
            g.addWidget(self.optimized, 0, col)
            tips[self.optimized] = OPTIMIZED_TIP
        self.gpu_hover = HoverTip(self.gpu_tip, tips)
        self.gpu_target = None
        self.gpu_tip.mousePressEvent = lambda _: self.on_gpu_tip_clicked()
        for b in tips:
            b.installEventFilter(self.gpu_hover)
        lay.addWidget(holder)
        lay.addWidget(self.gpu_tip)
        return p

    def build_screen(self):
        p, lay = panel(10, 6, 10, 0)  # Padding(20, 11, 20, 0)
        self.screen_head = w.Header("laptop", tr("Screen"))
        lay.addWidget(self.screen_head)
        holder, g = grid(4, 40)
        g.setRowMinimumHeight(1, 10 - 4)
        self.screen_tip = QtWidgets.QLabel("")
        self.screen_tip.setObjectName("tip")
        self.screen_tip.setFixedHeight(18)
        self.screen_tip.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.screen_auto = w.RButton(tr("Auto"), accent=GRAY)
        self.screen_60 = w.RButton(tr("60Hz"), accent=GRAY)
        self.screen_max = w.RButton(tr("Max"), accent=GRAY)
        for col, (b, key) in enumerate(((self.screen_auto, "auto"), (self.screen_60, "60"),
                                        (self.screen_max, "max"))):
            b.setFixedHeight(36)
            b.clicked.connect(lambda _=False, k=key: self.on_screen(k))
            g.addWidget(b, 0, col)
        self.screen_hover = HoverTip(self.screen_tip, {
            self.screen_auto: tr("Sets 60Hz to save battery, and back when plugged"),
            self.screen_60: tr("60Hz refresh rate to save battery"),
            self.screen_max: tr("Max refresh rate for lower latency")})
        for b in (self.screen_auto, self.screen_60, self.screen_max):
            b.installEventFilter(self.screen_hover)
        lay.addWidget(holder)
        lay.addWidget(self.screen_tip)
        return p

    def build_keyboard(self):
        p, lay = panel(10, 10, 10, 0)  # Padding(20, 20, 20, 0)
        self.kbd_head = w.Header("keyboard", tr("Laptop Keyboard"))
        self.fn_lock = w.RButton(tr("FN-Lock"), secondary=True, radius=2, borderless=True)
        f = self.fn_lock.font()
        f.setPointSizeF(f.pointSizeF() * 7.125 / 9)
        f.setBold(True)
        self.fn_lock.setFont(f)
        self.fn_lock.setFixedSize(62, 20)
        self.fn_lock.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.fn_lock.text_colour = w.THEME.control_dark
        self.fn_lock.setToolTip(tr("FN-Lock is toggled with Fn + Esc on this laptop"))
        self.kbd_head.right.addWidget(self.fn_lock)
        self.kbd_head.right.setContentsMargins(23, 0, 2, 0)
        lay.addWidget(self.kbd_head)

        holder = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(holder)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(0)
        for c in range(3):
            g.setColumnStretch(c, 1)
        self.aura_combo = w.RComboBox()
        for key, label in AURA:
            self.aura_combo.addItem(label, key)
        idx = self.aura_combo.findData(self.cfg.get("aura_effect", "static"))
        self.aura_combo.setCurrentIndex(max(idx, 0))
        self.aura_combo.activated.connect(lambda _: self.apply_aura())
        combo_box = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(combo_box)
        cl.setContentsMargins(3, 3, 3, 2)  # Margin(7, 7, 7, 4)
        cl.addWidget(self.aura_combo)
        self.colour_button = w.ColorButton(tr("Color"), "#" + self.cfg.get("aura_colour", "ffffff"), radius=2)
        self.colour_button.setFixedHeight(24)
        self.colour_button.clicked.connect(self.pick_colour)
        self.extra_button = w.RButton(tr("Extra"), "settings", secondary=True, radius=2)
        self.extra_button.setFixedHeight(24)
        self.extra_button.clicked.connect(self.on_extra)
        g.addWidget(combo_box, 0, 0)
        for col, b in ((1, self.colour_button), (2, self.extra_button)):
            cell = QtWidgets.QWidget()
            bl = QtWidgets.QVBoxLayout(cell)
            bl.setContentsMargins(2, 2, 2, 0)
            bl.addWidget(b)
            g.addWidget(cell, 0, col)
        lay.addWidget(holder)
        self.backlight_label = QtWidgets.QLabel("")
        self.backlight_label.setObjectName("tip")
        self.backlight_label.setFixedHeight(17)
        self.backlight_label.setContentsMargins(2, 0, 2, 0)
        self.backlight_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        lay.addWidget(self.backlight_label)
        return p

    def build_battery(self):
        p, lay = panel(10, 8, 10, 0)  # Padding(20, 15, 20, 0)
        self.bat_panel = p
        p.installEventFilter(self)
        self.bat_head = w.Header("battery-charging", tr("Battery Charge Limit"), height=22)
        lay.addWidget(self.bat_head)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.slider = w.Slider(40, 100, 5)
        self.slider.valueChanged.connect(self.show_limit)
        self.slider.released.connect(self.on_limit)
        self.full_button = w.RButton(tr("100%"), secondary=True, radius=2, borderless=True)
        f = self.full_button.font()
        f.setPointSizeF(f.pointSizeF() * 7.125 / 9)
        f.setBold(True)
        self.full_button.setFont(f)
        self.full_button.text_colour = w.THEME.control_dark
        self.full_button.setFixedSize(36, 18)
        self.full_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.full_button.clicked.connect(self.on_full_charge)
        self.full_button.installEventFilter(self)
        row.addWidget(self.slider, 1)
        row.addSpacing(4)
        row.addWidget(self.full_button, 0, QtCore.Qt.AlignVCenter)
        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        holder.setFixedHeight(22)
        lay.addWidget(holder)
        return p

    def build_startup(self):
        p = QtWidgets.QWidget()
        p.setFixedHeight(25)
        lay = QtWidgets.QHBoxLayout(p)
        lay.setContentsMargins(15, 0, 10, 0)
        self.startup = QtWidgets.QCheckBox(tr("Run on Startup"))
        self.startup.setChecked(os.path.exists(AUTOSTART))
        self.startup.toggled.connect(self.on_startup)
        self.charge_label = QtWidgets.QLabel("")
        self.charge_label.setObjectName("dim")
        self.charge_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lay.addWidget(self.startup)
        lay.addStretch()
        lay.addWidget(self.charge_label)
        return p

    def build_version(self):
        p = QtWidgets.QWidget()
        p.setMinimumHeight(25)
        lay = QtWidgets.QHBoxLayout(p)
        lay.setContentsMargins(12, 2, 12, 2)
        version = QtWidgets.QLabel(tr("Version: {version}", version=VERSION))
        version.setObjectName("version")
        version.setCursor(QtCore.Qt.PointingHandCursor)
        version.mousePressEvent = lambda _: self.on_version_clicked()
        self.version_label = version
        self.release_url = HOMEPAGE
        self.latest_release = None
        lay.addWidget(version)
        lay.addStretch()
        return p

    def build_footer(self):
        p = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(p)
        lay.setContentsMargins(10, 5, 10, 10)  # Padding(20, 10, 20, 20)
        lay.setSpacing(4)
        credits = w.RButton(tr("Credits"), "heart", secondary=True, radius=2)
        credits.clicked.connect(self.on_credits)
        updates = w.RButton(tr("Updates"), "download", secondary=True, radius=2)
        updates.clicked.connect(self.on_updates)
        quit_b = w.RButton(tr("Quit"), "log-out", secondary=True, radius=2)
        quit_b.clicked.connect(QtWidgets.QApplication.quit)
        for b in (credits, updates, quit_b):
            b.setFixedHeight(24)
            lay.addWidget(b, 1)
        return p

    def apply_theme(self):
        scheme = QtGui.QGuiApplication.styleHints().colorScheme()
        w.set_theme(scheme != QtCore.Qt.ColorScheme.Light)
        self.setStyleSheet(stylesheet())
        self.fn_lock.text_colour = w.THEME.control_dark
        self.full_button.text_colour = w.THEME.control_dark
        for child in self.findChildren(QtWidgets.QWidget):
            child.update()
        if self.tray:
            self.tray.apply_theme()

    # -- plumbing -------------------------------------------------------------
    def bg(self, fn, *args, then=None):
        """Run fn(*args) off the GUI thread, then call `then(result)` on it."""
        def job():
            result = fn(*args)
            if then:
                self.bridge.done.emit(then, result)
        self.pool.submit(job)

    def report(self, result, what):
        ok, out = result
        if ok:
            return
        if self.services_missing:
            self.flash_banner()  # the banner already says why; no raw command errors
            return
        QtWidgets.QMessageBox.warning(self, APP, tr("{what} failed:", what=what) + f"\n{out}")

    # -- asusd / cardwired status ------------------------------------------------------
    def show_services(self, running):
        missing = [n for n in ("asusd", "cardwired") if n not in running]
        if missing == self.services_missing:
            return
        self.services_missing = missing
        if missing:
            names = ", ".join(missing)
            self.banner.setText(tr("Not running: {names}. Settings cannot be changed. Click here to start.",
                                   names=names))
        self.banner.setVisible(bool(missing))
        self.setFixedHeight(self.root_layout.sizeHint().height())

    def flash_banner(self):
        self.banner.setStyleSheet(f"color: {TURBO.name()}; font-weight: bold;")
        QtCore.QTimer.singleShot(1200, lambda: self.banner.setStyleSheet(""))

    def start_services(self):
        missing = list(self.services_missing)
        if not missing:
            return
        if not all(shutil.which(SERVICE_TOOLS[n]) for n in missing if n in SERVICE_TOOLS):
            self.on_setup()  # not installed: Setup installs them
            return
        self.banner.setText("Starting " + " and ".join(missing) + " ...")
        self.bg(hotkeys.run_as_root, "systemctl start " + " ".join(missing),
                then=lambda r: (self.report_plain(r, tr("Starting services")),
                                setattr(self, "services_missing", ["?"]), self.refresh_slow(),
                                self.refresh_fast()))

    def report_plain(self, result, what):
        ok, out = result
        if not ok and out:
            QtWidgets.QMessageBox.warning(self, APP, tr("{what} failed:", what=what) + f"\n{out}")

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind not in (QtCore.QEvent.Enter, QtCore.QEvent.Leave) or not hasattr(self, "charge_label"):
            return False
        if obj is self.bat_panel:
            self.battery_hover = kind == QtCore.QEvent.Enter
            self.update_charge_label()
        elif obj is self.full_button:
            self.full_hover = kind == QtCore.QEvent.Enter
            self.update_charge_label()
        return False

    # -- refresh ----------------------------------------------------------------
    def refresh_fast(self):
        ac = hw.ac_online()
        if ac != self.last_ac:
            first = self.last_ac is None
            self.last_ac = ac
            if self.cfg.get("screen") == "auto":
                self.apply_screen_auto()
            if not first and self.cfg.get("gpu_auto"):
                self.apply_gpu_auto()
            self.apply_idle()
            if not first:
                self.on_power_source(ac)
            if not first and not ac and self.cfg.get("full_once"):
                self.end_full_charge()
            if not first:
                self.restore_kbd_level(ac)

        profile = hw.get_profile()
        if not self.mode_busy and profile != self.last_profile:
            if self.last_profile is not None and profile in hw.ASUSD_PROFILE:
                # changed outside the app (Fn+F5): it becomes this power source's mode, with a toast
                self.remember_mode(profile)
                self.toast_mode(profile)
            self.last_profile = profile
        custom = modes.active(self.cfg)
        if custom and profile != custom["base"] and not self.mode_busy:
            # profile changed outside (Fn+F5, asusd on charger change): the custom mode ended
            self.mode_busy = True
            self.bg(lambda: (modes.deactivate(self.cfg), self.save()),
                    then=lambda _: (setattr(self, "mode_busy", False), self.modes_changed()))
            custom = None
        for key, b in self.mode_buttons.items():
            b.set_activated(key == profile and not custom)
        # Settings.VisualiseMode: a custom mode lights "Fans + Power" in its base colour
        self.fans_button.set_activated(bool(custom))
        if custom:
            self.fans_button.set_accent({m[0]: m[3] for m in MODES}.get(custom["base"], CUSTOM))
            name = custom["name"]
        else:
            name = next((m[1] for m in MODES if m[0] == profile), profile or "?")
        self.perf_head.title.setText(tr("Mode: {name}", name=name))
        # dGPU temperature only while the window is open and the dGPU is awake anyway; asleep it
        # shows the last one (G-Helper 0.248, issue #5290), in Eco none
        now = time.monotonic()
        eco = self.gpu_current == "Integrated"
        power = hw.dgpu_power(blocked=eco)
        if power is None or eco:
            self.dgpu_temp = None
        query = (power == "active" and not eco and self.isVisible()
                 and now - self.dgpu_temp_at >= DGPU_TEMP_EVERY)
        if query:
            self.dgpu_temp_at = now
        self.bg(hw.sensors, query, then=self.show_sensors)

        limit = hw.get_charge_limit()
        if limit is not None and not self.slider.dragging:
            self.slider.set_value(limit)
            self.show_limit(limit)
            if self.cfg.get("full_once") and limit != 100:
                self.cfg.pop("full_once")
                save_config(self.cfg)
        self.full_button.set_activated(bool(self.cfg.get("full_once")))

        self.bat = hw.battery_status()
        text = ""
        if self.bat and self.bat["watts"]:
            if self.bat["status"] == "Charging":
                text = tr("Charging: {watts}W", watts=f"{self.bat['watts']:.1f}")
            elif self.bat["status"] == "Discharging":
                text = tr("Discharging: {watts}W", watts=f"{self.bat['watts']:.1f}")
        self.bat_head.info.setText(text)
        if text:  # charging or discharging: UPower's estimate, off the GUI thread
            self.bg(hw.battery_time, then=lambda t: (setattr(self, "bat_time", t), self.update_charge_label()))
        else:
            self.bat_time = None
        self.update_charge_label()

        level = hw.get_kbd_level()
        self.backlight_label.setText("")
        self.kbd_level = level
        self.remember_kbd_level(ac, level)

        if self.bat and self.cfg.get("full_once") and self.bat["percent"] == 100:
            self.end_full_charge()

    def refresh_slow(self):
        self.bg(hw.services_running, then=self.show_services)
        eco = self.gpu_current == "Integrated"
        self.bg(lambda: (hw.gpu_mode(), hw.gpu_pending(), hw.dgpu_power(blocked=eco)), then=self.show_gpu)
        self.bg(lambda: (hw.screen_info(), hw.get_overdrive()), then=self.show_screen)

    def update_charge_label(self):
        if self.full_hover:
            text = tr("One time charge to 100%")
        elif self.battery_hover:
            health = hw.battery_health()
            cycles = hw.battery_cycles()  # many ASUS batteries report 0
            text = tr("Battery Health: {health}%", health=f"{health:.1f}") if health else ""
            if text and cycles:
                text += ", " + tr("{count} cycles", count=cycles)
        else:
            bat = getattr(self, "bat", None)
            text = tr("Charge: {percent}%", percent=bat["percent"]) if bat and bat["percent"] is not None else ""
            if text and self.bat_time:
                kind, secs = self.bat_time
                time_text = tr("{h}h {m}m", h=secs // 3600, m=f"{secs % 3600 // 60:02d}")
                text += " (" + (tr("{time} left", time=time_text) if kind == "left" else
                                tr("{time} to full", time=time_text)) + ")"
        self.charge_label.setText(text)

    def show_limit(self, value):
        self.bat_head.title.setText(tr("Battery Charge Limit: {value}%", value=value))

    def show_sensors(self, s):
        fans = s["fans"]

        def fan(name):
            """FanSensorControl.FormatFan: percent of the (calibrated) max RPM."""
            rpm = fans.get(name)
            if rpm is None:
                return ""
            if fan_max(self.cfg, name) < rpm < INADEQUATE_RPM and not self.cfg.get("calibration_backup"):
                self.cfg[f"fan_max_{name}"] = rpm
                save_config(self.cfg)
            calibrated = any(k.startswith("fan_table_") for k in self.cfg)
            if self.cfg.get("fan_rpm", calibrated):
                return tr("Fan: {value}", value=f"{rpm}RPM")
            return tr("Fan: {value}", value=f"{min(100, round(rpm * 100 / fan_max(self.cfg, name)))}%")

        if s["dgpu"] is not None:
            self.dgpu_temp = s["dgpu"]
        cpu = f": {s['cpu']:.0f}°C" if s["cpu"] is not None else ""
        gpu = f": {self.dgpu_temp}°C" if self.dgpu_temp is not None else ""
        self.perf_head.info.setText(f"CPU{cpu}  {fan('cpu')}")
        self.gpu_head.info.setText(f"GPU{gpu}  {fan('gpu')}")
        if self.tray:
            tip = f"CPU{cpu} {fan('cpu')}\nGPU{gpu} {fan('gpu')}"
            if self.bat_head.info.text():
                tip += "\n" + self.bat_head.info.text()
            self.tray.setToolTip(tip)

    def show_gpu(self, data):
        mode, pending, power = data
        self.dgpu_awake = power == "active"
        if self.gpu_busy:
            return
        self.gpu_current = mode
        after = self.cfg.get("gpu_after_reboot")
        if after and mode and mode != "AsusMuxDgpu" and not pending:
            # back from Ultimate: the MUX is on the iGPU again, now the mode that was picked
            self.cfg.pop("gpu_after_reboot")
            save_config(self.cfg)
            if after != mode:
                self.switch_gpu(after)
                return
        # waiting for the reboot of a MUX change: what we asked for
        target = self.gpu_target if pending and self.gpu_target != mode else None
        if not target:
            self.gpu_target = None
        self.show_gpu_pending(mode, target, pending if target else None)
        auto = bool(self.cfg.get("gpu_auto"))
        for key, b in self.gpu_buttons.items():
            b.set_activated(key == mode and not (auto and key in ("Integrated", "Hybrid")))
        if self.optimized:
            self.optimized.set_activated(auto)
            self.optimized.set_accent(ECO if mode == "Integrated" else STANDARD)
        label = next((m[4] for m in GPU_MODES if m[0] == mode), mode or "?")
        if target:
            to = next((m[4] for m in GPU_MODES if m[0] == target), target)
            self.gpu_head.title.setText(tr("GPU Mode: {mode}", mode=f"{label} \u2192 {to}"))
        else:
            self.gpu_head.title.setText(tr("GPU Mode: {mode}", mode=label))
        if self.tray:
            self.tray.set_gpu(mode)

    def show_gpu_pending(self, mode, target, pending):
        for key, b in self.gpu_buttons.items():
            b.set_pending(key == target)
        if target or pending:
            action = (pending or "Reboot required to complete mode change").rstrip(".")
            reboot = "reboot" in action.lower() or "restart" in action.lower()
            self.gpu_logout_reboot = reboot
            self.gpu_hover.set_rest(tr("{action}. Click here to restart now, or pick the current mode to cancel.",
                                       action=tr(action)) if reboot else
                                    tr("{action}. Click here to log out now, or pick the current mode to cancel.",
                                       action=tr(action)))
            self.gpu_tip.setObjectName("pending")
            self.gpu_tip.setCursor(QtCore.Qt.PointingHandCursor)
        else:
            self.gpu_hover.set_rest("")
            self.gpu_tip.setObjectName("tip")
            self.gpu_tip.unsetCursor()
        self.gpu_tip.style().unpolish(self.gpu_tip)
        self.gpu_tip.style().polish(self.gpu_tip)
        height = 32 if (target or pending) else 18  # the pending note takes two lines
        if self.gpu_tip.height() != height:
            self.gpu_tip.setFixedHeight(height)
            # layouts pick the new height up on the next event loop pass
            QtCore.QTimer.singleShot(0, lambda: self.setFixedHeight(self.root_layout.sizeHint().height()))

    def on_gpu_tip_clicked(self):
        if self.gpu_tip.objectName() != "pending":
            return
        method = "promptReboot" if getattr(self, "gpu_logout_reboot", False) else "promptLogout"
        ok, _ = hw.run("busctl", "--user", "call", "org.kde.LogoutPrompt", "/LogoutPrompt",
                       "org.kde.LogoutPrompt", method, timeout=5)
        if not ok:
            QtWidgets.QMessageBox.information(self, APP, tr("Log out (or restart) to finish the GPU mode change."))

    def show_screen(self, data):
        info, overdrive = data
        if not info:
            self.screen_head.title.setText(tr("Screen: Turned off"))
            for b in (self.screen_auto, self.screen_60, self.screen_max):
                b.setEnabled(False)
            return
        _, hz, rates = info
        for b in (self.screen_auto, self.screen_60, self.screen_max):
            b.setEnabled(True)
        self.screen_head.title.setText(tr("Screen: {hz}Hz", hz=hz) + (tr(" + Overdrive") if overdrive else ""))
        self.screen_60.setText(tr("{hz}Hz", hz=min(rates)))
        od = overdrive is not None and not self.cfg.get("no_overdrive")
        self.screen_max.setText(tr("{hz}Hz", hz=max(rates)) + (" + OD" if od else ""))
        auto = self.cfg.get("screen") == "auto"
        self.screen_auto.set_activated(auto)
        self.screen_60.set_activated(not auto and hz <= min(rates))
        self.screen_max.set_activated(not auto and hz > min(rates))

    # -- actions ----------------------------------------------------------------
    def on_profile(self, key, notify=False):
        """A base mode (quiet / balanced / performance) or a custom mode id.
        notify: show the toast (mode picked by a key, not in the window)."""
        self.remember_mode(key)
        if notify:
            self.toast_mode(key)
        if modes.get(self.cfg, key):
            self.mode_busy = True

            def job():
                result = modes.activate(self.cfg, key)
                self.save()
                return result
            self.bg(job, then=self.mode_done)
            return
        for k, b in self.mode_buttons.items():
            b.set_activated(k == key)
        self.mode_busy = True

        def job():
            if modes.active(self.cfg):
                modes.deactivate(self.cfg)
                self.save()
            return hw.set_profile(key)
        self.bg(job, then=self.mode_done)

    def mode_done(self, result):
        self.mode_busy = False
        self.last_profile = hw.get_profile()
        self.report(result, tr("Mode"))
        self.refresh_fast()
        self.modes_changed()

    def remember_mode(self, key):
        """Modes.SetCurrent: the mode is kept per power source, like G-Helper's performance_<ac>.
        asusd is told too, so it already switches the base profile when the charger changes."""
        ac = bool(self.last_ac if self.last_ac is not None else hw.ac_online())
        src = "ac" if ac else "bat"
        if self.cfg.get(f"mode_{src}") == key:
            return
        self.cfg[f"mode_{src}"] = key
        self.save()
        base = modes.base_of(self.cfg, key)
        if base in hw.ASUSD_PROFILE:
            self.bg(hw.set_source_profile, base, ac)

    # keyboard_brightness / keyboard_brightness_ac in G-Helper: each power source keeps its own
    # backlight level. Fn+F2/F3 are handled by the firmware, so a change is seen by polling.
    def remember_kbd_level(self, ac, level):
        if (level is None or time.monotonic() < self.kbd_restoring
                or os.path.exists(hw.KBD_IDLE_FILE)):  # off because of the idle timeout
            return
        key = "kbd_ac" if ac else "kbd_bat"
        if self.cfg.get(key) != level:
            self.cfg[key] = level
            save_config(self.cfg)

    def restore_kbd_level(self, ac):
        level = self.cfg.get("kbd_ac" if ac else "kbd_bat")
        if level and level != self.kbd_level and not os.path.exists(hw.KBD_IDLE_FILE):
            self.kbd_restoring = time.monotonic() + 3  # until the new level reads back
            self.bg(hw.set_kbd_level, level)

    def on_power_source(self, ac):
        """Charger plugged or unplugged: the mode last used on this source comes back
        (custom modes too); with none remembered asusd's own choice stays."""
        target = self.cfg.get("mode_ac" if ac else "mode_bat")
        self.mode_busy = True

        def job():
            current = modes.active(self.cfg)
            if target and modes.get(self.cfg, target):
                modes.activate(self.cfg, target)  # also puts its limits on this source
            elif target in hw.ASUSD_PROFILE:
                if current:
                    modes.deactivate(self.cfg)
                if hw.get_profile() != target:
                    hw.set_profile(target)
                modes.restore_pending(self.cfg)
            elif current:
                modes.reapply(self.cfg)  # the other source has its own limits in asusd
            else:
                modes.restore_pending(self.cfg)
            self.save()
            return True, ""
        self.bg(job, then=self.mode_done)

    def toast_mode(self, key):
        base = modes.base_of(self.cfg, key)
        icon = {"quiet": "battery-profile-powersave", "balanced": "battery-profile-balanced",
                "performance": "battery-profile-performance"}.get(base, "battery-profile-balanced")
        self.toast(icon, modes.name_of(self.cfg, key))

    def toast(self, icon, text):
        """Program.toast.RunToast: KDE's OSD, or a tray notification elsewhere."""
        def fallback(ok):
            if not ok and self.tray:
                self.tray.showMessage(APP, text, QtWidgets.QSystemTrayIcon.Information, 1500)
        self.bg(hw.osd, icon, text, then=fallback)

    def modes_changed(self):
        """Custom modes were added, renamed, removed or (de)activated."""
        if self.tray:
            self.tray.build_menu()
        if self.fans and self.fans.isVisible():
            self.fans.load()
        if self.extra is not None:
            self.extra.build_bindings()  # "<mode> Mode" key actions

    def on_fans(self):
        if self.fans is None:
            self.fans = FansWindow(self)
        self.fans.show()
        self.fans.raise_()
        self.fans.activateWindow()

    def on_gpu(self, mode):
        if self.cfg.pop("gpu_auto", None):
            save_config(self.cfg)
        if mode == self.gpu_current:
            if self.gpu_target:  # picking the current mode cancels a pending MUX change
                self.gpu_target = None
                self.cfg.pop("gpu_after_reboot", None)
                save_config(self.cfg)
                self.bg(hw.set_armoury, "gpu_mux_mode", 0 if mode == "AsusMuxDgpu" else 1,
                        then=lambda r: (self.report(r, tr("GPU mode")), self.refresh_slow()))
            else:
                self.refresh_slow()
            return
        if mode == "AsusMuxDgpu" or self.gpu_current == "AsusMuxDgpu":
            answer = QtWidgets.QMessageBox.question(
                self, tr("GPU Mode"),
                tr("Switching to or from Ultimate Mode requires restart.\n\nSwitch and reboot now?"))
            if answer != QtWidgets.QMessageBox.Yes:
                self.refresh_slow()
                return
            if self.gpu_current == "AsusMuxDgpu":
                self.cfg["gpu_after_reboot"] = mode  # Cardwire's mode, set after the reboot
                save_config(self.cfg)
            self.switch_gpu(mode, reboot=True)
        else:
            close = []
            if mode == "Integrated":
                close = self.close_gpu_apps()
                if close is None:
                    self.refresh_slow()
                    return
            self.switch_gpu(mode, close=close)

    def close_gpu_apps(self):
        """Programs using the NVIDIA GPU before Eco -> pids to close, or None to cancel.
        Cardwire only blocks new users: running ones keep the dGPU awake until they quit. The
        desktop (KWin) keeps it open too, but that does not wake it, so it is left alone."""
        apps, _desktop = hw.gpu_apps()
        if not apps:
            return []
        pids = [pid for pid, _ in apps]
        if self.cfg.get("kill_gpu_apps"):
            return pids
        names = sorted({name for _, name in apps})
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question, tr("Switch to Eco"),
                                    tr("These programs use the NVIDIA GPU:") + "\n\n  " + "\n  ".join(names), parent=self)
        box.setInformativeText(tr("They keep it powered on until they are closed. Close them now?"))
        close = box.addButton(tr("Close and switch"), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(tr("Switch anyway"), QtWidgets.QMessageBox.DestructiveRole)
        cancel = box.addButton(QtWidgets.QMessageBox.Cancel)
        box.setDefaultButton(close)
        box.exec()
        if box.clickedButton() is cancel:
            return None
        return pids if box.clickedButton() is close else []

    @staticmethod
    def terminate(pids, wait=3.0):
        """SIGTERM, then give the programs a moment to let go of the GPU."""
        import signal
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        deadline = time.monotonic() + wait
        while pids and time.monotonic() < deadline:
            pids = [pid for pid in pids if os.path.exists(f"/proc/{pid}")]
            time.sleep(0.1)

    def switch_gpu(self, mode, reboot=False, close=()):
        self.gpu_busy = True
        self.gpu_head.title.setText(tr("GPU Mode: Changing ..."))
        for b in self.gpu_buttons.values():
            b.setEnabled(False)

        def done(result):
            ok, out = result
            self.gpu_busy = False
            for b in self.gpu_buttons.values():
                b.setEnabled(True)
            if not ok:
                self.cfg.pop("gpu_after_reboot", None)
                save_config(self.cfg)
                self.report(result, tr("GPU mode"))
            elif "reboot" in (out or "").lower():
                self.gpu_target = mode
                if reboot:
                    subprocess.Popen(["systemctl", "reboot"])
            self.refresh_slow()

        def job():
            if close:
                self.terminate(list(close))
            return hw.set_gpu_mode(mode)
        self.bg(job, then=done)

    def on_optimized(self):
        self.cfg["gpu_auto"] = True
        save_config(self.cfg)
        self.apply_gpu_auto()
        self.refresh_slow()

    def apply_gpu_auto(self):
        plugged = hw.ac_online() and not (self.cfg.get("optimized_usbc") and hw.usb_c_charger())
        want = "Hybrid" if plugged else "Integrated"
        if self.gpu_current not in ("Integrated", "Hybrid") or self.gpu_current == want or self.gpu_busy:
            return
        close = []
        if want == "Integrated" and self.cfg.get("kill_gpu_apps"):
            close = [pid for pid, _ in hw.gpu_apps()[0]]
        self.switch_gpu(want, close=close)

    def on_screen(self, key):
        self.cfg["screen"] = key
        save_config(self.cfg)
        if key == "auto":
            self.apply_screen_auto()
        elif key == "60":
            self.set_screen(60, False)
        else:
            self.set_screen(1000, not self.cfg.get("no_overdrive"))

    def apply_screen_auto(self):
        if hw.ac_online():
            self.set_screen(1000, not self.cfg.get("no_overdrive"))
        else:
            self.set_screen(60, False)

    def set_screen(self, hz, overdrive):
        """ScreenControl.SetScreen(rate, overdrive): max Hz goes with overdrive on, 60Hz with it off."""
        def job():
            result = hw.set_refresh(hz)
            if hw.get_overdrive() is not None and hw.get_overdrive() != overdrive:
                hw.set_overdrive(overdrive)
            return result
        self.bg(job, then=lambda r: (self.report(r, tr("Refresh rate")), self.refresh_slow()))

    def on_updates(self):
        if self.updates is None:
            self.updates = updates.UpdatesWindow(self, VERSION)
        self.updates.show()
        self.updates.raise_()
        self.updates.activateWindow()
        self.updates.load()

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
            QtWidgets.QApplication.quit()
        self.bg(job, then=done)

    def on_setup(self):
        if self.setup is None:
            self.setup = setup.SetupWindow(self)
        else:
            self.setup.refresh()
        self.setup.show()
        self.setup.raise_()
        self.setup.activateWindow()

    def first_run_setup(self):
        """Opens Setup at start when something required or recommended is missing (until 'Later'
        for this version)."""
        if hw.remove_kwin_limits() and self.tray:
            self.tray.showMessage(APP, tr("Log out once to get the HDMI / USB-C video ports back: "
                                  "\"Eco without logout\" is not needed with Cardwire."),
                                  QtWidgets.QSystemTrayIcon.Information, 8000)
        if self.cfg.get("setup_later") == VERSION:
            return
        self.bg(setup.checks, then=lambda rows: setup.needs_setup(rows) and self.on_setup())

    def after_setup(self):
        """Setup changed services, packages or the key rule: pick them up."""
        self.refresh_slow()
        self.hotkeys.start()
        if self.extra is not None:
            self.extra.refresh()

    def on_extra(self):
        if self.extra is None:
            self.extra = ExtraWindow(self)
        self.extra.show()
        self.extra.raise_()
        self.extra.activateWindow()

    def save(self):
        save_config(self.cfg)

    # -- key bindings ---------------------------------------------------------------
    def on_hotkeys_state(self, state):
        self.hotkeys_state = state
        if self.extra:
            self.extra.build_bindings()

    def on_hotkey_seen(self, key):
        seen = self.cfg.setdefault("seen_keys", [])
        if key not in seen:
            seen.append(key)
            self.save()
            if self.extra:
                self.extra.build_bindings()

    KBD_HW_CHANGED = "/sys/class/leds/asus::kbd_backlight/brightness_hw_changed"

    def capture_laptop_key(self):
        """Add -> Laptop key: the next ASUS key pressed becomes a bindable row.
        Some Fn keys never reach Linux (Fn+F2/F3: the keyboard firmware changes the light
        itself), so the dialog watches for that and explains instead of waiting forever."""
        self.hotkeys.capturing = True
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information, tr("Add laptop key"),
                                    tr("Press the laptop key (Fn + ...) you want to bind."),
                                    QtWidgets.QMessageBox.Cancel, self.extra or self)
        box.rejected.connect(self.end_capture)
        self.capture_box = box
        self.capture_light = hw._read(self.KBD_HW_CHANGED)
        self.capture_ticks = 0
        self.capture_timer = QtCore.QTimer(self, interval=300, timeout=self.capture_tick)
        self.capture_timer.start()
        box.open()

    def capture_tick(self):
        if not self.capture_box:
            return
        self.capture_ticks += 1
        light = hw._read(self.KBD_HW_CHANGED)
        if light != self.capture_light:
            self.capture_fail(tr("This key is handled by the keyboard's own firmware (it changes the "
                                 "backlight by itself) and never reaches Linux, so it cannot be rebound."))
        elif self.capture_ticks >= 34:  # ~10 s
            self.capture_fail(tr("No laptop key arrived. That key is either handled by the firmware "
                                 "itself or sent as a normal key combination.") + "\n\n" +
                              tr("Use Add -> Keyboard shortcut for normal key combinations."))

    def capture_fail(self, text):
        box = self.capture_box
        self.end_capture()
        if box:
            box.done(0)
        QtWidgets.QMessageBox.information(self.extra or self, tr("Add laptop key"), text)

    def end_capture(self):
        self.hotkeys.capturing = False
        self.capture_box = None
        timer = getattr(self, "capture_timer", None)
        if timer:
            timer.stop()

    def on_key_captured(self, scan, label):
        box = self.capture_box
        self.end_capture()
        if box:
            box.done(0)
        builtin = hotkeys.SCAN_TO_KEY.get(scan)
        name = builtin or f"scan_{scan:02X}"
        if builtin:
            self.on_hotkey_seen(builtin)
        elif name not in self.cfg.get("custom_keys", {}):
            self.cfg.setdefault("custom_keys", {})[name] = {"scan": scan, "label": label}
            self.save()
            if self.extra:
                self.extra.build_bindings()
        else:
            label = self.cfg["custom_keys"][name]["label"]
        if builtin:
            label = hotkeys.KEYS[builtin][0]
        QtWidgets.QMessageBox.information(self.extra or self, tr("Add laptop key"),
                                          tr("{key} is in the list. Pick what it should do.", key=label))

    def shortcut_description(self, sid):
        n = list(self.cfg.get("shortcuts", {})).index(sid) + 1 if sid in self.cfg.get("shortcuts", {}) else 0
        return f"asus-tso-helper custom key {n}"

    def add_shortcut(self):
        """Add -> Keyboard shortcut: pick keys here, the desktop confirms and owns them."""
        dlg = QtWidgets.QDialog(self.extra or self)
        dlg.setWindowTitle(tr("Add keyboard shortcut"))
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(QtWidgets.QLabel(tr("Press the key combination, then OK.\n"
                                       "KDE will ask once to confirm it.")))
        edit = QtWidgets.QKeySequenceEdit()
        edit.setMaximumSequenceLength(1)
        lay.addWidget(edit)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QtWidgets.QDialog.Accepted or edit.keySequence().isEmpty():
            return
        seq = edit.keySequence().toString(QtGui.QKeySequence.PortableText)
        sid = "user_" + secrets.token_hex(4)
        self.cfg.setdefault("shortcuts", {})[sid] = {"trigger": ""}
        self.save()
        self.portal_busy = True
        self.portal.bind([(sid, self.shortcut_description(sid), hotkeys.to_portal_trigger(seq))])

    def on_shortcuts_bound(self, triggers):
        self.portal_busy = False
        known = self.cfg.get("shortcuts", {})
        for sid, trigger in triggers.items():
            if sid in known:
                known[sid]["trigger"] = trigger
        self.save()
        if self.extra:
            self.extra.build_bindings()

    def on_shortcut(self, sid):
        action = self.hotkeys.binding(sid)
        if not action:
            return
        code = hotkeys.KEY_ACTIONS.get(action)
        if code is not None and self.hotkeys.send_key(code):
            return
        self.on_hotkey(action, sid)

    def remove_key(self, key):
        self.cfg.get("custom_keys", {}).pop(key, None)
        if self.cfg.get("shortcuts", {}).pop(key, None) is not None:
            hw.run("busctl", "--user", "call", "org.kde.kglobalaccel", "/kglobalaccel",
                   "org.kde.KGlobalAccel", "unregister", "ss", shortcuts.APP_ID, key, timeout=5)
        self.cfg.pop(f"key_{key}", None)
        self.cfg.pop(f"key_{key}_cmd", None)
        self.save()
        if self.extra:
            self.extra.build_bindings()

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

    def enable_hotkeys(self):
        self.bg(hotkeys.install_rule, then=lambda r: (self.report(r, tr("Enabling Key Bindings")),
                                                     QtCore.QTimer.singleShot(1500, self.hotkeys.start)))

    def on_hotkey(self, action, key):
        """InputDispatcher.KeyProcess for the actions that are not a plain key press."""
        def spawn(*cmd):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
        if action == "aura":
            i = (self.aura_combo.currentIndex() + 1) % self.aura_combo.count()
            self.aura_combo.setCurrentIndex(i)
            self.apply_aura()
            self.toast("input-keyboard-brightness", self.aura_combo.currentText())
        elif action == "performance":  # Modes.GetNext: Silent, Balanced, Turbo, then custom modes
            order = [m[0] for m in modes.all_modes(self.cfg)]
            current = self.cfg.get("active_mode") or hw.get_profile()
            nxt = order[(order.index(current) + 1) % len(order)] if current in order else "balanced"
            self.on_profile(nxt, notify=True)
        elif action.startswith("mode:"):
            if action[5:] in [m[0] for m in modes.all_modes(self.cfg)]:
                self.on_profile(action[5:], notify=True)
        elif action == "screen":
            spawn("kscreen-doctor", "--dpms", "off")
        elif action == "lock":
            spawn("loginctl", "lock-session")
        elif action == "screenshot":
            spawn("spectacle")
        elif action == "calculator":
            spawn("kcalc")
        elif action == "ghelper":
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()
        elif action == "custom":
            cmd = self.cfg.get(f"key_{key}_cmd", "").strip()
            if cmd:
                spawn("sh", "-c", cmd)

    def apply_topmost(self):
        on = bool(self.cfg.get("topmost"))
        if bool(self.windowFlags() & QtCore.Qt.WindowStaysOnTopHint) != on:
            visible = self.isVisible()
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, on)
            if visible:
                self.show()

    def pick_colour(self):
        colour = QtWidgets.QColorDialog.getColor(
            QtGui.QColor("#" + self.cfg.get("aura_colour", "ffffff")), self, tr("Color"))
        if colour.isValid():
            self.cfg["aura_colour"] = colour.name()[1:]
            self.colour_button.set_swatch(colour)
            self.apply_aura()

    def apply_aura(self):
        self.cfg["aura_effect"] = self.aura_combo.currentData()
        save_config(self.cfg)
        self.bg(hw.set_aura, self.cfg["aura_effect"], self.cfg.get("aura_colour", "ffffff"),
                self.cfg.get("aura_speed", "med"), then=lambda r: self.report(r, tr("Keyboard lighting")))

    def on_limit(self, percent):
        if self.cfg.pop("full_once", None) is not None:
            self.cfg.pop("limit_before_full", None)
            save_config(self.cfg)
        self.bg(hw.set_charge_limit, percent, then=lambda r: self.report(r, tr("Charge limit")))

    def on_full_charge(self):
        """BatteryControl.ToggleBatteryLimitFull: charge to 100% once, then restore the limit."""
        if self.cfg.get("full_once"):
            self.end_full_charge()
            return
        self.cfg["limit_before_full"] = self.slider.value
        self.cfg["full_once"] = True
        save_config(self.cfg)
        self.slider.set_value(100)
        self.show_limit(100)
        self.full_button.set_activated(True)
        # asusd puts the limit back on unplug even without this app; at 100% the app does it
        self.bg(hw.one_shot_full_charge, then=lambda r: self.report(r, tr("Charge limit")))

    def end_full_charge(self):
        limit = self.cfg.pop("limit_before_full", 80)
        self.cfg.pop("full_once", None)
        save_config(self.cfg)
        self.full_button.set_activated(False)
        self.bg(hw.set_charge_limit, limit, then=lambda r: (self.report(r, tr("Charge limit")), self.refresh_fast()))

    def on_credits(self):
        QtWidgets.QMessageBox.about(
            self, tr("Credits"),
            f"<b>{APP}</b> {VERSION}<br><br>"
            + tr("A Linux port of {ghelper} by seerge (GPL-3.0): its interface, layout and behaviour are "
                 "seerge's work.", ghelper="<a href='https://github.com/seerge/g-helper'>G-Helper</a>") + "<br>"
            + tr("Hardware control goes through {tools}.",
                 tools="<a href='https://asus-linux.org'>asusctl</a> &amp; "
                       "<a href='https://opengamingcollective.github.io/cardwire/'>Cardwire</a>") + "<br>"
            + tr("Icons: {icons}.", icons="<a href='https://lucide.dev'>Lucide</a> (ISC)") + "<br><br>"
            + (tr("Like it? {support}, and support {ghelper} too.",
                  support=f"<a href='{DONATE_URL}'>{tr('Support the project')}</a>",
                  ghelper="<a href='https://github.com/seerge/g-helper'>G-Helper</a>") + "<br><br>"
               if DONATE_URL else "")
            + tr("Not affiliated with or endorsed by ASUS. ASUS, ROG and TUF are trademarks of ASUSTeK Computer Inc."))

    def on_startup(self, on):
        if on:
            os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
            # the AppImage file or the installed command, so autostart survives moving the source
            icon = "asus-tso-helper" if hw.APPIMAGE else os.path.join(w.ASSETS, "asus-tso-helper.png")
            with open(AUTOSTART, "w") as f:
                f.write("[Desktop Entry]\nType=Application\nName=asus-tso-helper\n"
                        f"Exec=\"{hw.launcher()}\" --minimized\nIcon={icon}\n"
                        "X-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(AUTOSTART):
            os.remove(AUTOSTART)

    def closeEvent(self, event):
        if self.tray_available:
            event.ignore()
            self.hide()
            if not self.cfg.get("tray_hint_shown") and self.tray:
                self.cfg["tray_hint_shown"] = True
                self.save()
                self.tray.showMessage(APP, tr("Still running in the tray. Use Quit to close it."),
                                      QtGui.QIcon(w.APP_ICON), 5000)
        else:
            event.accept()
            QtWidgets.QApplication.quit()


class Tray(QtWidgets.QSystemTrayIcon):
    """Tray icon shows the GPU mode in its colour (tray-eco / standard / ultimate), like VisualiseIcon()."""

    ICONS = {"Integrated": "tray-eco.svg", "Hybrid": "tray-standard.svg", "AsusMuxDgpu": "tray-ultimate.svg"}

    def __init__(self, window):
        super().__init__(QtGui.QIcon(w.APP_ICON))
        self.window = window
        self.gpu = None
        self.menu = QtWidgets.QMenu()
        self.mode_actions = {}
        self.build_menu()
        self.menu.aboutToShow.connect(self.sync_menu)
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)
        self.set_gpu("Hybrid")
        self.apply_theme()

    def build_menu(self):
        """Settings.SetContextMenu: modes (custom ones too), GPU modes, Quit."""
        window = self.window
        self.menu.clear()
        title = self.menu.addAction(tr("Mode"))
        title.setEnabled(False)
        self.mode_actions = {}
        for key, label, _ in modes.all_modes(window.cfg):
            act = self.menu.addAction(label, lambda k=key: window.on_profile(k))
            act.setCheckable(True)
            self.mode_actions[key] = act
        self.menu.addSeparator()
        title = self.menu.addAction(tr("GPU Mode"))
        title.setEnabled(False)
        for key, label, *_ in GPU_MODES:
            if key in window.gpu_buttons:
                self.menu.addAction(label, lambda k=key: window.on_gpu(k))
        if window.optimized:
            self.menu.addAction(tr("Optimized"), window.on_optimized)
        self.menu.addSeparator()
        self.menu.addAction(tr("Quit"), QtWidgets.QApplication.quit)

    def apply_theme(self):
        self.menu.setStyleSheet(stylesheet())

    def sync_menu(self):
        current = self.window.cfg.get("active_mode") or hw.get_profile()
        for key, act in self.mode_actions.items():
            act.setChecked(key == current)

    def set_gpu(self, mode):
        if mode == self.gpu or mode not in self.ICONS:
            return
        self.gpu = mode
        self.setIcon(QtGui.QIcon(os.path.join(w.ASSETS, self.ICONS[mode])))

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self.show_window()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setDesktopFileName(APP)
    app.setQuitOnLastWindowClosed(False)
    hw.kwin_place_window()
    hw.integrate_desktop()
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSizeF(9)  # Segoe UI 9pt
    app.setFont(font)
    # one instance, like G-Helper: a second launch only brings the running window up
    server_name = f"{APP}-{os.getuid()}"
    probe = QtNetwork.QLocalSocket()
    probe.connectToServer(server_name)
    if probe.waitForConnected(500):
        if "--minimized" not in sys.argv:
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(500)
        probe.disconnectFromServer()
        sys.exit(0)
    QtNetwork.QLocalServer.removeServer(server_name)  # stale socket from a crash
    server = QtNetwork.QLocalServer()
    server.listen(server_name)

    tray_ok = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()
    window = MainWindow(tray_ok)
    if os.path.exists(AUTOSTART):
        window.on_startup(True)  # points at this copy (e.g. an AppImage that was moved)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def on_data():
            if bytes(conn.readAll()).startswith(b"show"):
                window.show()
                window.raise_()
                window.activateWindow()
            conn.disconnectFromServer()
        conn.readyRead.connect(on_data)
    server.newConnection.connect(on_connection)
    if tray_ok:
        window.tray = Tray(window)
        window.tray.show()
        window.apply_theme()
    if "--minimized" not in sys.argv or not tray_ok:
        window.show()
    QtCore.QTimer.singleShot(1500, window.first_run_setup)
    sys.exit(app.exec())
