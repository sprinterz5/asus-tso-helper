"""Qt ports of G-Helper's custom controls (RButton, RComboBox, Slider, RColorButton).

Geometry and colours follow seerge/g-helper app/UI/*.cs. G-Helper's designer works in
192-DPI units; every size here is that value halved, i.e. Qt logical pixels.
"""
import math
import os

from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
ICONS = os.path.join(ASSETS, "icons")
APP_ICON = os.path.join(ASSETS, "app-icon.svg")

# RForm.colorEco / colorStandard / colorTurbo / colorCustom / colorGray
ECO = QtGui.QColor(6, 180, 138)
STANDARD = QtGui.QColor(58, 174, 239)
TURBO = QtGui.QColor(255, 32, 32)
CUSTOM = QtGui.QColor(255, 128, 0)
GRAY = QtGui.QColor(168, 168, 168)


class Theme:
    """RForm.InitColors()."""

    def __init__(self, dark):
        self.dark = dark
        c = QtGui.QColor
        if dark:
            self.button_main = c(46, 46, 46)
            self.button_second = c(36, 36, 36)
            self.form_back = c(28, 28, 28)
            self.fore = c(240, 240, 240)
            self.border_main = c(55, 55, 55)
            self.border_second = c(42, 42, 42)
            self.chart_grid = c(70, 70, 70)
        else:
            self.button_main = c(255, 255, 255)      # SystemColors.ControlLightLight
            self.button_second = c(227, 227, 227)    # SystemColors.ControlLight
            self.form_back = c(240, 240, 240)        # SystemColors.Control
            self.fore = c(0, 0, 0)                   # SystemColors.ControlText
            self.border_main = c(220, 220, 220)
            self.border_second = c(215, 215, 215)
            self.chart_grid = c(211, 211, 211)       # Color.LightGray
        self.gray_text = c(109, 109, 109)            # SystemColors.GrayText
        self.control_dark = c(160, 160, 160)         # SystemColors.ControlDark


THEME = Theme(True)
_icons = {}


def set_theme(dark):
    global THEME
    THEME = Theme(dark)
    _icons.clear()


_STANDARD_BLUE = QtGui.QColor(STANDARD)


def set_accent(colour=None):
    """The desktop's accent colour in place of G-Helper's blue (Balanced, Standard, checkboxes,
    sliders, links); None brings the blue back. Changed in place, so every control holding
    STANDARD repaints with it; mode colours with a meaning (Silent green, Turbo red) stay."""
    STANDARD.setRgb((colour or _STANDARD_BLUE).rgb())


