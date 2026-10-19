"""Main window: Situations (Extra: "Situations", experimental). Four tiles take the place of the Mode, GPU
Mode and Screen blocks; under them the picked situation's settings, which fold away once set."""
from PySide6 import QtCore, QtWidgets

from . import backend as hw
from . import situations as sit
from . import widgets as w
from .i18n import tr
from .widgets import ECO, STANDARD, TURBO, CUSTOM, GRAY

TILE_COLOUR = {"go": ECO, "desk": STANDARD, "gaming": TURBO, "quiet": ECO}
# the classic window's icons, so a row reads at a glance
ROW_ICON = {"mode": "gauge", "gpu": "gpu", "screen": "laptop", "kbd": "keyboard"}
CHOICE_ICON = {("mode", "quiet"): "bike", ("mode", "balanced"): "car", ("mode", "performance"): "rocket",
               ("gpu", "Integrated"): "leaf", ("gpu", "Hybrid"): "flower-2", ("gpu", "AsusMuxDgpu"): "gamepad-2",
               ("gpu", "auto"): "sparkles"}
MODE_COLOUR = {"quiet": ECO, "balanced": STANDARD, "performance": TURBO}
GPU_COLOUR = {"Integrated": ECO, "Hybrid": STANDARD, "AsusMuxDgpu": TURBO, "auto": ECO}


