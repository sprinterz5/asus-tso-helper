"""First-run setup: checks what the app needs and fixes it behind one password prompt.

G-Helper has no such window because Windows ships ASUS's services; on Linux they come from the
asus-linux project (asusd, supergfxd) and a few small tools. The fix is one root shell script
for the distribution's package manager, run through pkexec, with its output shown live.
"""
import importlib.util
import os
import shutil

from PySide6 import QtCore, QtGui, QtWidgets

from . import backend as hw
from . import hotkeys
from . import widgets as w
from .widgets import ECO, TURBO

REQUIRED, RECOMMENDED, OPTIONAL, INFO = "required", "recommended", "optional", "info"
OLD_COPR = "/etc/yum.repos.d/_copr:copr.fedorainfracloud.org:lukenukem:asus-linux.repo"
TERRA_INSTALL = ("dnf install -y --nogpgcheck --repofrompath "
                 "'terra,https://repos.fyralabs.com/terra$releasever' terra-release")
NVIDIA_HOWTO = "https://rpmfusion.org/Howto/NVIDIA"
ASUS_LINUX = "https://asus-linux.org/guides/"


def os_release():
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                info[key] = value.strip('"')
    except OSError:
        pass
    return info


def distro():
    """'fedora', 'arch', 'debian', 'suse' or '' (by ID and ID_LIKE)."""
    rel = os_release()
    ids = (rel.get("ID", "") + " " + rel.get("ID_LIKE", "")).split()
    for family in ("fedora", "arch", "debian", "suse"):
        if family in ids or (family == "debian" and "ubuntu" in ids) or (family == "suse" and any("suse" in i for i in ids)):
            return family
    return ""


def is_asus():
    return "asus" in (hw._read("/sys/class/dmi/id/sys_vendor") or "").lower()


def has_dgpu():
    """A discrete GPU supergfxd can manage (NVIDIA, or the dGPU switch in the firmware)."""
    return hw.dgpu_power() is not None or os.path.exists(f"{hw.ARMOURY}/dgpu_disable")


def service_active(name):
    ok, out = hw.run("systemctl", "is-active", name, timeout=5)
    return out.strip() == "active"


def rpm_installed(name):
    return shutil.which("rpm") is not None and hw.run("rpm", "-q", name, timeout=5)[0]


def check(key, title, ok, level, detail="", fix=True):
    return {"key": key, "title": title, "ok": ok, "level": level, "detail": detail, "fix": fix}


def checks():
    """What the app needs, as rows for the window and input for script()."""
    family = distro()
    rows = []
    if not is_asus():
        rows.append(check("asus", "ASUS laptop", False, REQUIRED,
                          "This does not look like an ASUS laptop; most controls will not work.", fix=False))
        return rows
    if family == "fedora":
        terra = any(n.startswith("terra") for n in os.listdir("/etc/yum.repos.d"))
        rows.append(check("terra", "ASUS Linux repository (Terra)", terra, RECOMMENDED,
                          "The old COPR repository no longer gets updates; moves to Terra."
                          if os.path.exists(OLD_COPR) else "Where asusctl and supergfxctl come from on Fedora."))
    asusd = shutil.which("asusctl") is not None and service_active("asusd")
    rows.append(check("asusd", "asusd (modes, fans, keyboard, battery)", asusd, REQUIRED,
                      "" if asusd else "asusctl is missing or its service is not running."))
    if has_dgpu():
        gfx = shutil.which("supergfxctl") is not None and service_active("supergfxd")
        rows.append(check("supergfxd", "supergfxd (GPU modes)", gfx, RECOMMENDED,
                          "" if gfx else "Needed for Eco / Standard / Ultimate."))
    if family == "fedora" and rpm_installed("tuned-ppd"):
        rows.append(check("ppd", "Power profiles", False, RECOMMENDED,
                          "tuned-ppd fights asusd over the platform profile (asusctl issue #724); "
                          "switches to power-profiles-daemon, as asus-linux recommends."))
    rows.append(check("keys", "Laptop keys (Fn+F4 and others)",
                      os.path.exists(f"/etc/udev/rules.d/{hotkeys.RULE_NAME}") and hotkeys.find_device() is not None,
                      RECOMMENDED, "Lets the app read the ASUS hotkeys; nothing else from the keyboard."))
    if not all(importlib.util.find_spec(m) for m in ("evdev", "dbus")):
        rows.append(check("python", "Python modules (evdev, dbus)", False, RECOMMENDED,
                          "For key bindings and keyboard shortcuts."))
    rows.append(check("swayidle", "swayidle", shutil.which("swayidle") is not None, OPTIONAL,
                      "For the keyboard backlight timeout."))
    if has_dgpu():
        rows.append(check("lsof", "lsof", shutil.which("lsof") is not None, OPTIONAL,
                          "supergfxd uses it to close programs on the dGPU before Eco."))
    nvidia_gpu = any(hw._read(v) == "0x10de" for v in __import__("glob").glob("/sys/bus/pci/devices/*/vendor"))
    if nvidia_gpu:
        driver = os.path.exists("/sys/module/nvidia") or hw.run("modinfo", "nvidia", timeout=5)[0]
        rows.append(check("nvidia", "NVIDIA driver", driver, INFO,
                          "" if driver else "Not installed: needed for games on the NVIDIA GPU and its "
                          "temperature. Install it from your distribution (Fedora: RPM Fusion).", fix=False))
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    rows.append(check("kde", "KDE Plasma", "KDE" in desktop.upper(), INFO,
                      "" if "KDE" in desktop.upper() else
                      f"Running on {desktop or 'another desktop'}: refresh rate, toasts and the logout "
                      "prompt use KDE.", fix=False))
    return rows


