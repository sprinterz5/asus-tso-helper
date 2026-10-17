"""Once, on the first start after the rename asus-tso-helper -> Shiftray (0.7.0): the settings,
log and journal move to the new folders, and the autostart and menu entries are written again
under the new name. Runs before anything reads the settings (the language is read on import),
so it imports no Qt and nothing that does.

System files from the old name (the udev rule, the CPU boost tmpfiles entry) stay where they
are: renaming them would need a password. system_changes.py and Setup recognise both names.
"""
import os
import shutil

OLD, NEW = "asus-tso-helper", "shiftray"
HOME = os.path.expanduser("~")
FOLDERS = [os.path.join(HOME, ".config"), os.path.join(HOME, ".local", "state"), os.path.join(HOME, ".cache")]
OLD_AUTOSTART = os.path.join(HOME, ".config", "autostart", f"{OLD}.desktop")
OLD_MENU = [os.path.join(HOME, ".local", "share", "applications", f"{OLD}.desktop"),
            os.path.join(HOME, ".local", "share", "icons", "hicolor", "256x256", "apps", f"{OLD}.png")]


LAST = []  # what the last run() did, for the log (which starts later)


def run():
    """-> what was moved (for the log), empty when there was nothing from the old name."""
    done = []
    for base in FOLDERS:
        old, new = os.path.join(base, OLD), os.path.join(base, NEW)
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                shutil.move(old, new)
                done.append(f"{old} -> {new}")
            except OSError as err:
                done.append(f"{old}: not moved ({err})")
    if os.path.exists(OLD_AUTOSTART):
        from .backend.desktop import autostart_entry  # no Qt in there
        from .config import AUTOSTART
        try:
            with open(AUTOSTART, "w") as f:
                f.write(autostart_entry())
            os.remove(OLD_AUTOSTART)
            done.append(f"autostart -> {AUTOSTART}")
        except OSError as err:
            done.append(f"autostart: not moved ({err})")
    for path in OLD_MENU:  # the AppImage writes its menu entry again under the new name
        try:
            os.remove(path)
            done.append(f"removed {path}")
        except OSError:
            pass
    if done and shutil.which("busctl"):  # the window placement script, loaded again as shiftray-place
        os.system("busctl --user call org.kde.KWin /Scripting org.kde.kwin.Scripting unloadScript s "
                  f"{OLD}-place >/dev/null 2>&1")
    LAST[:] = done
    return done
