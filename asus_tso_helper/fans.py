"""'Fans and Power' window: the G-Helper Fans form (app/Fans.Designer.cs, app/Fans.cs).

Left column: CPU / GPU tabs with power-limit sliders. Right column: the mode picker and
draggable 8-point fan curves for the CPU and GPU fans, edited for the active mode.
Fan curves go through `asusctl fan-curve`; power limits through asusd, which keeps them
per mode and per power source (battery / plugged) and re-applies them on mode changes.
"""
from PySide6 import QtCore, QtGui, QtWidgets

from . import backend as hw
from . import modes as custom
from . import widgets as w
from .widgets import CUSTOM, ECO, STANDARD, TURBO, with_alpha

TEMP_MIN, TEMP_MAX = 20, 110  # Fans.cs tempMin / tempMax
FAN_MIN_RPM = 1800             # FanSensorControl.DEFAULT_FAN_MIN (18) * 100
FAN_MAX_RPM = 5800             # FanSensorControl.DEFAULT_FAN_MAX (58) * 100
INADEQUATE_RPM = 10400         # FanSensorControl.INADEQUATE_MAX (104) * 100
CAL_STEPS = [90, 80, 70, 60, 50, 40, 30, 20, 10, 0]  # fan power steps measured after the max


def flat_curve(duty):
    """A curve holding the fan at one power level at every temperature."""
    return [(t, duty) for t in range(20, 100, 10)]


def fan_max(cfg, fan):
    """Max RPM measured by Calibrate (or raised by readings above it); G-Helper's default otherwise."""
    return cfg.get(f"fan_max_{fan}", FAN_MAX_RPM)


# AppConfig.GetDefaultCurve, after FixFanCurve with "clamp fan dots": the curves Windows
# G-Helper falls back to. They are generic ROG curves, not this laptop's firmware ones.
_GH_T = {"balanced": [30, 50, 60, 64, 72, 80, 90, 100],
         "performance": [30, 50, 60, 70, 76, 80, 90, 100],
         "quiet": [30, 49, 59, 66, 71, 80, 90, 100]}
GHELPER_DEFAULTS = {
    "balanced": {"cpu": list(zip(_GH_T["balanced"], [0, 8, 17, 22, 34, 41, 48, 69])),
                 "gpu": list(zip(_GH_T["balanced"], [0, 12, 22, 29, 38, 45, 52, 74]))},
    "performance": {"cpu": list(zip(_GH_T["performance"], [17, 26, 34, 41, 52, 67, 81, 90])),
                    "gpu": list(zip(_GH_T["performance"], [22, 31, 38, 45, 57, 71, 85, 95]))},
    "quiet": {"cpu": list(zip(_GH_T["quiet"], [0, 0, 3, 12, 20, 28, 34, 41])),
              "gpu": list(zip(_GH_T["quiet"], [0, 0, 4, 17, 27, 35, 40, 45]))},
}


def snapshot_factory_curves(cfg):
    """Remember the firmware's own curves once, while they are still untouched.
    asusd's reset (pwm_enable=3) cannot be trusted on every model: on the FA507NV it
    returns the Balanced table for Turbo, so Factory Defaults restores this copy instead."""
    if cfg.get("factory_curves"):
        return False
    snap = {}
    for profile, _ in MODE_NAMES:
        curves = hw.get_fan_curves(profile)
        if not curves or any(c["enabled"] for c in curves.values()):
            return False  # customised already: better no snapshot than a wrong one
        snap[profile] = {fan: c["points"] for fan, c in curves.items()}
    cfg["factory_curves"] = snap
    return True


def fan_table(cfg, fan, profile):
    """[(power %, rpm)] measured by Calibrate in `profile`, sorted, rpm forced non-decreasing;
    None if that mode is not calibrated. Per mode, because the firmware treats the same power
    differently: in Turbo the fans never drop below ~2600 RPM, in Silent they can stop."""
    raw = cfg.get(f"fan_table_{profile}_{fan}")
    if not raw or len(raw) < 2:
        return None
    table, top = [], 0
    for duty, rpm in sorted((float(d), float(r)) for d, r in raw):
        top = max(top, rpm)
        table.append((duty, top))
    return table


def power_to_speed(cfg, fan, profile, power):
    """Fan power (what the firmware curve holds) -> % of max speed (what the fan really does).
    The two differ a lot: on this TUF 30% power already spins the fan at ~50% of its max RPM."""
    table = fan_table(cfg, fan, profile)
    if not table:
        return power
    rpm = table[-1][1]
    for (d0, r0), (d1, r1) in zip(table, table[1:]):
        if power <= d1:
            rpm = r0 + (r1 - r0) * (power - d0) / (d1 - d0) if d1 > d0 else r1
            break
    return min(100.0, rpm * 100 / fan_max(cfg, fan))


def speed_to_power(cfg, fan, profile, speed):
    """Inverse of power_to_speed: the power that makes the fan reach `speed` % of max RPM."""
    table = fan_table(cfg, fan, profile)
    if not table:
        return speed
    if speed <= 0:
        return 0
    rpm = speed * fan_max(cfg, fan) / 100
    for (d0, r0), (d1, r1) in zip(table, table[1:]):
        if rpm <= r1:
            if r1 <= r0:
                return d1
            return max(0.0, d0 + (d1 - d0) * (rpm - r0) / (r1 - r0))
    return 100


