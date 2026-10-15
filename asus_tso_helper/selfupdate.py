"""Self-update of the AppImage: G-Helper's AutoUpdateControl, for one file instead of a zip.

The new AppImage is downloaded next to the running one, checked against the size and SHA-256
that GitHub publishes for the release asset, then renamed over it. The running app keeps the
old file open until it quits, so the swap is safe; the app then restarts from the new file.
Runs from a source checkout or a distribution package only point to the release page.
"""
import hashlib
import os
import subprocess
import urllib.request

from . import backend as hw

ASSET = "asus-tso-helper-x86_64.AppImage"
USER_AGENT = "asus-tso-helper"


def possible():
    """Running as an AppImage the user can replace."""
    path = hw.APPIMAGE
    return bool(path) and os.access(path, os.W_OK) and os.access(os.path.dirname(path), os.W_OK)


def asset_of(release):
    """The AppImage asset of a release from updates.github_latest, or None."""
    return next((a for a in (release or {}).get("assets", []) if a.get("name") == ASSET), None)


def download(asset, progress=None):
    """-> (ok, path of the checked new file or an error). progress(percent) while downloading."""
    target = hw.APPIMAGE + ".part"
    digest = (asset.get("digest") or "").partition("sha256:")[2]
    sha = hashlib.sha256()
    size = 0
    try:
        req = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r, open(target, "wb") as f:
            total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
            while chunk := r.read(1 << 16):
                f.write(chunk)
                sha.update(chunk)
                size += len(chunk)
                if progress and total:
                    progress(size * 100 // total)
    except OSError as err:
        _remove(target)
        return False, f"Download failed: {err}"
    if asset.get("size") and size != asset["size"]:
        _remove(target)
        return False, f"Download incomplete ({size} of {asset['size']} bytes)."
    if digest and sha.hexdigest() != digest:
        _remove(target)
        return False, "The download does not match the release's checksum."
    os.chmod(target, 0o755)
    return True, target


def install(path):
    """Put the new file in place of the running AppImage (same directory, so an atomic rename)."""
    try:
        os.replace(path, hw.APPIMAGE)
    except OSError as err:
        _remove(path)
        return False, str(err)
    return True, ""


def restart():
    """Starts the new AppImage once this process has quit (one instance at a time)."""
    script = 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; exec "$2"'
    subprocess.Popen(["sh", "-c", script, "sh", str(os.getpid()), hw.APPIMAGE],
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