def needs_setup(rows):
    return any(not r["ok"] and r["level"] in (REQUIRED, RECOMMENDED) for r in rows)


def script(rows):
    """One root shell script for everything fixable; each step reports itself."""
    family = distro()
    todo = {r["key"] for r in rows if not r["ok"] and r["fix"]}
    lines = ["set -u", 'step() { echo; echo "== $1"; }']
    rule = f"/etc/udev/rules.d/{hotkeys.RULE_NAME}"
    if family == "fedora":
        pkgs = []
        if "terra" in todo:
            lines += ["step 'Terra repository'", f"{TERRA_INSTALL} || exit 1"]
            if os.path.exists(OLD_COPR):
                lines += [f"rm -f '{OLD_COPR}'", "dnf upgrade -y asusctl supergfxctl"]
        if "asusd" in todo:
            pkgs.append("asusctl")
        if "supergfxd" in todo:
            pkgs.append("supergfxctl")
        if "python" in todo:
            pkgs += ["python3-evdev", "python3-dbus"]
        pkgs += [p for p in ("swayidle", "lsof") if p in todo]
        if pkgs:
            lines += [f"step 'Installing {' '.join(pkgs)}'", f"dnf install -y {' '.join(pkgs)}"]
        if "ppd" in todo:
            lines += ["step 'power-profiles-daemon'",
                      "dnf swap -y tuned-ppd power-profiles-daemon --allowerasing && "
                      "systemctl enable --now power-profiles-daemon"]
    elif family == "arch":
        pkgs = (["asusctl"] if "asusd" in todo else []) + (["python-evdev", "python-dbus"] if "python" in todo else [])
        pkgs += [p for p in ("swayidle", "lsof") if p in todo]
        if pkgs:
            lines += [f"step 'Installing {' '.join(pkgs)}'", f"pacman -S --needed --noconfirm {' '.join(pkgs)}"]
        if "supergfxd" in todo:
            lines += ["step 'supergfxctl'", "pacman -Si supergfxctl >/dev/null 2>&1 && "
                      "pacman -S --needed --noconfirm supergfxctl || echo 'supergfxctl is not in your repositories: "
                      f"see {ASUS_LINUX}'"]
    elif family in ("debian", "suse"):
        tool = "apt-get install -y" if family == "debian" else "zypper --non-interactive install"
        pkgs = (["python3-evdev", "python3-dbus"] if "python" in todo else []) + [p for p in ("swayidle", "lsof") if p in todo]
        if pkgs:
            lines += [f"step 'Installing {' '.join(pkgs)}'", f"{tool} {' '.join(pkgs)}"]
        if todo & {"asusd", "supergfxd"}:
            lines += [f"echo 'asusctl / supergfxctl are not packaged here: see {ASUS_LINUX}'"]
    # restart, not just start: after an upgrade the old daemon would keep running
    if todo & {"asusd", "terra"}:
        lines += ["step 'asusd'", "systemctl enable asusd 2>/dev/null; systemctl restart asusd"]
    if "supergfxd" in todo or ("terra" in todo and shutil.which("supergfxctl")):
        lines += ["step 'supergfxd'", "systemctl enable supergfxd 2>/dev/null; systemctl restart supergfxd"]
    if "keys" in todo:
        src = hotkeys.RULE_SRC
        lines += ["step 'Laptop keys'", f"install -m 644 '{src}' {rule} && udevadm control --reload && "
                  "udevadm trigger -s input"]
    lines += ["echo", "echo '== Done'"]
    return "\n".join(lines) + "\n"


