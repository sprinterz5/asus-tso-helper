"""Parsers in backend/: fed the real output format of each tool, no hardware needed."""
import os
import subprocess
import time
import unittest
from unittest import mock

from asus_tso_helper import backend as hw
from asus_tso_helper.backend import battery, gpu


class Facade(unittest.TestCase):
    def test_every_hw_name_used_by_the_app_exists(self):
        """`hw.<name>` anywhere in the app must be re-exported by backend/__init__.py."""
        import glob
        import re
        root = os.path.join(os.path.dirname(__file__), "..", "asus_tso_helper")
        missing = set()
        for path in glob.glob(os.path.join(root, "*.py")):
            with open(path) as f:
                for name in re.findall(r"\bhw\.(\w+)", f.read()):
                    if not hasattr(hw, name):
                        missing.add(f"{os.path.basename(path)}: hw.{name}")
        self.assertEqual(missing, set())


class Cardwire(unittest.TestCase):
    def test_dgpu_users_parses_lsof(self):
        # busctl prints a{sas}: count, then per node: path, count, names
        out = 'a{sas} 2 "/dev/nvidia0" 2 "steam" "kwin_wayland" "/dev/dri/card1" 1 "firefox"'
        with mock.patch.object(gpu, "cardwire_dgpu", return_value="/gpu"), \
                mock.patch.object(gpu, "run", return_value=(True, out)):
            self.assertEqual(gpu.dgpu_users(), ["firefox", "steam"])  # the desktop's own are left out

    def test_last_blocked(self):
        out = 'a((tu)usus) 2 1700000000 5 111 "chrome" 1 "" 1700000100 7 4242 "game.exe" 1 "steam_app_1"'
        with mock.patch.object(gpu, "run", return_value=(True, out)):
            self.assertEqual(gpu.cardwire_last_blocked(), (4242, "game.exe"))

    def test_last_blocked_empty(self):
        with mock.patch.object(gpu, "run", return_value=(True, "a((tu)usus) 0")):
            self.assertIsNone(gpu.cardwire_last_blocked())


class Games(unittest.TestCase):
    def _spawn(self, env):
        p = subprocess.Popen(["sleep", "5"], env=dict(os.environ, **env))
        self.addCleanup(lambda: (p.kill(), p.wait()))
        time.sleep(0.1)
        return p.pid

    def test_steam_game(self):
        self.assertEqual(gpu.game_name(self._spawn({"SteamAppId": "1091500"})), "sleep")

    def test_wine_game(self):
        self.assertEqual(gpu.game_name(self._spawn({"WINEPREFIX": "/tmp/x"})), "sleep")

    def test_not_a_game(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("Steam", "STEAM", "WINE"))}
        p = subprocess.Popen(["sleep", "5"], env=env)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        time.sleep(0.1)
        self.assertIsNone(gpu.game_name(p.pid))


class Battery(unittest.TestCase):
    def test_history_parses_upower(self):
        out = "a(udu) 3 1700000300 13 2 1700000200 57.2 2 1700000100 0 0"
        with mock.patch.object(battery, "run", return_value=(True, out)):
            rows = battery.battery_history("charge", 3600)
        self.assertEqual(rows, [(1700000100, 0.0, 0), (1700000200, 57.2, 2), (1700000300, 13.0, 2)])

    def test_watts_per_mode(self):
        now = int(time.time())
        rate = [(now - 3000, 20.0, 2), (now - 2400, 20.0, 2), (now - 1800, 10.0, 2), (now - 1200, 10.0, 2)]
        with mock.patch.object(battery, "mode_log_lines", return_value=[(now - 4000, "performance"),
                                                                         (now - 2000, "quiet")]), \
                mock.patch.object(battery, "battery_history", return_value=rate):
            modes = battery.watts_per_mode(86400)
        self.assertAlmostEqual(modes["performance"][0], 20.0)
        self.assertAlmostEqual(modes["quiet"][0], 10.0)


if __name__ == "__main__":
    unittest.main()
