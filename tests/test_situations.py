"""Situations (situations.py): settings, the tile's line, and when the laptop is still in one."""
import unittest

from shiftray import situations as sit


class Situations(unittest.TestCase):
    def test_changes_go_on_top_of_the_defaults(self):
        cfg = {}
        sit.set_value(cfg, "go", "screen", "auto")
        self.assertEqual(sit.get(cfg, "go")["screen"], "auto")
        self.assertEqual(sit.get(cfg, "go")["mode"], "quiet")       # untouched default
        self.assertEqual(sit.get({}, "go")["screen"], "60")          # other configs keep the default

    def test_line_says_all_four(self):
        self.assertEqual(sit.summary({}, "quiet"), "Silent · Optimized · Auto · lights off")
        self.assertEqual(sit.summary({}, "gaming", screen_max="144Hz + OD"),
                         "Turbo · Standard · 144Hz + OD · lights high")

    def test_ultimate_is_a_choice(self):
        cfg = {}
        sit.set_value(cfg, "gaming", "gpu", "AsusMuxDgpu")
        self.assertEqual(sit.summary(cfg, "gaming"), "Turbo · Ultimate · Max · lights high")
        self.assertTrue(sit.matches(cfg, "gaming", "performance", "AsusMuxDgpu", False))

    def test_old_keep_values_fall_back_to_the_default(self):
        self.assertEqual(sit.get({"situations": {"quiet": {"gpu": None}}}, "quiet")["gpu"], "auto")

    def test_matches(self):
        self.assertTrue(sit.matches({}, "go", "quiet", "Integrated", False))
        self.assertFalse(sit.matches({}, "go", "balanced", "Integrated", False))       # Fn+F5 ended it
        self.assertFalse(sit.matches({}, "go", "quiet", "Integrated", True))           # Optimized took over
        self.assertTrue(sit.matches({}, "quiet", "quiet", "Hybrid", True))             # Optimized, plugged in
        self.assertFalse(sit.matches({"active_mode": "x"}, "go", "quiet", "Integrated", False))  # a custom mode

    def test_without_a_dgpu_the_gpu_mode_is_left_out(self):
        self.assertEqual(sit.summary({}, "go", gpu_modes=False), "Silent · 60Hz · lights low")
        self.assertTrue(sit.matches({}, "go", "quiet", None, False, gpu_modes=False))


if __name__ == "__main__":
    unittest.main()