def icon(name, size=16):
    """Lucide line icons (assets/icons, ISC licence) drawn in the text colour: black on light,
    white on dark, the way G-Helper's ControlHelper.AdjustImage inverts its icons."""
    key = (name, size, THEME.dark)
    if key not in _icons:
        with open(os.path.join(ICONS, name + ".svg")) as f:
            data = f.read().replace("currentColor", "#ffffff" if THEME.dark else "#000000")
        ratio = QtGui.QGuiApplication.primaryScreen().devicePixelRatio() if QtGui.QGuiApplication.primaryScreen() else 1
        px = int(size * ratio)
        img = QtGui.QImage(px, px, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        QtSvg.QSvgRenderer(QtCore.QByteArray(data.encode())).render(p)
        p.end()
        pix = QtGui.QPixmap.fromImage(img)
        pix.setDevicePixelRatio(ratio)
        _icons[key] = pix
    return _icons[key]


def shift(colour, amount):
    """RButton.Shift: blend towards black on light colours, white on dark ones."""
    lum = (colour.red() * 30 + colour.green() * 59 + colour.blue() * 11) / 100
    t = 0 if lum > 128 else 255
    return QtGui.QColor(int(colour.red() + (t - colour.red()) * amount),
                        int(colour.green() + (t - colour.green()) * amount),
                        int(colour.blue() + (t - colour.blue()) * amount), colour.alpha())


def rounded(rect, radius):
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def with_alpha(colour, alpha):
    c = QtGui.QColor(colour)
    c.setAlpha(alpha)
    return c


def gradient_border(p, rect, side, radius, width=1.0, top_lighten=0.1):
    """ControlHelper.DrawGradientBorder: lighter top edge fading into the side colour.
    `rect` is the centre line of the stroke."""
    if not THEME.dark and width <= 1:
        top = with_alpha(side, 64)
    else:
        top = QtGui.QColor(int(side.red() + (255 - side.red()) * top_lighten),
                           int(side.green() + (255 - side.green()) * top_lighten),
                           int(side.blue() + (255 - side.blue()) * top_lighten), side.alpha())
    flat = max(1.0, width)
    grad_h = round(rect.height() * (0.3 if THEME.dark else 0.9))
    start, end = rect.top() - width, rect.bottom() + width
    length = end - start
    p1 = max(0.0, min(0.98, (width + flat) / length))
    p2 = max(p1 + 0.01, min(1.0, (width + flat + grad_h) / length))
    g = QtGui.QLinearGradient(0, start, 0, end)
    g.setColorAt(0, top)
    g.setColorAt(p1, top)
    g.setColorAt(p2, side)
    g.setColorAt(1, side)
    pen = QtGui.QPen(QtGui.QBrush(g), width)
    p.setPen(pen)
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawPath(rounded(rect, radius))


class RButton(QtWidgets.QAbstractButton):
    """RButton: flat rounded button; when `activated` it gets a 3px accent border and a
    faint accent glow at the top. `vertical` = TextImageRelation.ImageAboveText."""

    BORDER = 3  # borderSize 5 at 192 DPI -> round((0.5*5-1)/2)*2+1

    def __init__(self, text="", icon_name=None, secondary=False, accent=None, radius=5,
                 vertical=False, borderless=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.icon_name = icon_name
        self.secondary = secondary
        self.accent = accent
        self.radius = math.floor(0.5 * radius + 0.5)
        self.vertical = vertical
        self.borderless = borderless
        self.activated = False
        self.pending = False      # a switch to this choice waits for logout / reboot
        self.pending_on = True
        self.pending_timer = QtCore.QTimer(self, interval=600, timeout=self._blink)
        self.text_colour = None
        self.setAttribute(QtCore.Qt.WA_Hover)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)

    def set_activated(self, on):
        if on != self.activated:
            self.activated = on
            self.update()

    def set_pending(self, on):
        """Blinking dashed accent border: chosen, but not active until logout / reboot."""
        if on == self.pending:
            return
        self.pending = on
        self.pending_on = True
        self.pending_timer.start() if on else self.pending_timer.stop()
        self.update()

    def _blink(self):
        self.pending_on = not self.pending_on
        self.update()

    def set_accent(self, colour):
        self.accent = colour
        self.update()

    def sizeHint(self):
        return QtCore.QSize(80, 24)

    def background(self):
        bg = THEME.button_second if self.secondary else THEME.button_main
        if self.isEnabled():
            if self.isDown():
                bg = shift(bg, 0.08)
            elif self.underMouse():
                bg = shift(bg, 0.04)
        return bg

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        b = self.BORDER
        r = self.radius
        rect = QtCore.QRectF(self.rect())

        # Region = rounded(rect, r+b), then a parent-coloured pen of width b on that outline
        surface = rect.adjusted(b / 2, b / 2, -b / 2, -b / 2)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self.background())
        p.drawPath(rounded(surface, r + b / 2))

        enabled = self.isEnabled()
        if not self.borderless and self.activated and self.accent is not None:
            inner = rect.adjusted(b, b, -b, -b)
            top, clear = with_alpha(self.accent, 32), with_alpha(self.accent, 0)
            g = QtGui.QLinearGradient(0, inner.top(), 0, inner.bottom()) if THEME.dark \
                else QtGui.QLinearGradient(0, inner.bottom(), 0, inner.top())
            g.setColorAt(0, top)
            g.setColorAt(0.2, clear)
            g.setColorAt(1, clear)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QBrush(g))
            p.drawPath(rounded(inner, r))
            accent = self.accent if enabled else with_alpha(self.accent, 110)
            gradient_border(p, inner.adjusted(-b / 2, -b / 2, b / 2, b / 2), accent, r + b / 2, b, 0.15)
        elif not self.borderless and enabled:
            inset = b // 2 + 1
            ring = rect.adjusted(inset + 0.5, inset + 0.5, -inset - 0.5, -inset - 0.5)
            side = THEME.border_second if self.secondary else THEME.border_main
            gradient_border(p, ring, side, r + b - inset, 1, 0.1)

        if self.pending and self.accent is not None and not self.activated:
            pen = QtGui.QPen(with_alpha(self.accent, 255 if self.pending_on else 70), 2)
            pen.setStyle(QtCore.Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawPath(rounded(rect.adjusted(2, 2, -2, -2), r + b / 2))

        self.paint_content(p, rect)

    def paint_content(self, p, rect):
        colour = self.text_colour or THEME.fore
        p.setPen(colour if self.isEnabled() else THEME.gray_text)
        p.setFont(self.font())
        fm = QtGui.QFontMetrics(self.font())
        text = self.text()
        pix = icon(self.icon_name) if self.icon_name else None
        if pix and self.vertical:
            gap = 4
            total = 16 + gap + fm.height()
            y = rect.top() + (rect.height() - total) / 2
            p.drawPixmap(QtCore.QPointF(rect.center().x() - 8, y), pix)
            p.drawText(QtCore.QRectF(rect.left(), y + 16 + gap, rect.width(), fm.height()),
                       QtCore.Qt.AlignCenter, text)
        elif pix:
            gap = 4 if text else 0  # an icon-only button: the icon centred
            total = 16 + gap + fm.horizontalAdvance(text)
            x = rect.left() + (rect.width() - total) / 2
            p.drawPixmap(QtCore.QPointF(x, rect.center().y() - 8), pix)
            p.drawText(QtCore.QRectF(x + 16 + gap, rect.top(), rect.width(), rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)
        else:
            p.drawText(rect, QtCore.Qt.AlignCenter, text)


class IconButton(RButton):
    """A small square button with only an icon, centred, and a soft shadow under it."""

    def __init__(self, icon_name, size=20, icon_size=12, nudge=(0, 0)):
        super().__init__("", icon_name, secondary=True)
        self.nudge = nudge  # optical centring for icons heavy on one side
        self.icon_size = icon_size
        self.setFixedSize(size, size + 2)  # 2 px for the shadow
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        box = QtCore.QRectF(0.5, 0.5, self.width() - 1, self.width() - 1)
        for i, alpha in ((2, 25), (1, 45)):  # shadow: two soft steps below
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, alpha))
            p.drawRoundedRect(box.translated(0, i), 3, 3)
        p.setBrush(self.background())
        p.setPen(QtGui.QPen(THEME.border_main, 1))
        p.drawRoundedRect(box, 3, 3)
        pix = icon(self.icon_name, self.icon_size)
        offset = (self.width() - self.icon_size) / 2
        p.drawPixmap(QtCore.QPointF(box.left() + offset - 0.5 + self.nudge[0],
                                    box.top() + offset - 0.5 + self.nudge[1]), pix)


