"""Custom modes, like G-Helper's Mode/Modes.cs ("Custom 1", "Turbo+ 30W", ...).

asusd knows only Silent / Balanced / Turbo. A custom mode is one of those (its base) plus its own
fan curves and power limits. While a custom mode is active its settings live in the base mode's
asusd slots; a copy of what was there before is kept and put back when the custom mode ends,
so the plain base mode is never changed by using a custom one.

Power limits in asusd are per mode *and* per power source, so the copy of the base limits is
kept per source too and restored for a source the next time it is active.
"""
import secrets

from . import backend as hw
from .i18n import tr

BASES = ["quiet", "balanced", "performance"]  # Modes.GetList order: Silent, Balanced, Turbo
PPT = ["ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"]


def custom_modes(cfg):
    return cfg.setdefault("custom_modes", [])


def get(cfg, mode_id):
    return next((m for m in custom_modes(cfg) if m["id"] == mode_id), None)


def active(cfg):
    return get(cfg, cfg.get("active_mode"))


def source():
    return "ac" if hw.ac_online() else "bat"


def read_ppt():
    return {"enabled": bool(hw.get_ppt_enabled()), "values": {n: hw.get_ppt(n) for n in PPT}}


def add(cfg, name=None):
    """Modes.Add: a new custom mode copying what the current mode does right now."""
    base = hw.get_profile() or "balanced"
    current = active(cfg)
    curves = hw.get_fan_curves(base)
    n = len(custom_modes(cfg)) + 1
    while any(m["name"] == f"Custom {n}" for m in custom_modes(cfg)):
        n += 1
    mode = {
        "id": "m" + secrets.token_hex(3),
        "name": name or f"Custom {n}",
        "base": current["base"] if current else base,
        "curves": {f: c["points"] for f, c in curves.items()},
        "fans_on": any(c["enabled"] for c in curves.values()),
        "ppt": read_ppt()["values"],
        "ppt_on": bool(hw.get_ppt_enabled()),
    }
    custom_modes(cfg).append(mode)
    return mode


def remove(cfg, mode_id):
    if cfg.get("active_mode") == mode_id:
        deactivate(cfg)
    mode = get(cfg, mode_id)
    for src in ("ac", "bat"):  # a power source that remembered this mode keeps its base
        if mode and cfg.get(f"mode_{src}") == mode_id:
            cfg[f"mode_{src}"] = mode["base"]
    cfg["custom_modes"] = [m for m in custom_modes(cfg) if m["id"] != mode_id]


def _backup(cfg, base):
    """Copy the base mode's own curves (once) and its limits for the current source (once)."""
    store = cfg.setdefault("mode_backup", {}).setdefault(base, {})
    if "curves" not in store:
        curves = hw.get_fan_curves(base)
        store["curves"] = {f: {"enabled": c["enabled"], "points": c["points"]} for f, c in curves.items()}
    src = source()
    if src not in store.setdefault("ppt", {}):
        store["ppt"][src] = read_ppt()


def _write(mode):
    base = mode["base"]
    for fan, points in (mode.get("curves") or {}).items():
        hw.set_fan_curve(base, fan, points)
    hw.enable_fan_curves(base, bool(mode.get("fans_on")))
    if mode.get("ppt_on") and mode.get("ppt"):
        for name, value in mode["ppt"].items():
            rng = hw.armoury_range(name)
            if value is not None and rng:
                hw.set_armoury(name, max(rng[0], min(rng[1], value)))
        hw.set_ppt_enabled(True)
    else:
        hw.set_ppt_enabled(False)


def activate(cfg, mode_id):
    """Switch to a custom mode: base profile first, then its curves and limits on top."""
    mode = get(cfg, mode_id)
    if mode is None:
        return False, "unknown mode"
    if cfg.get("active_mode") and cfg["active_mode"] != mode_id:
        deactivate(cfg)
    ok, out = hw.set_profile(mode["base"])
    if not ok:
        return ok, out
    _backup(cfg, mode["base"])
    _write(mode)
    cfg["active_mode"] = mode_id
    return True, ""


def reapply(cfg):
    """After a charger change asusd uses the other source's limits: put the custom ones there."""
    mode = active(cfg)
    if mode and hw.get_profile() == mode["base"]:
        _backup(cfg, mode["base"])
        _write(mode)


def deactivate(cfg):
    """Leave the custom mode and give the base mode its own settings back."""
    mode = active(cfg)
    cfg.pop("active_mode", None)
    if mode:
        restore(cfg, mode["base"])


def restore(cfg, base):
    store = cfg.get("mode_backup", {}).get(base)
    if not store:
        return
    for fan, curve in store.get("curves", {}).items():
        hw.set_fan_curve(base, fan, curve["points"])
        hw.enable_fan_curve(base, fan, curve["enabled"])
    store.pop("curves", None)
    if hw.get_profile() == base:
        ppt = store.get("ppt", {}).pop(source(), None)
        if ppt:
            for name, value in ppt["values"].items():
                if value is not None:
                    hw.set_armoury(name, value)
            hw.set_ppt_enabled(ppt["enabled"])
    if not store.get("ppt"):
        cfg["mode_backup"].pop(base, None)


def restore_pending(cfg):
    """Limits of a base mode for the other power source are put back once that source is active."""
    profile = hw.get_profile()
    active_mode = active(cfg)
    if active_mode and active_mode["base"] == profile:
        return
    if profile in cfg.get("mode_backup", {}):
        restore(cfg, profile)


def remember_edit(cfg, curves=None, fans_on=None, ppt=None, ppt_on=None):
    """Fans + Power edits while a custom mode is active belong to that mode."""
    mode = active(cfg)
    if not mode:
        return
    if curves:
        mode.setdefault("curves", {}).update(curves)
    if fans_on is not None:
        mode["fans_on"] = fans_on
    if ppt:
        mode["ppt"] = ppt
    if ppt_on is not None:
        mode["ppt_on"] = ppt_on


def base_of(cfg, key):
    mode = get(cfg, key)
    return mode["base"] if mode else key


def name_of(cfg, key):
    return next((name for k, name, _ in all_modes(cfg) if k == key), key)


def all_modes(cfg):
    """[(key, name, base)] in G-Helper's order; key is a base profile or a custom mode id."""
    names = {"quiet": tr("Silent"), "balanced": tr("Balanced"), "performance": tr("Turbo")}
    return [(b, names[b], b) for b in BASES] + [(m["id"], m["name"], m["base"]) for m in custom_modes(cfg)]
