"""A game starts, the mode changes; it quits, the power source's own mode comes back."""
import os
import tempfile
import unittest
from unittest import mock

from shiftray import window_games
from shiftray.backend import gpu


class FakeWindow(window_games.GamesMixin):
    """The main window's parts the mixin uses: on_profile / on_power_source as G-Helper's."""

    def __init__(self, ac=True, **cfg):
        self.cfg = {"game_mode_on": True, "mode_ac": "balanced", "mode_bat": "quiet", **cfg}
        self.last_ac = ac
        self.picked = []
        self.notes = []
        self.games, self.game_set, self.game_user = [], None, False

    def on_profile(self, key, notify=False, remember=True):
        if remember:
            self.cfg["mode_ac" if self.last_ac else "mode_bat"] = key
            self.game_mode_picked()
        self.cfg["active_mode"] = key
        self.picked.append(key)

    def on_power_source(self, ac):
        if self.games and self.switch_for_game():
            return
        self.game_set = None
        self.cfg["active_mode"] = self.cfg["mode_ac" if ac else "mode_bat"]
        self.picked.append(self.cfg["active_mode"])

    def notify(self, icon, body, *a):
        self.notes.append(body)

    def start(self, title="Cyberpunk 2077"):
        self.games = [title]
        self.games_started()


class GameMode(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(window_games.hw, "get_profile", return_value="balanced")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_game_gets_turbo_and_the_mode_comes_back(self):
        win = FakeWindow(active_mode="balanced")
        win.start()
        self.assertEqual(win.cfg["active_mode"], "performance")
        self.assertEqual(win.cfg["mode_ac"], "balanced")  # not remembered as the charger's mode
        win.games_ended()
        self.assertEqual(win.cfg["active_mode"], "balanced")
        self.assertEqual(len(win.notes), 2)
        self.assertIn("Cyberpunk 2077", win.notes[0])

    def test_unplugged_during_the_game(self):
        win = FakeWindow(active_mode="balanced")
        win.start()
        win.last_ac = False
        win.on_power_source(False)
        self.assertEqual(win.cfg["active_mode"], "balanced")  # the battery's game mode
        win.games_ended()
        self.assertEqual(win.cfg["active_mode"], "quiet")     # the battery's own mode

    def test_dont_change_on_battery(self):
        win = FakeWindow(ac=False, active_mode="quiet", game_mode_bat=window_games.KEEP)
        win.start()
        self.assertEqual(win.picked, [])
        win.games_ended()
        self.assertEqual(win.picked, [])  # nothing was switched, nothing to put back
        self.assertEqual(win.notes, [])

    def test_picked_by_hand_wins(self):
        win = FakeWindow(active_mode="balanced")
        win.start()
        win.on_profile("quiet")  # the user, during the game
        win.last_ac = False
        win.on_power_source(False)
        self.assertEqual(win.cfg["active_mode"], "quiet")
        win.games_ended()
        self.assertEqual(win.cfg["active_mode"], "quiet")
        self.assertEqual(len(win.notes), 1)  # no "back to" after the user took over

    def test_a_deleted_custom_mode_is_ignored(self):
        win = FakeWindow(active_mode="balanced", game_mode_ac="custom-gone")
        win.start()
        self.assertEqual(win.picked, [])


class SteamTitle(unittest.TestCase):
    def test_name_from_a_second_library(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(home, ".local/share/Steam/steamapps")
            lib = os.path.join(home, "Games/SteamLibrary")
            os.makedirs(root)
            os.makedirs(os.path.join(lib, "steamapps"))
            with open(os.path.join(root, "libraryfolders.vdf"), "w") as f:
                f.write(f'"libraryfolders"\n{{\n "0"\n {{\n  "path"  "{lib}"\n }}\n}}\n')
            with open(os.path.join(lib, "steamapps", "appmanifest_1091500.acf"), "w") as f:
                f.write('"AppState"\n{\n "appid" "1091500"\n "name" "Cyberpunk 2077"\n}\n')
            gpu._steam_titles.clear()
            with mock.patch.dict(os.environ, {"HOME": home}):
                self.assertEqual(gpu.steam_title("1091500"), "Cyberpunk 2077")
                self.assertIsNone(gpu.steam_title("42"))
            gpu._steam_titles.clear()

    def test_wine_helpers_are_not_games(self):
        with mock.patch.object(gpu, "game_name", return_value="winedevice.exe"):
            self.assertIsNone(gpu.game_title(1))

    def test_scan_reads_only_new_processes(self):
        with mock.patch.object(gpu.os, "listdir", return_value=["1", "2", "self"]), \
                mock.patch.object(gpu, "game_title", return_value="Game") as title:
            self.assertEqual(gpu.scan_games({1: None}), {1: None, 2: "Game"})
            title.assert_called_once_with(2)


class ChargedWhileOff(unittest.TestCase):
    def run_check(self, before, now, limit=80):
        from shiftray import ui
        tips = []
        win = mock.Mock(cfg={"off_mark": {"time": 0, "percent": before, "limit": limit}})
        win.tip = lambda icon, body: tips.append(body)
        with mock.patch.object(ui.hw, "battery_status", return_value={"percent": now}):
            ui.MainWindow.check_charged_while_off(win)
        self.assertNotIn("off_mark", win.cfg)  # said once
        return tips

    def test_past_the_limit(self):
        self.assertEqual(len(self.run_check(60, 98)), 1)

    def test_held_or_a_quick_reboot(self):
        self.assertEqual(self.run_check(60, 61), [])
        self.assertEqual(self.run_check(80, 81), [])
        self.assertEqual(self.run_check(60, 99, limit=100), [])


if __name__ == "__main__":
    unittest.main()
