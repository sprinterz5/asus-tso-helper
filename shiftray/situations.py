"""Situations (Extra: "Situations", experimental): one tile sets the mode, the GPU mode, the screen and
the keyboard light together. Every situation sets all four, so a tile always gives the same result;
"depends on the charger" is Optimized and Auto.

Stored in cfg["situations"] (only what differs from DEFAULTS); cfg["situation"] is the picked one.
"""
from .i18n import tr

# key, title, icon, settings
DEFAULTS = [
    ("go", tr("On the go"), "luggage", {"mode": "quiet", "gpu": "Integrated", "screen": "60", "kbd": "low"}),
    ("desk", tr("Desk"), "laptop", {"mode": "balanced", "gpu": "Hybrid", "screen": "max", "kbd": "med"}),
    ("gaming", tr("Gaming"), "gamepad-2", {"mode": "performance", "gpu": "Hybrid", "screen": "max", "kbd": "high"}),
    ("quiet", tr("Quiet"), "moon", {"mode": "quiet", "gpu": "auto", "screen": "auto", "kbd": "off"}),
]
KEYS = [d[0] for d in DEFAULTS]

# what each setting can be, in the order of the buttons; the labels for the tile's line
MODES = [("quiet", tr("Silent")), ("balanced", tr("Balanced")), ("performance", tr("Turbo"))]
GPUS = [("Integrated", tr("Eco")), ("Hybrid", tr("Standard")), ("AsusMuxDgpu", tr("Ultimate")),
        ("auto", tr("Optimized"))]
SCREENS = [("auto", tr("Auto")), ("60", tr("60Hz")), ("max", tr("Max"))]
KBDS = [("off", tr("Off")), ("low", tr("Low")), ("med", tr("Med")), ("high", tr("High"))]
LIGHTS = {"off": tr("lights off"), "low": tr("lights low"), "med": tr("lights med"), "high": tr("lights high")}


def get(cfg, key):
    """The situation's settings: the defaults with the user's changes on top."""
    base = dict(next(d[3] for d in DEFAULTS if d[0] == key))
    base.update({k: v for k, v in cfg.get("situations", {}).get(key, {}).items() if v is not None})
    return base


def set_value(cfg, key, setting, value):
    cfg.setdefault("situations", {}).setdefault(key, {})[setting] = value


def title(key):
    return next(d[1] for d in DEFAULTS if d[0] == key)


def icon(key):
    return next(d[2] for d in DEFAULTS if d[0] == key)


def summary(cfg, key, screen_max=None, gpu_modes=True):
    """The tile's grey line: 'Silent · Eco · 60Hz · lights low' (no GPU mode without a dGPU)."""
    s = get(cfg, key)
    screen = screen_max if s["screen"] == "max" and screen_max else dict(SCREENS)[s["screen"]]
    parts = (dict(MODES)[s["mode"]],) + ((dict(GPUS)[s["gpu"]],) if gpu_modes else ()) + (screen, LIGHTS[s["kbd"]])
    return " · ".join(parts)


def matches(cfg, key, profile, gpu, gpu_auto, gpu_modes=True):
    """Whether the laptop is still in this situation: its mode and GPU mode. A mode changed with Fn+F5
    or another app ends it."""
    s = get(cfg, key)
    if s["mode"] != profile or cfg.get("active_mode"):
        return False
    if not gpu_modes:
        return True
    if s["gpu"] == "auto":
        return bool(gpu_auto)
    return s["gpu"] == gpu and not gpu_auto
