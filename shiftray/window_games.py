"""Main window, part: a game starts, the mode changes (Extra → "When a game runs, switch the mode").

A mixin: its methods run as MainWindow methods (self is the main window).

Off by default. While on, the running processes are looked at every few seconds (only new ones,
a few files each: backend.scan_games); Steam, Proton, Wine, Lutris and Heroic games leave their
marks in the environment. The game's mode is not remembered as the power source's mode, so when
the last game quits, the mode remembered for the power source comes back. Picking a mode while
a game runs ends the switching until the next game.
"""
from PySide6 import QtCore

from . import backend as hw
from . import modes
from .i18n import tr

GAME_SCAN_MS = 4000
KEEP = "keep"  # "Don't change" in Extra
GAME_DEFAULTS = {"game_mode_ac": "performance", "game_mode_bat": "balanced"}


class GamesMixin:
    def init_games(self):
        self.game_pids = {}      # pid -> game title or None, from the last scan
        self.games = []          # titles of the games running now
        self.game_set = None     # the mode a game put on, while it stays on
        self.game_user = False   # the mode was picked by hand during this game: hands off
        self.game_timer = QtCore.QTimer(self)
        self.game_timer.setInterval(GAME_SCAN_MS)
        self.game_timer.timeout.connect(self.scan_games)
        self.apply_game_mode()

    def apply_game_mode(self):
        """The Extra checkbox changed (or at start)."""
        if self.cfg.get("game_mode_on"):
            if not self.game_timer.isActive():
                self.game_pids = {}
                self.game_timer.start()
                self.scan_games()
        else:
            self.game_timer.stop()
            if self.games:
                self.games_ended()

    def game_target(self, ac):
        """The mode a game gets on this power source, or None (Don't change, or a deleted mode)."""
        key = self.cfg.get("game_mode_ac" if ac else "game_mode_bat") or GAME_DEFAULTS["game_mode_ac" if ac else
                                                                                        "game_mode_bat"]
        return key if key != KEEP and key in [m[0] for m in modes.all_modes(self.cfg)] else None

    def scan_games(self):
        def found(pids):
            self.game_pids = pids
            games = sorted({t for t in pids.values() if t})
            if games and not self.games:
                self.games = games
                self.games_started()
            elif not games and self.games:
                self.games_ended()
            else:
                self.games = games
        self.bg(hw.scan_games, dict(self.game_pids), then=found, key="games")

    def games_started(self):
        self.game_user = False
        self.switch_for_game()

    def switch_for_game(self):
        """The mode for a running game on the present power source, unless picked by hand."""
        ac = bool(self.last_ac if self.last_ac is not None else hw.ac_online())
        target = self.game_target(ac)
        if self.game_user or target is None:
            return False
        current = self.cfg.get("active_mode") or hw.get_profile()
        self.game_set = target
        if target != current:
            self.on_profile(target, remember=False)
            self.notify("input-gaming", tr("{game} started: {mode}", game=self.games[0],
                                           mode=modes.name_of(self.cfg, target)))
        return True

    def games_ended(self):
        """The last game quit: the power source's own mode comes back, if the game's is still on."""
        game, self.games = (self.games or [""])[0], []
        if self.game_set is None:
            return
        self.game_set = None
        ac = bool(self.last_ac if self.last_ac is not None else hw.ac_online())
        back = self.cfg.get("mode_ac" if ac else "mode_bat")
        self.on_power_source(ac)
        if back:
            self.notify("input-gaming", tr("{game} closed: back to {mode}", game=game,
                                           mode=modes.name_of(self.cfg, back)))

    def game_mode_picked(self):
        """A mode picked by hand (window, tray, key) while a game runs wins until the game ends."""
        if self.games:
            self.game_user = True
            self.game_set = None
