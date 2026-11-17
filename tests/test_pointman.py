# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vince Bono
import asyncio
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from pointman.audit import AuditLog, verify
from pointman.cli import build_server, main
from pointman.core import Pointman
from pointman.policy import Denied, Policy

FIXTURE = Path(__file__).with_name("fixture_app.ps1")
TITLE = "Pointman Test Target"


class TempDir(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def policy(self, **overrides) -> Policy:
        settings = {"kill_switch": self.dir / "STOP", "audit_log": self.dir / "audit.jsonl", **overrides}
        return Policy(**settings)


class PolicyTest(TempDir):
    def test_default_policy_allows_nothing(self):
        with self.assertRaises(Denied):
            self.policy().check_read("notepad.exe")

    def test_reading_and_acting_are_separate_permissions(self):
        read_only = self.policy(allowed_apps=frozenset({"notepad.exe"}))
        read_only.check_read("NOTEPAD.EXE")
        with self.assertRaises(Denied):
            read_only.check_action("notepad.exe")
        self.policy(allowed_apps=frozenset({"notepad.exe"}), allow_actions=True).check_action("notepad.exe")

    def test_kill_switch_stops_even_allowed_apps(self):
        policy = self.policy(allowed_apps=frozenset({"notepad.exe"}), allow_actions=True)
        policy.kill_switch.write_text("")
        with self.assertRaises(Denied):
            policy.check_read("notepad.exe")

    def test_config_file_is_loaded_and_typos_are_errors(self):
        config = self.dir / "pointman.toml"
        config.write_text('allowed_apps = ["Notepad.exe"]\nallow_actions = true\n', encoding="utf-8")
        policy = Policy.load(config)
        self.assertTrue(policy.allows("notepad.exe") and policy.allow_actions)
        config.write_text("allow_action = true\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            Policy.load(config)
        self.assertEqual(main(["verify-audit", "--config", str(config)]), 2)


class AuditTest(TempDir):
    def test_chain_survives_reopening_and_detects_edits_and_deletions(self):
        path = self.dir / "audit.jsonl"
        AuditLog(path).record("read_window", "ok", app="notepad.exe")
        log = AuditLog(path)  # a new process continues the same chain
        log.record("click", "denied", reason="read-only")
        log.record("click", "ok")
        self.assertEqual(verify(path), (3, None))

        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join([lines[0], lines[1].replace("denied", "ok"), lines[2]]) + "\n", encoding="utf-8")
        self.assertIn("line 2", verify(path)[1])
        path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        self.assertIn("line 2", verify(path)[1])


class ServerTest(TempDir):
    def test_server_exposes_the_four_tools(self):
        policy = self.policy()
        server = build_server(Pointman(policy, AuditLog(policy.audit_log)))
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertEqual(names, {"list_windows", "read_window", "click", "set_text"})


@unittest.skipUnless(sys.platform == "win32", "drives a real window through Windows UI Automation")
class DesktopTest(TempDir):
    def setUp(self):
        super().setUp()
        self.app = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(FIXTURE)])
        self.addCleanup(self.app.wait)  # runs after kill; cleanups are last-in, first-out
        self.addCleanup(self.app.kill)

    def pointman(self, **overrides) -> Pointman:
        policy = self.policy(**overrides)
        return Pointman(policy, AuditLog(policy.audit_log))

    def handle(self, pointman: Pointman) -> int:
        for _ in range(60):  # the window takes a moment to appear
            for line in pointman.list_windows().splitlines():
                if TITLE in line:
                    return int(line.split()[0])
            time.sleep(0.5)
        self.fail("test window did not appear")

    def ref(self, tree: str, text: str) -> str:
        return next(line.split()[0] for line in tree.splitlines() if text in line)

    def test_unlisted_app_is_hidden_and_unreadable(self):
        allowed = self.pointman(allowed_apps=frozenset({"powershell.exe"}))
        handle = self.handle(allowed)
        stranger = self.pointman()
        self.assertNotIn(TITLE, stranger.list_windows())
        self.assertTrue(stranger.read_window(handle).startswith("DENIED"))

    def test_read_only_mode_reads_but_does_not_act_and_hides_the_password(self):
        pointman = self.pointman(allowed_apps=frozenset({"powershell.exe"}))
        handle = self.handle(pointman)
        tree = pointman.read_window(handle)
        self.assertIn("Button 'Greet'", tree)
        self.assertIn("(password, hidden)", tree)
        self.assertNotIn("hunter2", tree)
        self.assertTrue(pointman.click(handle, self.ref(tree, "'Greet'")).startswith("DENIED: read-only"))
        self.assertIn("'waiting'", pointman.read_window(handle))

    def test_actions_work_when_allowed_are_logged_and_refuse_password_boxes(self):
        pointman = self.pointman(allowed_apps=frozenset({"powershell.exe"}), allow_actions=True)
        handle = self.handle(pointman)
        tree = pointman.read_window(handle)
        self.assertTrue(pointman.set_text(handle, self.ref(tree, "'Secret'"), "x").startswith("DENIED"))
        self.assertTrue(pointman.set_text(handle, self.ref(tree, "'Name'"), "Vince").startswith("set"))
        self.assertTrue(pointman.click(handle, self.ref(tree, "'Greet'")).startswith("clicked"))
        self.assertIn("'hello Vince'", pointman.read_window(handle))

        log = pointman.policy.audit_log.read_text(encoding="utf-8")
        self.assertEqual(verify(pointman.policy.audit_log)[1], None)
        self.assertIn('"outcome": "denied"', log)
        self.assertNotIn("Vince", log)  # typed text is not written to the log


if __name__ == "__main__":
    unittest.main()