def restore_after_calibration(cfg):
    """Put back the curves and the mode saved before calibrating. Also run at startup,
    so a crash mid-calibration never leaves the fans pinned at 100%."""
    backup = cfg.get("calibration_backup")
    if not backup:
        return True, ""
    result = (True, "")
    target = backup.get("target", "performance")
    for fan, curve in backup["curves"].items():
        ok, out = hw.set_fan_curve(target, fan, curve["points"])
        if ok:
            ok, out = hw.enable_fan_curve(target, fan, curve["enabled"])
        if not ok:
            result = (ok, out)
    if backup.get("profile"):
        hw.set_profile(backup["profile"])
    return result

WIN_ACCENT = QtGui.QColor(0, 120, 215)

MODE_NAMES = [("quiet", "Silent"), ("balanced", "Balanced"), ("performance", "Turbo")]
PPT = [("ppt_pl1_spl", "SPL (CPU sustained)"),
       ("ppt_pl2_sppt", "sPPT (CPU long boost)"),
       ("ppt_pl3_fppt", "fPPT (CPU short boost)")]


class TrackBar(QtWidgets.QWidget):
    """RTrackBar: a Windows trackbar with ticks on top (TickStyle.TopLeft) and a pointer thumb."""

    released = QtCore.Signal(int)
    valueChanged = QtCore.Signal(int)

    def __init__(self, minimum, maximum, value, tick=5):
        super().__init__()
        self.min, self.max, self.value, self.tick = minimum, maximum, value, tick
        self.dragging = False
        self.setFixedHeight(32)
        self.setAttribute(QtCore.Qt.WA_Hover)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def set_range(self, lo, hi):
        self.min, self.max = lo, hi
        self.update()

    def set_value(self, v, emit=False):
        v = max(self.min, min(self.max, int(round(v))))
        if v != self.value:
            self.value = v
            self.update()
            if emit:
                self.valueChanged.emit(v)

    def _x(self, v):
        span = max(1, self.max - self.min)
        return 8 + (self.width() - 16) * (v - self.min) / span

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        t = w.THEME
        # ticks
        p.setPen(QtGui.QPen(t.control_dark, 1))
        if self.max > self.min:
            v = self.min
            while v <= self.max:
                x = round(self._x(v)) + 0.5
                p.drawLine(QtCore.QPointF(x, 3), QtCore.QPointF(x, 7))
                v += self.tick
        # channel
        cy = 19
        p.fillRect(QtCore.QRectF(8, cy - 2, self.width() - 16, 4), t.chart_grid)
        # pointer thumb (points up, towards the ticks)
        x = self._x(self.value)
        colour = WIN_ACCENT if self.isEnabled() else t.control_dark
        if self.underMouse() or self.dragging:
            colour = colour.lighter(115)
        path = QtGui.QPainterPath()
        path.moveTo(x, cy - 10)
        path.lineTo(x + 5, cy - 5)
        path.lineTo(x + 5, cy + 9)
        path.lineTo(x - 5, cy + 9)
        path.lineTo(x - 5, cy - 5)
        path.closeSubpath()
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(colour)
        p.drawPath(path)

    def _from_pos(self, px):
        span = self.width() - 16
        self.set_value(self.min + (px - 8) / max(1, span) * (self.max - self.min), emit=True)

    def mousePressEvent(self, e):
        self.dragging = True
        self._from_pos(e.position().x())

    def mouseMoveEvent(self, e):
        if self.dragging:
            self._from_pos(e.position().x())

    def mouseReleaseEvent(self, e):
        self.dragging = False
        self.update()
        self.released.emit(self.value)

    def keyPressEvent(self, e):
        delta = {QtCore.Qt.Key_Left: -1, QtCore.Qt.Key_Down: -1,
                 QtCore.Qt.Key_Right: 1, QtCore.Qt.Key_Up: 1}.get(e.key())
        if delta is None:
            return super().keyPressEvent(e)
        self.set_value(self.value + delta, emit=True)

    def keyReleaseEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right, QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
            self.released.emit(self.value)


class SliderPanel(QtWidgets.QWidget):
    """panelCPU / panelGPUTemp...: grey caption left, bold value right, trackbar below."""

    released = QtCore.Signal(int)

    def __init__(self, caption, lo, hi, value, unit, tick=5):
        super().__init__()
        self.unit = unit
        self.setFixedHeight(62)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(3, 4, 3, 0)
        lay.setSpacing(2)
        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(2, 0, 2, 0)
        self.caption = QtWidgets.QLabel(caption)
        self.value_label = QtWidgets.QLabel("")
        f = self.value_label.font()
        f.setBold(True)
        self.value_label.setFont(f)
        top.addWidget(self.caption)
        top.addStretch()
        top.addWidget(self.value_label)
        lay.addLayout(top)
        self.track = TrackBar(lo, hi, value, tick)
        self.track.valueChanged.connect(self.show_value)
        self.track.released.connect(self.released)
        lay.addWidget(self.track)
        lay.addStretch()
        self.show_value(value)

    def show_value(self, v):
        self.value_label.setText(f"{v}{self.unit}")

    def set(self, lo, hi, value):
        self.track.set_range(lo, hi)
        self.track.set_value(value)
        self.show_value(self.track.value)


class Title(QtWidgets.QWidget):
    """panelTitleCPU / panelTitleGPU: icon at (5, 9), bold label at (23, 8)."""

    def __init__(self, icon_name, text, height=30):
        super().__init__()
        self.icon_name = icon_name
        self.setFixedHeight(height)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(25, 0, 0, 0)
        self.label = QtWidgets.QLabel(text)
        f = self.label.font()
        f.setBold(True)
        self.label.setFont(f)
        lay.addWidget(self.label)
        lay.addStretch()
        self.right = lay

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.drawPixmap(QtCore.QPointF(5, (self.height() - 16) / 2), w.icon(self.icon_name))