# --- window ---------------------------------------------------------------------------
class SetupWindow(QtWidgets.QWidget):
    """Checklist in G-Helper's style: a mark, the item and what it is for; one button to fix all."""

    finished = QtCore.Signal()

    def __init__(self, main):
        super().__init__(main, QtCore.Qt.Window)
        self.main = main
        self.proc = None
        self.setWindowTitle("Setup")
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.setFixedWidth(506)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(6)
        head = QtWidgets.QLabel("A few things this laptop needs. One password sets them all up.")
        head.setWordWrap(True)
        f = head.font()
        f.setBold(True)
        head.setFont(f)
        root.addWidget(head)
        self.list = QtWidgets.QGridLayout()
        self.list.setHorizontalSpacing(8)
        self.list.setVerticalSpacing(4)
        self.list.setColumnStretch(1, 1)
        root.addLayout(self.list)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(150)
        self.log.hide()
        root.addWidget(self.log)
        buttons = QtWidgets.QHBoxLayout()
        self.links = QtWidgets.QLabel(f"<a style='color:{w.STANDARD.name()}' href='{ASUS_LINUX}'>asus-linux.org guides</a>")
        self.links.setOpenExternalLinks(True)
        buttons.addWidget(self.links)
        buttons.addStretch()
        self.later = w.RButton("Later", secondary=True, radius=2)
        self.later.setFixedSize(90, 26)
        self.later.clicked.connect(self.on_later)
        self.go = w.RButton("Set up", radius=2, accent=ECO)
        self.go.setFixedSize(110, 26)
        self.go.clicked.connect(self.run)
        self.go.set_activated(True)
        for b in (self.later, self.go):
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            buttons.addWidget(b)
        root.addLayout(buttons)
        self.rows = []
        self.refresh()

    def refresh(self):
        self.rows = checks()
        while self.list.count():
            item = self.list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, r in enumerate(self.rows):
            mark = QtWidgets.QLabel("✓" if r["ok"] else ("•" if r["level"] in (OPTIONAL, INFO) else "✗"))
            colour = ECO if r["ok"] else (QtGui.QColor("gray") if r["level"] in (OPTIONAL, INFO) else TURBO)
            mark.setStyleSheet(f"color: {colour.name()}; font-weight: bold;")
            mark.setFixedWidth(14)
            mark.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
            text = f"<b>{r['title']}</b>"
            if r["level"] == OPTIONAL:
                text += " <span style='color:gray'>(optional)</span>"
            if r["detail"] and not r["ok"]:
                text += f"<br><span style='color:gray'>{r['detail']}</span>"
            if r["key"] == "nvidia" and not r["ok"]:
                text += f" <a style='color:{w.STANDARD.name()}' href='{NVIDIA_HOWTO}'>How to install</a>"
            label = QtWidgets.QLabel(text)
            label.setWordWrap(True)
            label.setOpenExternalLinks(True)
            self.list.addWidget(mark, i, 0)
            self.list.addWidget(label, i, 1)
        fixable = any(not r["ok"] and r["fix"] for r in self.rows)
        self.go.setEnabled(fixable and self.proc is None)
        self.go.setText("Set up" if fixable else "All set")
        QtCore.QTimer.singleShot(0, self.adjustSize)

    def run(self):
        self.go.setEnabled(False)
        self.later.setEnabled(False)
        self.log.clear()
        self.log.show()
        self.proc = QtCore.QProcess(self)
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc.readyRead.connect(lambda: self.log.appendPlainText(
            bytes(self.proc.readAll()).decode(errors="replace").rstrip()))
        self.proc.finished.connect(self.done)
        self.proc.start("pkexec", ["sh", "-c", script(self.rows)])

    def done(self, code, _status):
        self.proc = None
        self.later.setEnabled(True)
        self.later.setText("Close")
        if code in (126, 127):
            self.log.appendPlainText("\nThe password prompt was cancelled.")
        self.refresh()
        self.main.after_setup()
        self.finished.emit()

    def on_later(self):
        self.main.cfg["setup_later"] = self.main.version
        self.main.save()
        self.close()
