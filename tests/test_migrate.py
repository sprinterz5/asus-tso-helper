"""The one-time move from asus-tso-helper to Shiftray, in a throwaway home folder."""
import os
import tempfile
import unittest
from unittest import mock

from shiftray import migrate


class Migrate(unittest.TestCase):
    def test_settings_log_and_autostart_move(self):
        home = tempfile.mkdtemp()
        for sub in (".config/asus-tso-helper", ".local/state/asus-tso-helper", ".config/autostart"):
            os.makedirs(os.path.join(home, sub))
        with open(os.path.join(home, ".config/asus-tso-helper/config.json"), "w") as f:
            f.write('{"language": "ru"}')
        old_autostart = os.path.join(home, ".config/autostart/asus-tso-helper.desktop")
        open(old_autostart, "w").close()
        new_autostart = os.path.join(home, ".config/autostart/shiftray.desktop")
        folders = [os.path.join(home, p) for p in (".config", ".local/state", ".cache")]
        with mock.patch.object(migrate, "FOLDERS", folders), \
                mock.patch.object(migrate, "OLD_AUTOSTART", old_autostart), \
                mock.patch.object(migrate, "OLD_MENU", []), \
                mock.patch.object(migrate, "LAST", []), \
                mock.patch("shiftray.config.AUTOSTART", new_autostart), \
                mock.patch.object(migrate.shutil, "which", return_value=None):
            done = migrate.run()
            self.assertTrue(done)
            with open(os.path.join(home, ".config/shiftray/config.json")) as f:
                self.assertIn("ru", f.read())
            self.assertTrue(os.path.isdir(os.path.join(home, ".local/state/shiftray")))
            self.assertFalse(os.path.exists(old_autostart))
            with open(new_autostart) as f:
                self.assertIn("Name=Shiftray", f.read())
            self.assertEqual(migrate.run(), [])  # the second start finds nothing to move


if __name__ == "__main__":
    unittest.main()