class ColorButton(RButton):
    """RColorButton: a button with a colour swatch on its right edge."""

    def __init__(self, text, colour, **kw):
        super().__init__(text, **kw)
        self.swatch = QtGui.QColor(colour)

    def set_swatch(self, colour):
        self.swatch = QtGui.QColor(colour)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        h = self.height()
        size = round(h * 0.45)
        margin = (h - size) / 2
        rect = QtCore.QRectF(self.width() - margin - size, margin, size, size)
        p.setPen(QtGui.QPen(THEME.border_main, 1))
        p.setBrush(self.swatch)
        p.drawPath(rounded(rect, self.radius))


class Header(QtWidgets.QWidget):
    """panel*Title: 16px icon, bold title, grey-free right-aligned status text."""

    def __init__(self, icon_name, title, height=20):
        super().__init__()
        self.icon_name = icon_name
        self.setFixedHeight(height)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(23, 0, 0, 0)  # label at x=20 plus WinForms label padding
        lay.setSpacing(0)
        self.title = QtWidgets.QLabel(title)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.info = QtWidgets.QLabel("")
        self.info.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
        lay.addWidget(self.title, 1)
        lay.addWidget(self.info)
        self.right = lay

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.drawPixmap(QtCore.QPointF(4, 0), icon(self.icon_name))