class ApplyCheck(QtWidgets.QCheckBox):
    """checkApplyPower / checkApplyFans: a checkbox on a ButtonSecond strip."""

    def __init__(self, text):
        super().__init__(text)
        self.setFixedHeight(23)
        self.setObjectName("apply")


class FanChart(QtWidgets.QWidget):
    """RChart line series with 8 draggable points: X = temperature 20..110, Y = fan 0..100%.
    Clicking the Y axis toggles its labels between percent and RPM, like Fans.ChartCPU_MouseClick."""

    edited = QtCore.Signal()
    axis_clicked = QtCore.Signal()

    def __init__(self, title, colour):
        super().__init__()
        self.title = title
        self.colour = colour
        self.rpm = False
        self.fan_max = FAN_MAX_RPM
        self.calibrated = False
        self.min_speed = 0
        self.clamp = False
        self.points = []
        self.active = True
        self.drag = None
        self.tip = None
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def set_points(self, points, active):
        self.points = [list(p) for p in points]
        # Fans.LoadProfile: firmware curves repeat the last point; nudge duplicates apart
        for i in range(1, len(self.points)):
            if self.points[i][0] <= self.points[i - 1][0]:
                self.points[i][0] = self.points[i - 1][0] + 1
        self.active = active
        self.update()

    def _area(self):
        fm = QtGui.QFontMetrics(self._axis_font())
        left = fm.horizontalAdvance("10000") + 8
        return QtCore.QRectF(left, 22, self.width() - left - 10, self.height() - 22 - fm.height() - 8)

    def y_label(self, pct, unit=""):
        """Fans.ChartYLabel."""
        if pct == 0:
            return "OFF"
        if self.rpm and self.calibrated:
            return f"{100 * round(self.fan_max * pct / 10000)}{unit}"  # Y is real % of max speed
        if self.rpm:
            return f"{200 * int((FAN_MIN_RPM + (self.fan_max - FAN_MIN_RPM) * pct / 100) // 200)}{unit}"
        return f"{round(pct)}%"

    def _axis_font(self):
        f = QtGui.QFont(self.font())
        f.setPointSizeF(7)
        return f

    def _to_px(self, t, p):
        a = self._area()
        return QtCore.QPointF(a.left() + a.width() * (t - TEMP_MIN) / (TEMP_MAX - TEMP_MIN),
                              a.bottom() - a.height() * p / 100)

    def _from_px(self, pt):
        a = self._area()
        t = TEMP_MIN + (pt.x() - a.left()) / a.width() * (TEMP_MAX - TEMP_MIN)
        p = (a.bottom() - pt.y()) / a.height() * 100
        return t, p

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        t = w.THEME
        chart_main = QtGui.QColor(35, 35, 35) if t.dark else t.button_main
        p.fillRect(self.rect(), chart_main)
        p.setPen(t.fore)
        p.drawText(QtCore.QRectF(0, 3, self.width(), 18), QtCore.Qt.AlignCenter, self.title)

        a = self._area()
        p.setFont(self._axis_font())
        fm = QtGui.QFontMetrics(self._axis_font())
        grid = QtGui.QPen(t.chart_grid, 1)
        for v in range(0, 101, 10):
            y = round(a.bottom() - a.height() * v / 100) + 0.5
            p.setPen(grid)
            p.drawLine(QtCore.QPointF(a.left(), y), QtCore.QPointF(a.right(), y))
            p.setPen(t.fore)
            p.drawText(QtCore.QRectF(0, y - 8, a.left() - 4, 16),
                       QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self.y_label(v))
        for c in range(TEMP_MIN, TEMP_MAX + 1, 10):
            x = round(a.left() + a.width() * (c - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) + 0.5
            p.setPen(grid)
            p.drawLine(QtCore.QPointF(x, a.top()), QtCore.QPointF(x, a.bottom()))
            p.setPen(t.fore)
            p.drawText(QtCore.QRectF(x - 15, a.bottom() + 3, 30, fm.height()), QtCore.Qt.AlignCenter, str(c))

        if self.calibrated and self.min_speed > 1:
            floor_y = a.bottom() - a.height() * self.min_speed / 100
            band = QtCore.QRectF(a.left(), floor_y, a.width(), a.bottom() - floor_y)
            p.fillRect(band, with_alpha(t.fore, 18))
            p.setPen(t.gray_text)
            p.drawText(band.adjusted(6, 0, -6, -2), QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                       "fan minimum in this mode")

        if not self.points:
            return
        colour = self.colour if self.active else QtGui.QColor(128, 128, 128)
        pts = [self._to_px(*pt) for pt in self.points]
        p.setPen(QtGui.QPen(colour, 2))
        p.drawPolyline(pts)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(colour)
        for pt in pts:
            p.drawEllipse(pt, 4, 4)

        if self.tip is not None:
            i = self.tip
            text = f"{round(self.points[i][0])}°C, {self.y_label(self.points[i][1], ' RPM')}"
            box = QtCore.QRectF(0, 0, fm.horizontalAdvance(text) + 10, fm.height() + 6)
            anchor = pts[i]
            box.moveTo(min(anchor.x() + 8, self.width() - box.width() - 4), max(anchor.y() - box.height() - 6, 2))
            p.setBrush(t.button_main)
            p.setPen(QtGui.QPen(t.border_main, 1))
            p.drawRect(box)
            p.setPen(t.fore)
            p.drawText(box, QtCore.Qt.AlignCenter, text)

    def _nearest(self, pos):
        best, dist = None, 12
        for i, pt in enumerate(self.points):
            d = (self._to_px(*pt) - pos).manhattanLength()
            if d < dist:
                best, dist = i, d
        return best

    def mousePressEvent(self, e):
        if e.position().x() < self._area().left():
            self.axis_clicked.emit()
            return
        self.drag = self._nearest(e.position())
        self.tip = self.drag
        self.update()

    def mouseMoveEvent(self, e):
        if self.drag is None:
            near = self._nearest(e.position())
            self.setCursor(QtCore.Qt.SizeAllCursor if near is not None else QtCore.Qt.ArrowCursor)
            return
        i = self.drag
        temp, pct = self._from_px(e.position())
        lo = self.points[i - 1][0] + 1 if i > 0 else TEMP_MIN
        hi = self.points[i + 1][0] - 1 if i < len(self.points) - 1 else TEMP_MAX
        if self.clamp:  # FixFanCurve with clamp: point i lives in [30 + 10i, 40 + 10i]
            lo, hi = max(lo, 30 + 10 * i), min(hi, 40 + 10 * i)
        temp = max(lo, min(hi, round(temp)))
        floor = self.min_speed if self.calibrated else 0
        pct = max(floor, min(100, round(pct)))
        self.points[i] = [temp, pct]
        # keep the curve non-decreasing, like G-Helper does while dragging
        for j in range(i + 1, len(self.points)):
            self.points[j][1] = max(self.points[j][1], pct)
        for j in range(i):
            self.points[j][1] = min(self.points[j][1], pct)
        self.active = True
        self.update()

    def mouseReleaseEvent(self, e):
        if self.drag is not None:
            self.drag = None
            self.tip = None
            self.update()
            self.edited.emit()


class FansWindow(QtWidgets.QWidget):
    def __init__(self, main):
        super().__init__(main, QtCore.Qt.Window)
        self.main = main
        self.profile = None
        self.calibration = None
        self.ac = None
        self.setWindowTitle(f"Fans and Power - {hw.cpu_name()}".rstrip(" -"))
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setFixedSize(675, 550)  # ClientSize 1350 x 1100

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_sliders())
        root.addWidget(self.build_fans(), 1)

        self.poll = QtCore.QTimer(self, interval=2000, timeout=self.check_profile)
        self.poll.start()

    # -- layout -----------------------------------------------------------------
    def build_sliders(self):
        col = QtWidgets.QWidget()
        col.setFixedWidth(265)
        lay = QtWidgets.QVBoxLayout(col)
        lay.setContentsMargins(5, 0, 0, 0)
        lay.setSpacing(0)

        nav = QtWidgets.QWidget()
        nl = QtWidgets.QHBoxLayout(nav)
        nl.setContentsMargins(2, 3, 2, 2)
        nl.setSpacing(4)
        self.nav_cpu = w.RButton("CPU", secondary=True, accent=STANDARD, radius=2)
        self.nav_gpu = w.RButton("GPU", secondary=True, accent=TURBO, radius=2)
        self.nav_adv = w.RButton("Advanced", secondary=True, accent=CUSTOM, radius=2)
        for i, b in enumerate((self.nav_cpu, self.nav_gpu, self.nav_adv)):
            b.setFixedHeight(29)
            b.clicked.connect(lambda _=False, k=i: self.show_tab(k))
            nl.addWidget(b, 1)
        lay.addWidget(nav)

        # CPU tab
        self.cpu_tab = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(self.cpu_tab)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cpu_title = Title("cpu", "Power Limits")
        self.power_source = QtWidgets.QLabel("")
        self.power_source.setObjectName("tip")
        cpu_title.right.addWidget(self.power_source)
        cpu_title.right.setContentsMargins(25, 0, 6, 0)
        cl.addWidget(cpu_title)
        self.ppt = {}
        for name, caption in PPT:
            rng = hw.armoury_range(name)
            if not rng:
                continue
            lo, hi, cur = rng
            panel = SliderPanel(caption, lo, hi, cur, "W")
            panel.released.connect(lambda v, n=name: self.on_ppt(n, v))
            panel.track.valueChanged.connect(lambda v, n=name: self.constrain_ppt(n, v))
            cl.addWidget(panel)
            self.ppt[name] = panel
        apply_box = QtWidgets.QWidget()
        al = QtWidgets.QVBoxLayout(apply_box)
        al.setContentsMargins(7, 7, 7, 7)
        self.apply_power = ApplyCheck("Apply Power Limits")
        self.apply_power.clicked.connect(self.on_apply_power)
        al.addWidget(self.apply_power)
        cl.addWidget(apply_box)
        cl.addStretch()
        lay.addWidget(self.cpu_tab)

        # GPU tab
        self.gpu_tab = QtWidgets.QWidget()
        gl = QtWidgets.QVBoxLayout(self.gpu_tab)
        gl.setContentsMargins(0, 0, 0, 9)
        gl.setSpacing(0)
        gl.addWidget(Title("gpu", hw.dgpu_name() or "GPU Settings"))
        self.gpu_sliders = {}
        for name, caption, unit in (("nv_dynamic_boost", "Dynamic Boost", "W"),
                                    ("nv_temp_target", "Temperature Target", "°C")):
            rng = hw.armoury_range(name)
            if not rng:
                continue
            lo, hi, cur = rng
            panel = SliderPanel(caption, lo, hi, cur, unit, tick=1 if hi - lo <= 15 else 5)
            panel.released.connect(lambda v, n=name: self.on_gpu_value(n, v))
            gl.addWidget(panel)
            self.gpu_sliders[name] = panel
        self.gpu_note = QtWidgets.QLabel("")
        self.gpu_note.setObjectName("tip")
        self.gpu_note.setWordWrap(True)
        self.gpu_note.setContentsMargins(5, 4, 5, 0)
        gl.addWidget(self.gpu_note)
        gl.addStretch()
        lay.addWidget(self.gpu_tab)

        # Advanced tab: G-Helper's Ryzen undervolt (Curve Optimizer) needs ryzen_smu here
        self.adv_tab = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(self.adv_tab)
        vl.setContentsMargins(0, 0, 0, 9)
        # G-Helper's "Power Mode" (Windows power slider) per mode = the CPU's EPP, kept by asusd
        vl.addWidget(Title("cpu", "Power Mode"))
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(7, 4, 7, 2)
        self.epp = w.RComboBox()
        for value, label in hw.EPP_CHOICES:
            self.epp.addItem(label, value)
        self.epp.setToolTip("How eagerly the CPU clocks up in this mode (energy performance preference).\n"
                            "Custom modes share it with their base mode.")
        self.epp.activated.connect(self.on_epp)
        row.addWidget(self.epp, 1)
        vl.addLayout(row)
        vl.addSpacing(8)
        vl.addWidget(Title("cpu", "Undervolting"))
        note = QtWidgets.QLabel("CPU / iGPU undervolting (Curve Optimizer) needs the ryzen_smu kernel "
                                "module and is not available in asus-tso-helper yet.\n\n"
                                "GPU clock offsets are not exposed by the NVIDIA driver on Wayland.")
        note.setObjectName("tip")
        note.setWordWrap(True)
        note.setContentsMargins(5, 4, 5, 0)
        vl.addWidget(note)
        vl.addStretch()
        lay.addWidget(self.adv_tab)
        lay.addStretch()
        self.show_tab(0)
        return col

    def build_fans(self):
        col = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 5, 0)
        lay.setSpacing(0)

        title = Title("fan", "BIOS Fan Curves", height=33)
        title.layout().setContentsMargins(27, 0, 2, 0)
        modes = QtWidgets.QWidget()
        modes.setFixedWidth(240)
        ml = QtWidgets.QHBoxLayout(modes)
        ml.setContentsMargins(0, 4, 2, 5)
        ml.setSpacing(3)
        self.remove_btn = w.RButton("", "circle-minus", secondary=True, radius=2)
        self.rename_btn = w.RButton("", "pencil", secondary=True, radius=2)
        add = w.RButton("", "circle-plus", secondary=True, radius=2)
        for b, tip, slot in ((self.remove_btn, "Remove this custom mode", self.on_remove_mode),
                             (self.rename_btn, "Rename this custom mode", self.on_rename_mode),
                             (add, "New custom mode from the current settings", self.on_add_mode)):
            b.setFixedSize(27, 23)
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            b.setToolTip(tip)
            b.clicked.connect(slot)
        self.combo = w.RComboBox()
        self.combo.activated.connect(self.on_mode)
        ml.addWidget(self.remove_btn)
        ml.addWidget(self.rename_btn)
        ml.addWidget(self.combo, 1)
        ml.addWidget(add)
        title.right.addWidget(modes)
        lay.addWidget(title)

        charts = QtWidgets.QWidget()
        chl = QtWidgets.QVBoxLayout(charts)
        chl.setContentsMargins(5, 0, 5, 2)
        chl.setSpacing(10)
        self.chart_cpu = FanChart("CPU Fan Profile, RPM/°C", STANDARD)
        self.chart_gpu = FanChart("GPU Fan Profile, RPM/°C", TURBO)
        for c, fan in ((self.chart_cpu, "cpu"), (self.chart_gpu, "gpu")):
            c.edited.connect(lambda f=fan: self.on_curve_edited(f))
            c.axis_clicked.connect(self.on_toggle_rpm)
            chl.addWidget(c, 1)
        lay.addWidget(charts, 1)
        # checkFanClamp: keep the 8 points on the 30..110 grid, one 10 degC slot each
        self.clamp = QtWidgets.QCheckBox("Clamp to Grid", self.chart_cpu)
        self.clamp.setObjectName("apply")
        self.clamp.move(6, 4)
        self.clamp.setChecked(bool(self.main.cfg.get("fan_clamp", True)))
        self.clamp.toggled.connect(self.on_clamp)
        for c in (self.chart_cpu, self.chart_gpu):
            c.clamp = self.clamp.isChecked()

        bottom = QtWidgets.QWidget()
        bottom.setFixedHeight(58)
        vl = QtWidgets.QVBoxLayout(bottom)
        vl.setContentsMargins(9, 1, 7, 12)
        vl.setSpacing(0)
        self.result = QtWidgets.QLabel("")  # labelFansResult
        self.result.setFixedHeight(16)
        vl.addWidget(self.result)
        vl.addStretch()
        bl = QtWidgets.QHBoxLayout()
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        vl.addLayout(bl)
        self.reset = w.RButton("Factory Defaults", secondary=True, radius=2)
        self.reset.setFixedSize(126, 27)
        self.reset.clicked.connect(self.on_reset_menu)
        self.calibrate = w.RButton("Calibrate", secondary=True, radius=2)
        self.calibrate.setFixedSize(70, 27)
        self.calibrate.setToolTip("Spins both fans at 100% for ~20 s to measure their real max RPM")
        self.calibrate.clicked.connect(self.on_calibrate)
        for b in (self.reset, self.calibrate):
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.apply_fans = ApplyCheck("Apply Fan Curve")
        self.apply_fans.clicked.connect(self.on_apply_fans)
        bl.addWidget(self.reset, 0, QtCore.Qt.AlignBottom)
        bl.addWidget(self.calibrate, 0, QtCore.Qt.AlignBottom)
        bl.addStretch()
        bl.addWidget(self.apply_fans, 0, QtCore.Qt.AlignBottom)
        lay.addWidget(bottom)
        return col

    def show_tab(self, index):
        for i, (b, tab) in enumerate(((self.nav_cpu, self.cpu_tab), (self.nav_gpu, self.gpu_tab),
                                      (self.nav_adv, self.adv_tab))):
            b.set_activated(index == i)
            tab.setVisible(index == i)

    def on_clamp(self, on):
        self.main.cfg["fan_clamp"] = on
        self.main.save()
        for c in (self.chart_cpu, self.chart_gpu):
            c.clamp = on

    # -- data -------------------------------------------------------------------
    def showEvent(self, e):
        self.load()
        super().showEvent(e)

    def check_profile(self):
        # asusd keeps limits per mode *and* per power source, and the firmware ranges change
        # with the charger too, so reload on either
        if self.isVisible() and (hw.get_profile() != self.profile or hw.ac_online() != self.ac):
            self.load()

    def load(self):
        if self.calibration:
            return
        self.profile = hw.get_profile()
        self.ac = hw.ac_online()
        self.power_source.setText("plugged in" if self.ac else "on battery")
        self.power_source.setToolTip("Limits are kept separately for each mode, "
                                     "on battery and when plugged in")
        self.init_axis()
        self.fill_modes()
        self.main.bg(lambda: hw.get_fan_curves(self.profile), then=self.show_curves)
        self.main.bg(self.read_power, then=self.show_power)
        self.main.bg(hw.get_profile_epp, self.profile, then=self.show_epp)

    def show_epp(self, value):
        self.epp.setEnabled(value is not None)
        index = self.epp.findData(value)  # 0 = "default": the kernel's choice, none selected
        self.epp.setCurrentIndex(index)

    def on_epp(self, _index):
        if self.profile in hw.EPP_PROP:
            self.main.bg(hw.set_profile_epp, self.profile, self.epp.currentData(),
                         then=lambda r: self.main.report(r, "Power mode"))

    def read_power(self):
        enabled = bool(hw.get_ppt_enabled())
        values = {}
        for name in list(self.ppt) + list(self.gpu_sliders):
            rng = hw.armoury_range(name)
            stored = hw.get_ppt(name) if name in self.ppt else None
            values[name] = (rng, stored)
        return enabled, values

    def show_power(self, data):
        enabled, values = data
        self.apply_power.setChecked(enabled)
        for name, panel in {**self.ppt, **self.gpu_sliders}.items():
            rng, stored = values[name]
            if not rng:
                continue
            lo, hi, cur = rng
            value = stored if enabled and stored is not None else cur
            panel.set(lo, hi, max(lo, min(hi, value)))
            panel.track.setEnabled(hi > lo)
        boost = values.get("nv_dynamic_boost", (None,))[0]
        self.gpu_note.setText("Dynamic Boost is locked by the firmware right now (often on battery)."
                              if boost and boost[0] == boost[1] else "")

    def show_curves(self, curves):
        """The firmware stores fan power; the charts show % of max speed (after Calibrate)."""
        cfg = self.main.cfg
        cpu, gpu = curves.get("cpu"), curves.get("gpu")
        enabled = bool((cpu and cpu["enabled"]) or (gpu and gpu["enabled"]))
        self.apply_fans.setChecked(enabled)
        for chart, fan, curve in ((self.chart_cpu, "cpu", cpu), (self.chart_gpu, "gpu", gpu)):
            if curve:
                chart.min_speed = power_to_speed(cfg, fan, self.profile, 0)
                chart.set_points([(t, power_to_speed(cfg, fan, self.profile, p)) for t, p in curve["points"]],
                                 enabled)

    def set_result(self, text, error=True):
        self.result.setText(text)
        self.result.setStyleSheet("color: red;" if error else f"color: {w.THEME.gray_text.name()};")

    # -- actions ----------------------------------------------------------------
    # -- custom modes (Fans.ButtonAdd / Rename / Remove) ------------------------------
    def fill_modes(self):
        cfg = self.main.cfg
        current = cfg.get("active_mode") or self.profile
        self.combo.clear()
        for key, name, _ in custom.all_modes(cfg):
            self.combo.addItem(name, key)
        self.combo.setCurrentIndex(max(0, self.combo.findData(current)))
        is_custom = custom.get(cfg, current) is not None
        self.remove_btn.setVisible(is_custom)
        self.rename_btn.setVisible(is_custom)

    def on_mode(self):
        key = self.combo.currentData()
        if key != (self.main.cfg.get("active_mode") or self.profile):
            self.main.on_profile(key)

    def on_add_mode(self):
        cfg = self.main.cfg

        def job():
            mode = custom.add(cfg)
            result = custom.activate(cfg, mode["id"])
            self.main.save()
            return result
        self.main.bg(job, then=lambda r: (self.main.report(r, "New mode"), self.main.refresh_fast(),
                                          self.main.modes_changed()))

    def on_rename_mode(self):
        mode = custom.active(self.main.cfg)
        if not mode:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "Rename mode", "Name:", text=mode["name"])
        if ok and name.strip():
            mode["name"] = name.strip()
            self.main.save()
            self.main.refresh_fast()
            self.main.modes_changed()

    def on_remove_mode(self):
        """Fans.ButtonRemove: drop the custom mode and go back to Balanced."""
        mode = custom.active(self.main.cfg)
        if not mode:
            return
        cfg = self.main.cfg

        def job():
            custom.remove(cfg, mode["id"])
            self.main.save()
            return hw.set_profile("balanced")
        self.main.bg(job, then=lambda r: (self.main.report(r, "Remove mode"), self.main.refresh_fast(),
                                          self.main.modes_changed()))

    def remember(self, **edit):
        """Edits while a custom mode is on belong to that mode."""
        if custom.active(self.main.cfg):
            custom.remember_edit(self.main.cfg, **edit)
            self.main.save()

    def on_curve_edited(self, fan):
        chart = self.chart_cpu if fan == "cpu" else self.chart_gpu
        points = [(t, speed_to_power(self.main.cfg, fan, self.profile, p)) for t, p in chart.points]
        profile = self.profile
        self.remember(curves={fan: points}, fans_on=True)
        self.apply_fans.setChecked(True)
        self.chart_cpu.active = self.chart_gpu.active = True
        self.chart_cpu.update()
        self.chart_gpu.update()

        def job():
            ok, out = hw.set_fan_curve(profile, fan, points)
            if ok:
                ok, out = hw.enable_fan_curves(profile, True)
            return ok, out
        self.main.bg(job, then=lambda r: (self.main.report(r, "Fan curve"), self.load()))

    def on_apply_fans(self, on):
        self.remember(fans_on=on)
        self.chart_cpu.active = self.chart_gpu.active = on
        self.chart_cpu.update()
        self.chart_gpu.update()
        self.main.bg(hw.enable_fan_curves, self.profile, on,
                     then=lambda r: (self.main.report(r, "Fan curve"), self.load()))

    def on_reset_menu(self):
        menu = QtWidgets.QMenu(self)
        factory = menu.addAction("Factory (this laptop's firmware)")
        factory.setEnabled(bool(self.main.cfg.get("factory_curves", {}).get(self.profile)))
        if not factory.isEnabled():
            factory.setText("Factory (no saved copy of the firmware curves)")
        factory.triggered.connect(self.on_reset_factory)
        gh = menu.addAction("G-Helper defaults (as on Windows)")
        gh.setEnabled(self.profile in GHELPER_DEFAULTS)
        gh.triggered.connect(self.on_reset_ghelper)
        menu.exec(self.reset.mapToGlobal(QtCore.QPoint(0, -menu.sizeHint().height())))

    def write_curves(self, curves, enable, what):
        profile = self.profile
        self.remember(curves=dict(curves), fans_on=enable)

        def job():
            for fan, points in curves.items():
                ok, out = hw.set_fan_curve(profile, fan, points)
                if not ok:
                    return ok, out
            return hw.enable_fan_curves(profile, enable)
        self.main.bg(job, then=lambda r: (self.main.report(r, what), self.load()))

    def on_reset_factory(self):
        """Firmware curves, and custom curves off: the fans run on the firmware's own control."""
        self.write_curves(self.main.cfg["factory_curves"][self.profile], False, "Factory defaults")

    def on_reset_ghelper(self):
        """Generic G-Helper curves; they only take effect as a custom curve, so it is enabled."""
        self.write_curves(GHELPER_DEFAULTS[self.profile], True, "G-Helper defaults")

    def constrain_ppt(self, name, value):
        """Fans.TrackPower_Scroll: keep SPL <= sPPT <= fPPT while dragging any of them."""
        order = [n for n, _ in PPT if n in self.ppt]
        i = order.index(name)
        for other in order[:i]:
            track = self.ppt[other].track
            if track.value > value:
                track.set_value(value)
                self.ppt[other].show_value(track.value)
        for other in order[i + 1:]:
            track = self.ppt[other].track
            if track.value < value:
                track.set_value(value)
                self.ppt[other].show_value(track.value)

    def on_ppt(self, name, value):
        self.apply_power.setChecked(True)
        self.on_apply_power(True)

    def on_apply_power(self, on):
        values = {name: panel.track.value for name, panel in self.ppt.items()}
        self.remember(ppt=values, ppt_on=on)

        def job():
            if on:
                # asusd stores these for the current mode and power source; with the
                # group disabled they are only stored, enabling it then applies them
                for name, value in values.items():
                    ok, out = hw.set_armoury(name, value)
                    if not ok:
                        return ok, out
            return hw.set_ppt_enabled(on)
        self.main.bg(job, then=lambda r: (self.main.report(r, "Power limits"), self.load()))

    def on_gpu_value(self, name, value):
        self.main.bg(hw.set_armoury, name, value, then=lambda r: (self.main.report(r, "GPU setting"), self.load()))

    # -- calibration (FanSensorControl.StartCalibration) ----------------------------
    def init_axis(self):
        cfg = self.main.cfg
        calibrated = True
        for chart, fan in ((self.chart_cpu, "cpu"), (self.chart_gpu, "gpu")):
            chart.calibrated = fan_table(cfg, fan, self.profile) is not None
            chart.rpm = bool(cfg.get("fan_rpm", chart.calibrated))  # RPM once the mode is calibrated
            chart.fan_max = fan_max(cfg, fan)
            chart.calibrated = fan_table(cfg, fan, self.profile) is not None
            calibrated = calibrated and chart.calibrated
            chart.update()
        if not self.calibration:
            name = dict(MODE_NAMES).get(self.profile, self.profile)
            self.set_result("" if calibrated else
                            f"Press Calibrate so the charts show the real fan speed in {name}", error=False)

    def on_toggle_rpm(self):
        self.main.cfg["fan_rpm"] = not self.main.cfg.get("fan_rpm")
        self.main.save()
        self.init_axis()

    def on_calibrate(self):
        """G-Helper measures only the max RPM. Here the fans are also stepped down through
        CAL_STEPS so fan power can be translated into real speed in both directions."""
        if self.calibration:
            return
        self.calibrate.setEnabled(False)
        self.set_result("Measuring Max Speed ...")
        cfg = self.main.cfg

        target = self.profile  # calibrate the mode on screen; each mode gets its own table

        def start():
            curves = hw.get_fan_curves(target)
            if not curves:
                return False, "could not read the fan curves"
            cfg["calibration_backup"] = {
                "profile": hw.get_profile(),
                "target": target,
                "curves": {f: {"enabled": c["enabled"], "points": c["points"]} for f, c in curves.items()},
            }
            self.main.save()
            ok, out = hw.set_profile(target)
            for fan in curves:
                if ok:
                    ok, out = hw.set_fan_curve(target, fan, flat_curve(100))
            if ok:
                ok, out = hw.enable_fan_curves(target, True)
            return ok, out

        def started(result):
            ok, out = result
            if not ok:
                self.finish_calibration(error=out)
                return
            self.calibration = {"phase": "max", "max": {}, "same": 0, "ticks": 0,
                                "table": {}, "step": -1, "busy": False, "target": target}
            self.cal_timer = QtCore.QTimer(self, interval=1000, timeout=self.calibration_tick)
            self.cal_timer.start()

        self.main.bg(start, then=started)

    def calibration_tick(self):
        cal = self.calibration
        if cal["busy"]:
            return
        fans = hw.sensors(False)["fans"]
        cal["ticks"] += 1
        if cal["phase"] == "max":
            same = True
            for fan, rpm in fans.items():
                if rpm > cal["max"].get(fan, 0):
                    cal["max"][fan] = rpm
                    same = False
            cal["same"] = cal["same"] + 1 if same else 0
            self.set_result(f"Measuring Max Speed - CPU: {cal['max'].get('cpu', 0)}, "
                            f"GPU: {cal['max'].get('gpu', 0)} ({cal['same']}s)")
            if cal["same"] >= 15 or cal["ticks"] >= 90:
                for fan, rpm in cal["max"].items():
                    cal["table"][fan] = [(100, rpm)]
                cal["phase"] = "steps"
                self.next_step()
            return

        # stepping down: wait until both fans settle on a speed, then record it
        duty = CAL_STEPS[cal["step"]]
        reading = (fans.get("cpu", 0), fans.get("gpu", 0))
        cal["stable"] = cal["stable"] + 1 if reading == cal["last"] else 0
        cal["last"] = reading
        cal["wait"] += 1
        self.set_result(f"Measuring {duty}% power - CPU: {reading[0]}, GPU: {reading[1]} "
                        f"({cal['step'] + 1}/{len(CAL_STEPS)})")
        if (cal["wait"] >= 4 and cal["stable"] >= 3) or cal["wait"] >= 15:
            for fan, rpm in fans.items():
                cal["table"].setdefault(fan, []).append((duty, rpm))
            self.next_step()

    def next_step(self):
        cal = self.calibration
        cal["step"] += 1
        if cal["step"] >= len(CAL_STEPS):
            self.cal_timer.stop()
            cfg = self.main.cfg
            for fan, rpm in cal["max"].items():
                if 1000 < rpm < INADEQUATE_RPM:
                    # max is physical (keep the highest ever seen); the table belongs to this mode
                    cfg[f"fan_max_{fan}"] = max(rpm, cfg.get(f"fan_max_{fan}", 0))
                    cfg[f"fan_table_{cal['target']}_{fan}"] = sorted(cal["table"].get(fan, []))
            self.main.save()
            self.finish_calibration()
            return
        duty = CAL_STEPS[cal["step"]]
        cal.update(busy=True, wait=0, stable=0, last=None)

        def job():
            for fan in cal["max"]:
                ok, out = hw.set_fan_curve(cal["target"], fan, flat_curve(duty))
                if not ok:
                    return ok, out
            return True, ""

        def done(result):
            cal["busy"] = False
            if not result[0]:
                self.cal_timer.stop()
                self.finish_calibration(error=result[1])

        self.main.bg(job, then=done)

    def finish_calibration(self, error=None):
        cfg = self.main.cfg

        def restore():
            result = restore_after_calibration(cfg)
            cfg.pop("calibration_backup", None)
            self.main.save()
            return result

        def done(result):
            self.calibration = None
            self.calibrate.setEnabled(True)
            if error:
                self.set_result(f"Calibration failed: {error}")
            else:
                self.set_result(f"Measured - CPU: {fan_max(cfg, 'cpu')}, GPU: {fan_max(cfg, 'gpu')}", error=False)
            self.main.report(result, "Restoring fan curves")
            self.load()
            self.main.refresh_fast()

        self.main.bg(restore, then=done)
