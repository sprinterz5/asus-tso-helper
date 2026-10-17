"""Root scripts, the system changes registry, update parsing and translations."""
import ast
import glob
import json
import os
import re
import tempfile
import unittest
from unittest import mock

from asus_tso_helper import setup, system_changes as sc, updates

ROOT = os.path.join(os.path.dirname(__file__), "..", "asus_tso_helper")


class SetupScript(unittest.TestCase):
    def rows(self, *keys):
        return [{"key": k, "ok": False, "fix": True} for k in keys]

    def test_fedora_steps(self):
        with mock.patch.object(setup, "distro", return_value="fedora"):
            text = setup.script(self.rows("terra", "asusd", "cardwire", "keys"))
        for part in ("terra-release", "dnf install -y asusctl", "cardwire", "udevadm", "== Done"):
            self.assertIn(part, text)

    def test_nothing_to_do(self):
        with mock.patch.object(setup, "distro", return_value="fedora"):
            self.assertNotIn("dnf", setup.script([]))

    def test_every_root_step_is_a_listed_change(self):
        """Setup may only do what System changes can show (and mostly undo)."""
        keys = {c.key for c in sc.changes()}
        self.assertTrue(setup.todo_changes({"terra", "asusd", "python", "swayidle", "cardwire", "ppd",
                                            "keys", "boost"}) <= keys)


class SystemChanges(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        patch = mock.patch.object(sc, "JOURNAL", os.path.join(tmp, "changes.json"))
        patch.start()
        self.addCleanup(patch.stop)

    def test_every_change_is_described_and_undoable(self):
        for c in sc.changes():
            self.assertTrue(c.title and c.why, c.key)
            self.assertTrue(c.can_undo or c.manual, f"{c.key}: neither Undo nor a manual way back")

    def test_journal(self):
        sc.record("deep_sleep")
        self.assertIn("deep_sleep", sc.journal())
        sc.forget("deep_sleep")
        self.assertNotIn("deep_sleep", sc.journal())

    def test_root_undo_is_one_prompt(self):
        calls = []
        with mock.patch.object(sc.hw, "run", side_effect=lambda *a, **k: calls.append(a) or (True, "")):
            sc.undo(["keys", "boost", "deep_sleep"])
        prompts = [c for c in calls if c[0] == "pkexec"]
        self.assertEqual(len(prompts), 1)
        script = prompts[0][-1]
        self.assertIn("rm -f /etc/udev/rules.d/", script)
        self.assertIn("mem_sleep", script)


class Conflicts(unittest.TestCase):
    def test_found_conflict_becomes_a_setup_row_and_a_stop_step(self):
        from asus_tso_helper import conflicts
        tlp = next(c for c in conflicts.CONFLICTS if c.key == "tlp")
        with mock.patch.object(conflicts, "found", return_value=[tlp]), \
                mock.patch.object(setup, "is_asus", return_value=True), \
                mock.patch.object(setup, "distro", return_value="arch"):
            rows = setup.checks()
            row = next(r for r in rows if r["key"] == "conflict:tlp")
            text = setup.script([row])
        self.assertIn("systemctl disable --now tlp", text)
        self.assertIn("stopped:tlp", setup.todo_changes({"conflict:tlp"}))

    def test_every_stopped_service_can_be_started_again(self):
        keys = {c.key: c for c in sc.changes()}
        from asus_tso_helper import conflicts
        for c in conflicts.CONFLICTS:
            if c.service:
                self.assertIn(f"enable --now {c.service}", keys["stopped:" + c.key].undo_root)
            else:
                self.assertTrue(c.manual, c.key)


class Updates(unittest.TestCase):
    def test_exact_ids_for_both_architectures(self):
        out = ("Available xorg-x11-drv-nvidia-cuda-libs-3:615.78.08-1.fc44.x86_64 (rpmfusion-nonfree-updates)\n"
               "Available xorg-x11-drv-nvidia-cuda-libs-3:615.78.08-1.fc44.i686 (rpmfusion-nonfree-updates)\n"
               "Available kernel-7.2.11-200.fc44.x86_64 (updates)\n")
        fake = mock.Mock(stdout=out)
        with mock.patch.object(updates.shutil, "which", return_value="/usr/bin/pkcon"), \
                mock.patch.object(updates.subprocess, "run", return_value=fake):
            found = updates.repo_updates()
        self.assertEqual(found["kernel"], "7.2.11")
        self.assertEqual(updates.UPDATE_IDS["xorg-x11-drv-nvidia-cuda-libs"], [
            "xorg-x11-drv-nvidia-cuda-libs;3:615.78.08-1.fc44;x86_64;rpmfusion-nonfree-updates",
            "xorg-x11-drv-nvidia-cuda-libs;3:615.78.08-1.fc44;i686;rpmfusion-nonfree-updates"])


class Translations(unittest.TestCase):
    def strings(self):
        found = set()
        for path in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
            with open(path) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr" and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    found.add(node.args[0].value)
        return found

    def test_russian_is_complete_and_placeholders_match(self):
        with open(os.path.join(ROOT, "translations", "ru.json")) as f:
            ru = json.load(f)
        missing = sorted(s for s in self.strings() if s not in ru)
        self.assertEqual(missing, [], "add these to translations/ru.json")
        for en, text in ru.items():
            if text:
                self.assertEqual(set(re.findall(r"{(\w+)}", en)), set(re.findall(r"{(\w+)}", text)), en)


if __name__ == "__main__":
    unittest.main()
