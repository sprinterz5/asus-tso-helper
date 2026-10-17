"""Battery window: charge and power draw over a day or a week, battery health, and what each
mode costs on battery. Nothing of G-Helper's; kept out of the main window so it never gets in
the way. The record is UPower's own (it keeps it anyway); the app only logs mode changes."""
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import backend as hw
from . import modes
from . import widgets as w
from .i18n import tr
from .widgets import STANDARD, CUSTOM

PERIODS = (("day", 86400), ("week", 7 * 86400))


class Chart(QtWidgets.QWidget):
    """Charge % (blue line, left scale) and power draw W (orange, right scale) over time."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(170)
        self.charge, self.rate, self.seconds = [], [], 86400

    def set_data(self, charge, rate, seconds):
        self.charge, self.rate, self.seconds = charge, rate, seconds
        self.update()

    def paintEvent(self, _):
        t = w.THEME
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        area = QtCore.QRectF(self.rect()).adjusted(34, 8, -34, -20)
        now = time.time()
        start = now - self.seconds
        top_w = max([v for _, v, s in self.rate if s] + [20])
        top_w = (int(top_w) // 10 + 1) * 10

        def x(ts):
            return area.left() + (ts - start) / self.seconds * area.width()

        # grid, scales
        p.setFont(self.font())
        for i in range(5):
            y = area.bottom() - i * area.height() / 4
            p.setPen(QtGui.QPen(t.chart_grid, 1))
            p.drawLine(QtCore.QPointF(area.left(), y), QtCore.QPointF(area.right(), y))
            p.setPen(STANDARD)
            p.drawText(QtCore.QRectF(0, y - 8, 30, 16), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, f"{i * 25}%")
            p.setPen(CUSTOM)
            p.drawText(QtCore.QRectF(area.right() + 4, y - 8, 30, 16), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                       f"{i * top_w // 4}W")
        p.setPen(t.gray_text)
        step = 3600 * (4 if self.seconds <= 86400 else 24)
        mark = int(start // step + 1) * step
        while mark < now:
            label = time.strftime("%H:%M" if self.seconds <= 86400 else "%a", time.localtime(mark))
            p.drawText(QtCore.QRectF(x(mark) - 30, area.bottom() + 3, 60, 16), QtCore.Qt.AlignCenter, label)
            mark += step

        def line(rows, top, colour):
            pen = QtGui.QPen(colour, 1.6)
            p.setPen(pen)
            path, drawing, last = QtGui.QPainterPath(), False, 0
            for ts, value, state in rows:
                if ts < start:
                    continue
                if state == 0 or ts - last > 1800:  # asleep or off: a gap, not a slope
                    drawing = False
                last = ts
                if state == 0:
                    continue
                pt = QtCore.QPointF(x(ts), area.bottom() - min(value, top) / top * area.height())
                if drawing:
                    path.lineTo(pt)
                else:
                    path.moveTo(pt)
                    drawing = True
            p.drawPath(path)

        line(self.rate, top_w, CUSTOM)
        line(self.charge, 100, STANDARD)
        if not self.charge:
            p.setPen(t.gray_text)
            p.drawText(area, QtCore.Qt.AlignCenter, tr("No history yet"))


class BatteryWindow(QtWidgets.QWidget):
    loaded = QtCore.Signal(object)

    def __init__(self, main):
        super().__init__(main, QtCore.Qt.Window)
        self.main = main
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setWindowTitle(tr("Battery"))
        self.resize(520, 330)
        self.seconds = PERIODS[0][1]
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(w.Header("chart-line", tr("Battery"), height=22), 1)
        self.buttons = {}
        for key, seconds in PERIODS:
            b = w.RButton(tr("24 hours") if key == "day" else tr("7 days"), secondary=True, radius=2)
            b.setFixedSize(QtCore.QSize(72, 20))
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, s=seconds: self.load(s))
            top.addWidget(b)
            self.buttons[seconds] = b
        root.addLayout(top)
        self.chart = Chart()
        root.addWidget(self.chart, 1)
        self.summary = QtWidgets.QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(QtCore.Qt.RichText)
        root.addWidget(self.summary)
        self.loaded.connect(self.show_data)

    def load(self, seconds=None):
        self.seconds = seconds or self.seconds
        for s, b in self.buttons.items():
            b.set_activated(s == self.seconds)
        span = self.seconds

        def job():
            data = (hw.battery_history("charge", span), hw.battery_history("rate", span),
                    hw.battery_health(), hw.watts_per_mode(span))
            self.loaded.emit((span, data))
        self.main.bg(job)

    def show_data(self, result):
        span, (charge, rate, health, per_mode) = result
        if span != self.seconds:
            return
        self.chart.set_data(charge, rate, span)
        lines = []
        if health:
            text = tr("Health: {percent}% ({full} of {design} Wh)", percent=f"{health['health']:.0f}",
                      full=f"{health['full']:.1f}", design=f"{health['design']:.1f}")
            if health["cycles"]:
                text += ", " + tr("{count} cycles", count=health["cycles"])
            lines.append(text)
        on_battery = [v for ts, v, s in rate if s == 2 and v > 0]
        if on_battery and health:
            avg = sum(on_battery) / len(on_battery)
            lines.append(tr("On battery: {watts}W on average, a full charge lasts about {hours} h",
                            watts=f"{avg:.1f}", hours=f"{health['full'] / avg:.1f}"))
        if per_mode:
            cells = []
            for key, (watts, hours) in sorted(per_mode.items(), key=lambda kv: kv[1][0]):
                cells.append(f"<b>{modes.name_of(self.main.cfg, key)}</b> {watts:.1f}W"
                             + (f" · ~{health['full'] / watts:.1f} h" if health else ""))
            lines.append(tr("By mode") + ": " + " &nbsp;&nbsp; ".join(cells))
        else:
            lines.append(f"<span style='color:{w.THEME.gray_text.name()}'>"
                         + tr("Draw per mode appears after some time on battery.") + "</span>")
        self.summary.setText("<br>".join(lines))