class SituationsMixin:
    def build_situations(self):
        p = QtWidgets.QWidget()
        p.setObjectName("panel")
        lay = QtWidgets.QVBoxLayout(p)
        lay.setContentsMargins(10, 10, 10, 16)  # the battery block assumes a tip line above it
        lay.setSpacing(0)
        self.sit_head = w.Header("sparkles", tr("Situation"), height=34)  # CPU and GPU lines on the right
        lay.addWidget(self.sit_head)
        holder = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(holder)
        g.setContentsMargins(2, 2, 2, 2)
        g.setSpacing(4)
        self.sit_tiles = {}
        for i, key in enumerate(sit.KEYS):
            b = w.TileButton(sit.title(key), sit.icon(key), accent=TILE_COLOUR[key])
            b.setFixedHeight(62)
            b.clicked.connect(lambda _=False, k=key: self.pick_situation(k))
            g.addWidget(b, i // 2, i % 2)
            self.sit_tiles[key] = b
        lay.addWidget(holder)

        lay.addSpacing(8)
        self.sit_fold = w.FoldHeader("", bool(self.cfg.get("situation_details_open", True)))
        self.sit_fold.toggled.connect(self.on_situation_fold)
        lay.addWidget(self.sit_fold)
        self.sit_body = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(self.sit_body)
        bl.setContentsMargins(2, 4, 2, 0)
        bl.setSpacing(4)
        self.sit_buttons = {}  # (setting, value) -> button
        rows = [("mode", tr("Mode"), sit.MODES), ("gpu", tr("GPU"), [g for g in sit.GPUS if self.gpu_choice_ok(g[0])]),
                ("screen", tr("Screen"), sit.SCREENS), ("kbd", tr("Keyboard"), sit.KBDS)]
        for setting, caption, choices in rows:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(4)
            icon = QtWidgets.QLabel()
            icon.setPixmap(w.icon(ROW_ICON[setting]))
            icon.setToolTip(caption)
            icon.setFixedWidth(22)
            row.addWidget(icon)
            for value, text in choices:
                b = w.RButton(text, CHOICE_ICON.get((setting, value)), secondary=True, radius=2,
                              accent=self.choice_colour(setting, value))
                b.setFixedHeight(26)
                b.clicked.connect(lambda _=False, s=setting, v=value: self.set_situation_value(s, v))
                row.addWidget(b, 1)
                self.sit_buttons[(setting, value)] = b
            if setting == "mode":  # the curves and limits of these modes
                fans = w.RButton(tr("Fans"), "fan", secondary=True, radius=2)
                fans.setFixedHeight(26)
                fans.clicked.connect(self.on_fans)
                row.addWidget(fans, 1)
            bl.addLayout(row)
        self.sit_body.setVisible(self.sit_fold.opened)
        lay.addWidget(self.sit_body)
        self.sit_panel = p
        return p

    def gpu_choice_ok(self, value):
        """What this laptop has: Optimized needs Eco and Standard, Ultimate a MUX switch."""
        if value == "auto":
            return self.optimized is not None
        return value in self.gpu_buttons

    @staticmethod
    def choice_colour(setting, value):
        if setting == "mode":
            return MODE_COLOUR.get(value, CUSTOM)
        if setting == "gpu":
            return GPU_COLOUR.get(value, GRAY)
        return GRAY

    def apply_situations_layout(self):
        """Tiles, or the G-Helper blocks they stand for."""
        on = bool(self.cfg.get("situations_on"))
        self.sit_panel.setVisible(on)
        for panel in (self.perf_panel, self.gpu_panel, self.screen_panel):
            panel.setVisible(not on)
        if on:
            self.show_situations()
        QtCore.QTimer.singleShot(0, lambda: self.setFixedHeight(self.root_layout.sizeHint().height()))

    def set_situations(self, on):
        self.cfg["situations_on"] = on
        self.save()
        self.apply_situations_layout()

    def current_situation(self):
        """The picked situation while the laptop is still in it, else None."""
        key = self.cfg.get("situation")
        if key in sit.KEYS and sit.matches(self.cfg, key, self.last_profile, self.gpu_current,
                                           self.cfg.get("gpu_auto")):
            return key
        return None

    def show_situations(self):
        if not self.cfg.get("situations_on"):
            return
        active = self.current_situation()
        shown = self.cfg.get("situation") if self.cfg.get("situation") in sit.KEYS else sit.KEYS[0]
        screen_max = self.screen_max.text() if self.screen_max.text() != tr("Max") else None
        for key, b in self.sit_tiles.items():
            b.set_activated(key == active)
            b.set_line(sit.summary(self.cfg, key, screen_max))
        self.sit_head.title.setText(tr("Situation: {name}", name=sit.title(active)) if active else tr("Situation"))
        self.sit_fold.title.setText(tr("{name} is", name=sit.title(shown)))
        self.sit_fold.summary.setText(sit.summary(self.cfg, shown, screen_max))
        settings = sit.get(self.cfg, shown)
        for (setting, value), b in self.sit_buttons.items():
            b.set_activated(settings.get(setting) == value)
            if setting == "screen" and value == "max" and screen_max:
                b.setText(screen_max)

    def on_situation_fold(self, opened):
        self.cfg["situation_details_open"] = opened
        self.save()
        self.sit_body.setVisible(opened)
        QtCore.QTimer.singleShot(0, lambda: self.setFixedHeight(self.root_layout.sizeHint().height()))

    def pick_situation(self, key):
        self.cfg["situation"] = key
        self.save()
        self.apply_situation(sit.get(self.cfg, key))
        self.show_situations()

    def set_situation_value(self, setting, value):
        """Changes the shown situation, and the laptop with it."""
        key = self.cfg.get("situation") if self.cfg.get("situation") in sit.KEYS else sit.KEYS[0]
        self.cfg["situation"] = key
        sit.set_value(self.cfg, key, setting, value)
        self.save()
        self.apply_situation({setting: value})
        self.show_situations()

    def apply_situation(self, settings):
        """Each setting through the same path as its own button."""
        mode = settings.get("mode")
        if mode and (mode != self.last_profile or self.cfg.get("active_mode")):
            self.on_profile(mode)
        gpu = settings.get("gpu")
        if gpu == "auto" and not self.cfg.get("gpu_auto"):
            self.on_optimized()
        elif gpu in ("Integrated", "Hybrid", "AsusMuxDgpu") and (gpu != self.gpu_current or self.cfg.get("gpu_auto")):
            self.on_gpu(gpu)  # to or from Ultimate it asks about the reboot first
        screen = settings.get("screen")
        if screen and screen != self.cfg.get("screen"):
            self.on_screen(screen)
        kbd = settings.get("kbd")
        if kbd:
            self.bg(hw.set_kbd_level, kbd, then=lambda r: self.report(r, tr("Keyboard backlight")))
