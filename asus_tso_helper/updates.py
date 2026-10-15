"""'BIOS and Driver Updates' window: G-Helper's app/Updates.cs + UpdatesController.cs.

BIOS comes from the same ASUS support API G-Helper uses. ASUS's drivers are Windows-only, so
"Drivers and Software" lists what matters on Linux instead: kernel, NVIDIA driver, asusctl,
Cardwire, firmware (fwupd) and this app. Updates for packages are what the system's own
repositories offer (PackageKit, the backend of Discover), so a red row is one the user can
actually install; upstream releases are shown in the tooltip.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.request

from PySide6 import QtCore, QtGui, QtWidgets

from . import backend as hw
from . import widgets as w
from .widgets import ECO, TURBO

GITHUB_REPO = "sprinterz5/asus-tso-helper"
SYMBOL_UPDATED = "•"
SYMBOL_NEW = "⬤"
STATUS_NOT_FOUND, STATUS_UPTODATE, STATUS_NEW = 0, 1, 2
USER_AGENT = "asus-tso-helper"


# --- data ---------------------------------------------------------------------------
def fetch_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def version_key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def newer(a, b):
    """a is a newer version than b (both known)."""
    return bool(a and b) and version_key(a) > version_key(b)


def bios_and_model():
    """AppConfig.GetBiosAndModel: 'FA507NV.318' -> ('318', 'FA507NV')."""
    raw = hw._read("/sys/class/dmi/id/bios_version") or ""
    model, _, bios = raw.rpartition(".")
    if not model:
        model, bios = (hw._read("/sys/class/dmi/id/board_name") or raw), ""
    return bios, model


def row(category, title, version, date="", url="", status=STATUS_NOT_FOUND, tip=""):
    return {"category": category, "title": title, "version": version, "date": date,
            "url": url, "status": status, "tip": tip or version}


def fetch_bios():
    """GetPDBIOS; only what can be flashed from Linux (EZ Flash in the BIOS setup):
    the Windows installers and Windows-only firmware tools are left out."""
    bios, model = bios_and_model()
    rog = "&systemCode=rog" if "ROG" in (hw._read("/sys/class/dmi/id/product_name") or "") else ""
    url = (f"https://rog.asus.com/support/webapi/product/GetPDBIOS?website=global"
           f"&model={model}&cpu={model}{rog}")
    data = fetch_json(url)
    rows = []
    for group in ((data.get("Result") or {}).get("Obj") or []):
        name = group.get("Name", "")
        if "windows" in name.lower() or name.lower() != "bios":
            continue
        seen = set()
        for f in group.get("Files") or []:
            title = f.get("Title", "")
            if title in seen:
                continue  # files come newest first: one row per title, like G-Helper
            seen.add(title)
            version = str(f.get("Version", "")).replace("V", "")
            r = row(name, title, version, f.get("ReleaseDate", ""),
                    ((f.get("DownloadUrl") or {}).get("Global") or ""))
            if version.isdigit() and bios.isdigit():
                r["status"] = STATUS_NEW if int(version) > int(bios) else STATUS_UPTODATE
                r["tip"] = f"Download: {version}\nInstalled: {bios}\nFlash it with ASUS EZ Flash (F2 at boot)."
            rows.append(r)
    return rows


def package_version(name):
    """Installed version of a distribution package, whatever the package manager."""
    for cmd in (["rpm", "-q", "--qf", "%{VERSION}", name], ["pacman", "-Q", name],
                ["dpkg-query", "-W", "-f", "${Version}", name]):
        if shutil.which(cmd[0]):
            ok, out = hw.run(*cmd, timeout=5)
            if ok and out:
                return out.split()[-1]
    return None


PACKAGE_ID = re.compile(r"^(?P<name>.+)-(?:\d+:)?(?P<version>[^-]+)-(?P<release>[^-]+)\.(?P<arch>[^.]+)$")


def repo_updates():
    """{package name: version} the system repositories offer (PackageKit, as in Discover)."""
    if not shutil.which("pkcon"):
        return None
    try:
        p = subprocess.run(["pkcon", "get-updates", "--plain"], capture_output=True, text=True,
                           timeout=90, env={**os.environ, "LANG": "C", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and "(" in line:
            m = PACKAGE_ID.match(parts[1])
            if m:
                found.setdefault(m["name"], m["version"])
    return found


def github_latest(repo):
    try:
        data = fetch_json(f"https://api.github.com/repos/{repo}/releases/latest")
    except (OSError, ValueError):
        return None
    return {"version": data.get("tag_name", "").lstrip("v"), "date": (data.get("published_at") or "")[:10],
            "url": data.get("html_url", ""),
            "assets": [{"name": a.get("name"), "url": a.get("browser_download_url"), "size": a.get("size"),
                        "digest": a.get("digest")} for a in data.get("assets") or []]}


# asusctl moved from GitLab to the Open Gaming Collective on GitHub (6.5.0+), next to Cardwire.
# releases/latest skips pre-releases, so only stable versions are offered.
UPSTREAM = {"asusctl": lambda: github_latest("OpenGamingCollective/asusctl"),
            "cardwire": lambda: github_latest("OpenGamingCollective/cardwire")}


def app_latest():
    """Latest release of this app on GitHub, or None (no network, or not published yet)."""
    return github_latest(GITHUB_REPO)


def fetch_linux(app_version):
    """-> (rows, number of package updates the repositories offer for the whole system)."""
    updates = repo_updates()
    checked = updates is not None
    updates = updates or {}

    def from_repo(category, title, installed, names, upstream=None, url="", family=None):
        """family(name) -> True for every package that must be updated together with this row
        (all kernel packages, all NVIDIA packages), so the install button never splits them."""
        offer = next((updates[n] for n in names if n in updates), None)
        if installed is None:
            return None
        r = row(category, title, offer or installed, upstream["date"] if upstream else "", url)
        r["packages"] = sorted(n for n in updates if (family or (lambda n: n in names))(n))
        tip = [f"Installed: {installed}"]
        if offer:
            tip.insert(0, f"Available: {offer}")
        if upstream:
            tip.append(f"Latest upstream: {upstream['version']}")
        r["tip"] = "\n".join(tip)
        if offer and newer(offer, installed):
            r["status"] = STATUS_NEW
        elif checked:
            r["status"] = STATUS_UPTODATE
        return r

    rows = []
    kernel = platform.release().split("-")[0]
    rows.append(from_repo("System", "Linux kernel", kernel, ["kernel", "kernel-core", "linux", "linux-image-generic"],
                          family=lambda n: n == "kernel" or n.startswith(("kernel-", "linux", "linux-"))))
    nvidia = hw._read("/sys/module/nvidia/version") or (hw.run("modinfo", "-F", "version", "nvidia", timeout=5)[1] or None)
    if nvidia and "not found" not in nvidia.lower():
        rows.append(from_repo("Graphics", "NVIDIA driver", nvidia.strip(),
                              ["akmod-nvidia", "xorg-x11-drv-nvidia", "nvidia-driver", "nvidia-utils",
                               "nvidia-open", "nvidia-dkms"], family=lambda n: "nvidia" in n))
    for project, title in (("asusctl", "asusctl (asusd)"), ("cardwire", "Cardwire (GPU modes)")):
        upstream = UPSTREAM[project]()
        rows.append(from_repo("ASUS", title, package_version(project), [project], upstream,
                              upstream["url"] if upstream else "", family=lambda n, p=project: n.startswith(p)))
    ok, out = hw.run("fwupdmgr", "get-updates", "--json", timeout=30) if shutil.which("fwupdmgr") else (False, "")
    if ok:
        try:
            for dev in json.loads(out).get("Devices", []):
                rel = (dev.get("Releases") or [{}])[0]
                rows.append(row("Firmware", dev.get("Name", "?"), rel.get("Version", ""), "", "",
                                STATUS_NEW, f"Installed: {dev.get('Version', '?')}\nAvailable: {rel.get('Version', '?')}"))
        except ValueError:
            pass
    latest = app_latest()
    app = row("App", "asus-tso-helper", latest["version"] if latest else app_version,
              latest["date"] if latest else "", latest["url"] if latest else f"https://github.com/{GITHUB_REPO}")
    if latest:
        app["status"] = STATUS_NEW if newer(latest["version"], app_version) else STATUS_UPTODATE
        app["tip"] = f"Download: {latest['version']}\nInstalled: {app_version}"
    else:
        app["tip"] = f"Installed: {app_version}\nNo release found on GitHub."
    rows.append(app)
    return [r for r in rows if r], len(updates)


def discover_updates():
    """Package rows open the system's updater (Discover on KDE)."""
    for cmd in (["plasma-discover", "--mode", "update"], ["gnome-software", "--mode=updates"]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


# --- window ---------------------------------------------------------------------------
class Table(QtWidgets.QWidget):
    """tableBios / tableDrivers: 23% category, 40% title, 15% date, 22 px symbol, 22% version."""

    def __init__(self):
        super().__init__()
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(10, 4, 10, 10)  # panel Padding(20)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        for col, stretch in enumerate((23, 40, 15, 0, 22)):
            self.grid.setColumnStretch(col, stretch)
        self.grid.setColumnMinimumWidth(3, 22)

    def clear(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def message(self, text):
        self.clear()
        label = QtWidgets.QLabel(text)
        label.setObjectName("tip")
        self.grid.addWidget(label, 0, 0, 1, 5)

    def fill(self, rows, open_row):
        self.clear()
        bold_underline = QtGui.QFont(self.font())
        bold_underline.setBold(True)
        bold_underline.setUnderline(True)
        underline = QtGui.QFont(self.font())
        underline.setUnderline(True)
        for i, r in enumerate(rows):
            for col, text in enumerate((r["category"], r["title"], r["date"])):
                label = QtWidgets.QLabel(text)
                label.setFixedHeight(24)
                label.setContentsMargins(3, 0, 3, 0)
                label.setMinimumWidth(1)
                self.grid.addWidget(label, i, col)
            symbol = QtWidgets.QLabel()
            symbol.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            symbol.setContentsMargins(0, 0, 4, 0)
            version = QtWidgets.QLabel(r["version"])
            version.setCursor(QtCore.Qt.PointingHandCursor)
            version.setToolTip(r["tip"])
            version.setContentsMargins(0, 0, 3, 0)
            colour = ECO
            version.setFont(underline)
            if r["status"] == STATUS_NEW:
                version.setFont(bold_underline)
                colour = TURBO
                symbol.setText(SYMBOL_NEW)
                symbol.setStyleSheet(f"color: {TURBO.name()}; font-size: 5pt;")
            elif r["status"] == STATUS_NOT_FOUND:
                colour = QtGui.QColor("gray")
            else:
                symbol.setText(SYMBOL_UPDATED)
                symbol.setStyleSheet(f"color: {ECO.name()};")
            version.setStyleSheet(f"color: {colour.name()};")
            version.mousePressEvent = lambda _, r=r: open_row(r)
            self.grid.addWidget(symbol, i, 3)
            self.grid.addWidget(version, i, 4)


class TitlePanel(QtWidgets.QWidget):
    """panelBiosTitle / panelDriversTitle: 16 px icon at 14, bold label at 34."""

    def __init__(self, icon_name, title, height):
        super().__init__()
        self.icon_name = icon_name
        self.setFixedHeight(height)
        self.lay = QtWidgets.QHBoxLayout(self)
        self.lay.setContentsMargins(34, 0, 10, 0)
        self.title = QtWidgets.QLabel(title)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.lay.addWidget(self.title)
        self.lay.addStretch()

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.drawPixmap(QtCore.QPointF(14, (self.height() - 16) / 2), w.icon(self.icon_name))


class UpdatesWindow(QtWidgets.QWidget):
    loaded = QtCore.Signal(str, object)

    def __init__(self, main, app_version):
        super().__init__(main, QtCore.Qt.Window)
        self.main = main
        self.app_version = app_version
        self.setObjectName("root")
        self.setAttribute(QtCore.Qt.WA_StyledBackground)
        self.resize(655, 345)  # ClientSize 1310 x 690 at 192 DPI
        self.new_count = 0
        self.pending = 0
        self.system_updates = 0
        self.new_rows = []
        self.proc = None
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.bios_title = TitlePanel("cpu", "BIOS", 30)
        self.status = QtWidgets.QLabel("")
        f = self.status.font()
        f.setBold(True)
        self.status.setFont(f)
        self.bios_title.lay.addWidget(self.status)
        self.refresh_button = w.RButton("", "refresh-cw", secondary=True, radius=2)
        self.refresh_button.setFixedSize(26, 23)
        self.refresh_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.refresh_button.setToolTip("Refresh")
        self.refresh_button.clicked.connect(self.load)
        self.bios_title.lay.addSpacing(8)
        self.bios_title.lay.addWidget(self.refresh_button)
        root.addWidget(self.bios_title)
        self.bios = Table()
        root.addWidget(self.bios)
        drivers_title = TitlePanel("download", "Drivers and Software", 26)
        self.progress = QtWidgets.QLabel("")
        self.progress.setObjectName("tip")
        self.install_button = w.RButton("Install Updates", secondary=True, radius=2)
        self.install_button.setFixedSize(150, 23)
        self.install_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.install_button.clicked.connect(self.install)
        self.install_button.hide()
        drivers_title.lay.addWidget(self.progress)
        drivers_title.lay.addSpacing(8)
        drivers_title.lay.addWidget(self.install_button)
        root.addWidget(drivers_title)
        self.drivers = Table()
        root.addWidget(self.drivers)
        root.addStretch()
        root.addWidget(self.legend())
        self.loaded.connect(self.on_loaded)

    def legend(self):
        """tableLayoutLegend: Legend, grey, red and green chips."""
        box = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(box)
        lay.setContentsMargins(5, 0, 5, 10)  # Padding(10, 0, 10, 20)
        lay.setSpacing(5)
        items = [("Legend", None), ("Can't check local version", QtGui.QColor("gray")),
                 (f"<span style='font-size:5pt'>{SYMBOL_NEW}</span>&nbsp; Update Available", TURBO),
                 (f"{SYMBOL_UPDATED} Updated", ECO)]
        for i, (text, colour) in enumerate(items):
            label = QtWidgets.QLabel(text)
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setFixedHeight(22)
            if colour is not None:
                label.setStyleSheet(f"background: {colour.name()}; color: white; border-radius: 2px; padding: 0 6px;")
            lay.addWidget(label, 15 if i == 0 else 28)
        return box

    def load(self):
        if self.pending:
            return  # a check is already running
        bios, model = bios_and_model()
        self.setWindowTitle(f"BIOS and Driver Updates: {model} {bios}".strip())
        self.new_count = 0
        self.pending = 2
        self.new_rows = []
        self.install_button.hide()
        self.set_status()
        self.bios.message("Checking ...")
        self.drivers.message("Checking ... (asks the system for package updates)")

        def job(kind, fn, *args):
            def run():
                try:
                    result = fn(*args)
                except Exception as err:  # network down, API changed: show it instead of crashing
                    result = err
                self.loaded.emit(kind, result)
            self.main.pool.submit(run)
        job("bios", fetch_bios)
        job("drivers", fetch_linux, self.app_version)

    def on_loaded(self, kind, result):
        table = self.bios if kind == "bios" else self.drivers
        self.pending -= 1
        if kind == "drivers" and not isinstance(result, Exception):
            result, self.system_updates = result
            self.new_rows = [r for r in result if r["status"] == STATUS_NEW and r.get("packages")]
            self.install_button.setVisible(bool(self.new_rows) and self.proc is None)
            self.install_button.setText(f"Install Updates ({len(self.new_rows)})")
        if isinstance(result, Exception):
            table.message(f"Could not check: {result}")
        elif not result:
            table.message("Nothing found for this model.")
        else:
            table.fill(result, self.open_row)
            self.new_count += sum(r["status"] == STATUS_NEW for r in result)
        self.set_status()

    def set_status(self):
        f = self.status.font()
        if self.new_count:
            self.status.setText(f"New updates: {self.new_count}")
            self.status.setStyleSheet(f"color: {TURBO.name()};")
            f.setUnderline(True)
        else:
            self.status.setText("Checking ..." if self.pending else "No new updates")
            self.status.setStyleSheet(f"color: {ECO.name()};" if not self.pending else "")
            f.setUnderline(False)
        self.status.setFont(f)

    # -- one-button install: PackageKit offline update, as Discover does it ----------------
    def install(self):
        """Only the red rows (with every package that belongs to them); the rest of the system
        stays with Discover. Downloaded now, installed while restarting."""
        packages = sorted({p for r in self.new_rows for p in r["packages"]})
        listed = "".join(f"\n  {r['title']} {r['version']}" for r in self.new_rows)
        others = self.system_updates - len(packages)
        answer = QtWidgets.QMessageBox.question(
            self, "Install Updates",
            f"Download these updates now and install them while the laptop restarts?{listed}\n\n"
            f"({len(packages)} packages.{f' The other {others} system updates stay in Discover.' if others > 0 else ''})"
            "\n\nBIOS updates are not included: flash them with ASUS EZ Flash (F2 at boot).")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        self.install_button.hide()
        self.refresh_button.setEnabled(False)
        self.packages = packages
        self.run_step(["pkcon", "update", "--only-download", "--noninteractive", "--plain", *packages],
                      self.downloaded, "Downloading updates")

    def run_step(self, cmd, then, label):
        self.progress.setText(label + " ...")
        self.proc = QtCore.QProcess(self)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("LANG", "C")
        env.insert("LC_ALL", "C")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc_output = ""

        def read():
            text = bytes(self.proc.readAll()).decode(errors="replace")
            self.proc_output += text
            for pct in re.findall(r"Percentage:\s*(\d+)", text):
                self.progress.setText(f"{label} ... {pct}%")

        def finished(code, _status):
            output = self.proc_output
            self.proc = None
            then(code == 0, output)
        self.proc.readyRead.connect(read)
        self.proc.finished.connect(finished)
        self.proc.start(cmd[0], cmd[1:])

    def downloaded(self, ok, output):
        if not ok:
            return self.install_failed("Downloading the updates failed.", output)
        self.run_step(["pkcon", "offline-trigger"], self.triggered, "Preparing the restart")

    def triggered(self, ok, output):
        if not ok:
            # no offline updates here (e.g. Arch): install right away, then a restart finishes it
            self.run_step(["pkcon", "update", "--noninteractive", "--plain", *self.packages],
                          self.installed_online, "Installing updates")
            return
        self.progress.setText("Ready: installs on restart")
        self.ask_restart("The updates are downloaded and will be installed while the laptop restarts.")

    def installed_online(self, ok, output):
        if not ok:
            return self.install_failed("Installing the updates failed.", output)
        self.progress.setText("Installed")
        self.ask_restart("The updates are installed. Restart so the new kernel and drivers are used.")

    def ask_restart(self, text):
        self.refresh_button.setEnabled(True)
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Information, "Install Updates", text, parent=self)
        now = box.addButton("Restart now", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is now:
            subprocess.Popen(["systemctl", "reboot"])

    def install_failed(self, text, output):
        self.refresh_button.setEnabled(True)
        self.install_button.show()
        self.progress.setText("")
        tail = "\n".join(output.strip().splitlines()[-6:])
        QtWidgets.QMessageBox.warning(self, "Install Updates", f"{text}\n\n{tail}")

    def open_row(self, r):
        if r["category"] == "App" and r["status"] == STATUS_NEW and self.main.can_self_update():
            self.main.self_update()
            return
        if r["category"] in ("System", "Graphics", "Firmware") or (r["category"] == "ASUS" and r["status"] == STATUS_NEW):
            if discover_updates():
                return
        if r["url"]:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(r["url"]))
