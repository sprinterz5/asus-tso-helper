#!/usr/bin/env python3
"""Draws the app and tray icons (a white S on a coloured circle, after G-Helper's G) into asus_tso_helper/assets.

The S is plain geometry, not text, so it looks the same without any font. Tray icons use the
GPU mode colours, like G-Helper's eco / standard / ultimate tray icons.
Run: python3 tools/make_icons.py
"""
import os

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "asus_tso_helper", "assets")
COLOURS = {"app": "#3aaeef", "eco": "#06b48a", "standard": "#3aaeef", "ultimate": "#ff2020"}


def svg(colour):
    """G-Helper's icon is a thin white G on a coloured circle; this is the same with an S (Second)."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <circle cx="128" cy="128" r="120" fill="{colour}"/>
  <path d="M168 88C158 76 144 70 127 70C104 70 87 82 87 101C87 121 105 127 128 131C152 135 170 141 170 161C170 180 152 190 129 190C109 190 94 183 84 170" fill="none" stroke="#ffffff" stroke-width="24" stroke-linecap="round"/>
</svg>
"""


def main():
    for name, colour in COLOURS.items():
        path = os.path.join(ASSETS, f"{name}-icon.svg" if name == "app" else f"tray-{name}.svg")
        with open(path, "w") as f:
            f.write(svg(colour))
        print(path)
    try:  # a PNG for .desktop files and notifications
        from PySide6 import QtCore, QtGui, QtSvg
        app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
        renderer = QtSvg.QSvgRenderer(os.path.join(ASSETS, "app-icon.svg"))
        img = QtGui.QImage(256, 256, QtGui.QImage.Format_ARGB32)
        img.fill(0)
        p = QtGui.QPainter(img)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        img.save(os.path.join(ASSETS, "asus-tso-helper.png"))
        print(os.path.join(ASSETS, "asus-tso-helper.png"))
    except ImportError:
        pass


if __name__ == "__main__":
    main()
