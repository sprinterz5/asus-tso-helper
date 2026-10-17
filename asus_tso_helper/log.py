"""The app's log: ~/.local/state/asus-tso-helper/app.log (two files of 512 KB at most).

Normal runs keep warnings and errors, plus one line per action the user takes. Start with
--debug (or ASUS_TSO_DEBUG=1) to also log every command the app runs, with its exit code, time
and output, and to print everything to the terminal. Extra -> Diagnostics attaches the tail.
"""
import logging
import logging.handlers
import os
import sys
import threading

LOG_FILE = os.path.expanduser("~/.local/state/asus-tso-helper/app.log")
log = logging.getLogger("asus-tso-helper")


def setup(debug=False):
    debug = debug or os.environ.get("ASUS_TSO_DEBUG") == "1"
    log.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(threadName)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=512 * 1024, backupCount=1)
        handler.setFormatter(fmt)
        log.addHandler(handler)
    except OSError:
        pass  # read-only home: the app still works, it just keeps no log
    if debug:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        log.addHandler(console)

    # a crash anywhere, in the GUI thread or a background job, ends up in the log
    def hook(kind, value, tb):
        log.error("uncaught exception", exc_info=(kind, value, tb))
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = hook
    threading.excepthook = lambda a: log.error(f"uncaught exception in {a.thread.name if a.thread else '?'}",
                                               exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    log.info(f"start, debug={debug}")
    return debug


def tail(lines=200):
    try:
        with open(LOG_FILE, errors="replace") as f:
            return f.read().splitlines()[-lines:]
    except OSError:
        return []
