import sys

if "--kbd-idle" in sys.argv:  # run by swayidle; must not start the GUI
    from .backend import kbd_idle
    kbd_idle(sys.argv[sys.argv.index("--kbd-idle") + 1])
    sys.exit(0)

from .ui import main  # noqa: E402

main()