class RComboBox(QtWidgets.QComboBox):
    """RComboBox: rounded flat box with a thin border and a chevron."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.setFixedHeight(20)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QtGui.QPen(THEME.border_main, 1))
        p.setBrush(shift(THEME.button_main, 0.04) if self.underMouse() else THEME.button_main)
        p.drawPath(rounded(rect, 2))
        p.setPen(THEME.fore)
        p.drawText(rect.adjusted(5, 0, -20, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                   self.currentText())
        cx, cy = rect.right() - 10, rect.center().y()
        pen = QtGui.QPen(THEME.fore, 1.2)
        p.setPen(pen)
        p.drawPolyline([QtCore.QPointF(cx - 4, cy - 2), QtCore.QPointF(cx, cy + 2),
                        QtCore.QPointF(cx + 4, cy - 2)])


class Slider(QtWidgets.QWidget):
    """UI/Slider.cs: thin bar, accent fill, white-ringed thumb that grows on hover."""

    valueChanged = QtCore.Signal(int)
    released = QtCore.Signal(int)

    INNER_NORMAL, INNER_HOVER, INNER_PRESSED = 12 / 22, 16 / 22, 10 / 22

    def __init__(self, minimum=40, maximum=100, step=5):
        super().__init__()
        self.min, self.max, self.step = minimum, maximum, step
        self.value = maximum
        self.accent = STANDARD
        self.dragging = False
        self.inner = self.INNER_NORMAL
        self.target = self.INNER_NORMAL
        self.anim = QtCore.QTimer(self, interval=30, timeout=self._animate)
        self.setFixedHeight(20)
        self.setAttribute(QtCore.Qt.WA_Hover)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def set_value(self, v, emit=False):
        v = max(self.min, min(self.max, int(round(v / self.step) * self.step)))
        if v != self.value:
            self.value = v
            self.update()
            if emit:
                self.valueChanged.emit(v)

    def _geometry(self):
        radius = 0.4 * self.height()
        bar_h = self.height() * 0.15
        bar = QtCore.QRectF(radius, (self.height() - bar_h) / 2, self.width() - 2 * radius, bar_h)
        return radius, bar

    def _x(self, v):
        _, bar = self._geometry()
        return bar.left() + bar.width() * (v - self.min) / (self.max - self.min)

    def _set_target(self, t):
        self.target = t
        self.anim.start()

    def _animate(self):
        self.inner += (self.target - self.inner) * 0.3
        if abs(self.target - self.inner) < 0.01:
            self.inner = self.target
            self.anim.stop()
        self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        radius, bar = self._geometry()
        x = self._x(self.value)
        p.fillRect(bar, THEME.chart_grid)
        p.fillRect(QtCore.QRectF(bar.left(), bar.top(), x - bar.left(), bar.height()), self.accent)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(THEME.button_main)
        p.drawEllipse(QtCore.QPointF(x, bar.center().y()), radius, radius)
        p.setBrush(self.accent)
        r = radius * self.inner
        p.drawEllipse(QtCore.QPointF(x, bar.center().y()), r, r)

    def _from_pos(self, px):
        _, bar = self._geometry()
        t = (min(max(px, bar.left()), bar.right()) - bar.left()) / bar.width()
        self.set_value(self.min + t * (self.max - self.min), emit=True)

    def enterEvent(self, e):
        self._set_target(self.INNER_HOVER)

    def leaveEvent(self, e):
        self._set_target(self.INNER_NORMAL)

    def mousePressEvent(self, e):
        self.dragging = True
        self._set_target(self.INNER_PRESSED)
        self._from_pos(e.position().x())

    def mouseMoveEvent(self, e):
        if self.dragging:
            self._from_pos(e.position().x())

    def mouseReleaseEvent(self, e):
        self.dragging = False
        self._set_target(self.INNER_HOVER if self.underMouse() else self.INNER_NORMAL)
        self.released.emit(self.value)

    def keyPressEvent(self, e):
        delta = {QtCore.Qt.Key_Left: -self.step, QtCore.Qt.Key_Down: -self.step,
                 QtCore.Qt.Key_Right: self.step, QtCore.Qt.Key_Up: self.step}.get(e.key())
        if delta is None:
            return super().keyPressEvent(e)
        self.set_value(self.value + delta, emit=True)
        self.released.emit(self.value)
