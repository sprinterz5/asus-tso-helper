"""Battery tips (ui.MainWindow): run on a stand-in for the window, no display or hardware needed."""
import time
import types
import unittest
from unittest import mock

from shiftray import backend as hw
from shiftray import ui
from shiftray.backend import battery


def window(**state):
    """The attributes the tips read, plus bg() that runs at once and tip() that records."""
    w = types.SimpleNamespace(cfg={}, tips=[], last_ac=False, dgpu_was_awake=True, gpu_current="Hybrid",
                              dgpu_apps=[], dgpu_seen={}, dgpu_told={}, sleep_mark=None)
    w.__dict__.update(state)
    w.bg = lambda fn, *args, then=None, key=None: then(fn(*args)) if then else fn(*args)
    w.tip = lambda icon, body, action=None, then=None: w.tips.append((body, action))
    w.on_extra = w.on_gpu = lambda *a: None
    return w


class TimeToLimit(unittest.TestCase):
    def test_counts_to_the_limit_not_to_full(self):
        with mock.patch.object(battery, "battery_energy", return_value=(40.0, 80.0)), \
                mock.patch.object(battery, "battery_status",
                                  return_value={"percent": 50, "status": "Charging", "watts": 20.0}):
            self.assertEqual(battery.time_to_limit(80), 24 / 20 * 3600)  # 24 Wh missing at 20 W
            self.assertIsNone(battery.time_to_limit(40))                  # already there

    def test_battery_time_uses_the_limit_while_charging(self):
        with mock.patch.object(battery, "run", return_value=(True, "x 0")), \
                mock.patch.object(battery, "time_to_limit", return_value=1800):
            self.assertEqual(battery.battery_time(80), ("to limit", 1800))


class DgpuOnBattery(unittest.TestCase):
    def test_one_notification_lists_every_app(self):
        w = window(dgpu_apps=["code", "firefox"])
        with mock.patch.object(hw, "dgpu_games", return_value=[]), \
                mock.patch.object(hw, "dgpu_watts", return_value=8.2):
            ui.MainWindow.check_dgpu_on_battery(w)             # first seen now: too early
            self.assertEqual(w.tips, [])
            later = time.monotonic() + ui.DGPU_AWAKE_TELL + 1
            with mock.patch.object(time, "monotonic", return_value=later):
                ui.MainWindow.check_dgpu_on_battery(w)
                ui.MainWindow.check_dgpu_on_battery(w)         # told already: not again today
        self.assertEqual(len(w.tips), 1)
        self.assertIn("code, firefox", w.tips[0][0])
        self.assertIn("8 W", w.tips[0][0])

    def test_quiet_while_gaming_or_charging(self):
        later = time.monotonic() + ui.DGPU_AWAKE_TELL + 1
        w = window(dgpu_apps=["steam"], dgpu_seen={"steam": 0.0})
        with mock.patch.object(hw, "dgpu_games", return_value=["Cyberpunk 2077"]), \
                mock.patch.object(hw, "dgpu_watts", return_value=40.0), \
                mock.patch.object(time, "monotonic", return_value=later):
            ui.MainWindow.check_dgpu_on_battery(w)
            w2 = window(dgpu_apps=["firefox"], dgpu_seen={"firefox": 0.0}, last_ac=True)
            ui.MainWindow.check_dgpu_on_battery(w2)
        self.assertEqual(w.tips + w2.tips, [])


class SleepReport(unittest.TestCase):
    def test_small_drain_is_just_reported(self):
        w = window(sleep_mark=(time.time() - 8 * 3600, (60.0, 80.0), False))
        with mock.patch.object(hw, "battery_energy", return_value=(56.0, 80.0)), \
                mock.patch.object(hw, "deep_sleep", return_value=False):
            ui.MainWindow.report_sleep(w, ac=False)
        self.assertEqual(len(w.tips), 1)
        self.assertIn("5%", w.tips[0][0])        # 4 of 80 Wh
        self.assertIsNone(w.tips[0][1])          # 0.6 %/h: no deep sleep button

    def test_big_drain_offers_deep_sleep(self):
        w = window(sleep_mark=(time.time() - 8 * 3600, (60.0, 80.0), False))
        with mock.patch.object(hw, "battery_energy", return_value=(44.0, 80.0)), \
                mock.patch.object(hw, "deep_sleep", return_value=False):
            ui.MainWindow.report_sleep(w, ac=False)
        self.assertIsNotNone(w.tips[0][1])

    def test_charging_is_not_reported(self):
        w = window(sleep_mark=(time.time() - 8 * 3600, (60.0, 80.0), True))
        with mock.patch.object(hw, "battery_energy", return_value=(70.0, 80.0)):
            ui.MainWindow.report_sleep(w, ac=True)
        self.assertEqual(w.tips, [])


if __name__ == "__main__":
    unittest.main()
