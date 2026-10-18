"""Parsers in backend/: fed the real output format of each tool, no hardware needed."""
import os
import subprocess
import time
import unittest
from unittest import mock

from shiftray import backend as hw
from shiftray.backend import battery, gpu


class Facade(unittest.TestCase):
    def test_every_hw_name_used_by_the_app_exists(self):
        """`hw.<name>` anywhere in the app must be re-exported by backend/__init__.py."""
        import glob
        import re
        root = os.path.join(os.path.dirname(__file__), "..", "shiftray")
        missing = set()
        for path in glob.glob(os.path.join(root, "*.py")):
            with open(path) as f:
                for name in re.findall(r"\bhw\.(\w+)", f.read()):
                    if not hasattr(hw, name):
                        missing.add(f"{os.path.basename(path)}: hw.{name}")
        self.assertEqual(missing, set())


class SysfsCache(unittest.TestCase):
    def setUp(self):
        from shiftray.backend import common
        self.common = common
        common._found.clear()

    def test_found_path_is_kept_until_it_disappears(self):
        find = mock.Mock(return_value="/sys/class/hwmon/hwmon3")
        with mock.patch.object(os.path, "exists", return_value=True) as exists:
            self.assertEqual(self.common._cached("k", find), "/sys/class/hwmon/hwmon3")
            self.common._cached("k", find)
            self.assertEqual(find.call_count, 1)
            exists.return_value = False  # gone (a driver reloaded): look again
            self.common._cached("k", find)
            self.assertEqual(find.call_count, 2)

    def test_nothing_found_is_looked_for_again_later(self):
        find = mock.Mock(return_value=None)
        self.assertIsNone(self.common._cached("k", find))
        self.common._cached("k", find)
        self.assertEqual(find.call_count, 1)
        with mock.patch.object(time, "monotonic", return_value=time.monotonic() + 61):
            self.common._cached("k", find)
        self.assertEqual(find.call_count, 2)


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


class CardwireRetry(unittest.TestCase):
    def test_missed_dgpu_is_looked_for_again(self):
        calls = []
        answers = iter([(False, "Couldn't set mode to Integrated, Integrated and Smart modes require a offload "
                                 "discrete GPU"), (True, ""), (True, "")])
        with mock.patch.object(gpu, "run", side_effect=lambda *a, **k: calls.append(a) or next(answers)):
            self.assertEqual(gpu.set_cardwire_mode("Integrated"), (True, ""))
        self.assertTrue(any("RefreshGpu" in c for c in calls))


class CardwireLookup(unittest.TestCase):
    def setUp(self):
        gpu._cardwire_dgpu.clear()
        gpu._cardwire_missed[0] = None

    tearDown = setUp

    def test_no_dgpu_is_not_asked_every_refresh(self):
        """A laptop without a dGPU (or Cardwire that missed it): one look a minute, not every 2 s."""
        with mock.patch.object(gpu, "run", return_value=(False, "no such object")) as run:
            self.assertIsNone(gpu.cardwire_dgpu())
            self.assertIsNone(gpu.cardwire_dgpu())
            self.assertEqual(run.call_count, 1)
            with mock.patch.object(time, "monotonic", return_value=time.monotonic() + 61):
                gpu.cardwire_dgpu()
            self.assertEqual(run.call_count, 2)

    def test_found_dgpu_is_kept(self):
        answers = [(True, 'ssuubbbbssbs "AMD Radeon 660M" "0000:36:00.0" 128 1 true false false true "AMD" "amdgpu" false "none"'),
                   (True, 'ssuubbbbssbs "NVIDIA GeForce RTX 4060 Laptop GPU" "0000:01:00.0" 129 0 false true false true "Nvidia" "nvidia" true "0"')]
        with mock.patch.object(gpu, "run", side_effect=answers) as run:
            self.assertTrue(gpu.cardwire_dgpu().endswith("/Gpu/1"))
            self.assertTrue(gpu.cardwire_dgpu().endswith("/Gpu/1"))
            self.assertEqual(run.call_count, 2)


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
