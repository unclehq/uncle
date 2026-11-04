#!/usr/bin/env python3
"""TUI desktop-launch prompt behavior (cases g-j of the change plan's test strategy).

Observable behavior only: prompt_kind/prompt_text, .uncle/workflow/desktop-* files,
home_history, and whether the child process ran. No real GUI: the launch command
is a python3 -c stub that writes a marker file.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui
from uncle_tui import UncleTUI

STUB_MARKER = "stub-ran"


def make_project(root, scripts=None, launch_json=None, config_cmd=None):
    root = Path(root)
    (root / ".uncle" / "workflow").mkdir(parents=True)
    pkg = {"name": "x", "main": "main.js", "devDependencies": {"electron": "^30"},
           "scripts": scripts if scripts is not None else {
               "start": "python3 -c \"open('%s','w').write('x'); import time; time.sleep(30)\"" % (root / STUB_MARKER)}}
    (root / "package.json").write_text(json.dumps(pkg))
    if launch_json is not None:
        (root / ".uncle" / "launch.json").write_text(launch_json)
    if config_cmd is not None:
        (root / ".uncle" / "config").write_text("desktop.launch_command = %s\n" % config_cmd)
    return root


def finished_ui(unattended=False):
    ui = UncleTUI.__new__(UncleTUI)
    ui.state = "running"
    ui.prompt_kind = ""
    ui.prompt_text = ""
    ui.gate_file = ""
    ui.proc = Mock()
    ui.proc.poll.return_value = 0
    ui.proc.returncode = 0
    ui.chat_open = True
    ui.chat_focus = "chat"
    ui.chat_picker = False
    ui.chat_choices = []
    ui.chat_edit = False
    ui.chat_composer = ""
    ui.chat_error = ""
    ui.chat = Mock()
    ui.recovery_active = False
    ui.workflow_exit_reported = True
    ui.workflow_exit_code = 0
    ui.workflow_completed = True
    ui.workflow_unattended = unattended
    ui.support_checked = False
    ui.home_history = []
    ui.sel = 0
    return ui


class Base(unittest.TestCase):
    env = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        pid = self.root / ".uncle" / "workflow" / "desktop-app.pid"
        if pid.exists():
            try:
                os.kill(json.loads(pid.read_text())["pid"], 15)
            except Exception:
                pass

    tty = True

    def run_offer(self, ui, env=None):
        patches = [patch("sys.stdin.isatty", return_value=self.tty, create=True),
                   patch.dict(os.environ, {"CI": "", "SSH_CONNECTION": "", "SSH_TTY": ""}, clear=False),
                   patch.object(uncle_tui, "_project_root", return_value=str(self.root)),
                   patch.object(uncle_tui, "_workflow_family", return_value="app"),
                   patch.dict(os.environ, env or {}, clear=False)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        ui._offer_support()
        return ui

    def wf(self, name):
        return self.root / ".uncle" / "workflow" / name

    def record(self):
        p = self.wf("desktop-launch.json")
        return json.loads(p.read_text()) if p.exists() else None

    def history_text(self, ui):
        return "\n".join(str(h) for h in ui.home_history)


class DesktopPromptTests(Base):
    def test_prompt_shows_argv_and_warning_and_enter_declines(self):  # (g)
        make_project(self.root)
        ui = self.run_offer(finished_ui())
        self.assertEqual(ui.prompt_kind, "desktop")
        self.assertIn("npm", ui.prompt_text + "python3")
        self.assertRegex(ui.prompt_text.lower(), "privilege")
        ui.handle_key(10)
        self.assertNotEqual(ui.prompt_kind, "desktop")
        self.assertEqual(self.record()["status"], "declined")
        self.assertFalse((self.root / STUB_MARKER).exists())

    def test_decline_keys_record_declined_without_spawn(self):  # (g)
        for key in (ord("n"), ord("N"), 27, 10, 13):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as d:
                    self.root = make_project(d)
                    ui = self.run_offer(finished_ui())
                    self.assertEqual(ui.prompt_kind, "desktop")
                    ui.handle_key(key)
                    self.assertEqual(self.record()["status"], "declined")
                    self.assertFalse((self.root / STUB_MARKER).exists())
                    self.assertFalse(self.wf("desktop-app.pid").exists())

    def test_unrelated_keys_leave_prompt_open(self):  # (g)
        make_project(self.root)
        ui = self.run_offer(finished_ui())
        for key in (ord("x"), ord("q"), ord(" "), 9, ord("1")):
            ui.handle_key(key)
            self.assertEqual(ui.prompt_kind, "desktop", key)
        self.assertIsNone(self.record())
        self.assertFalse((self.root / STUB_MARKER).exists())

    def test_y_launches_and_records(self):  # (g)
        make_project(self.root)
        ui = self.run_offer(finished_ui())
        ui.handle_key(ord("y"))
        import time
        for _ in range(50):
            if (self.root / STUB_MARKER).exists():
                break
            time.sleep(0.1)
        self.assertTrue((self.root / STUB_MARKER).exists())
        self.assertTrue(self.wf("desktop-app.pid").exists())

    def test_config_command_shown_in_full_and_never_spawned_unconfirmed(self):  # (g)
        cmd = "python3 -c \"open('%s','w').write('x')\" --flag-one --flag-two" % (self.root / "cfg-ran")
        make_project(self.root, config_cmd=cmd)
        ui = self.run_offer(finished_ui())
        self.assertEqual(ui.prompt_kind, "desktop")
        self.assertIn("--flag-two", ui.prompt_text)
        self.assertFalse((self.root / "cfg-ran").exists())
        # unattended run: still never launched without y
        with tempfile.TemporaryDirectory() as d:
            root2 = make_project(d, config_cmd=cmd.replace(str(self.root), d))
            self.root = root2
            ui2 = finished_ui(unattended=True)
            ui2._quit = Mock()
            self.run_offer(ui2)
            self.assertFalse((root2 / "cfg-ran").exists())
            self.assertFalse((root2 / ".uncle" / "workflow" / "desktop-app.pid").exists())


class PreviewInteractionTests(Base):
    LAUNCH_JSON = json.dumps({"kind": "webpage", "url": "http://localhost:5173"})

    def test_launch_json_unchanged_across_outcomes(self):  # (h)
        for label, setup in (("declined", ord("n")), ("ambiguous", None), ("unattended", None)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as d:
                scripts = {"start": "a", "dev": "b"} if label == "ambiguous" else None
                self.root = make_project(d, scripts=scripts, launch_json=self.LAUNCH_JSON)
                before = (self.root / ".uncle" / "launch.json").read_bytes()
                ui = finished_ui(unattended=(label == "unattended"))
                ui._quit = Mock()
                with patch.object(uncle_tui, "CompletionPreview", create=True) as cp:
                    self.run_offer(ui)
                    if setup:
                        ui.handle_key(setup)
                self.assertEqual((self.root / ".uncle" / "launch.json").read_bytes(), before)
                if label == "ambiguous":
                    self.assertNotEqual(ui.prompt_kind, "desktop")
                    self.assertEqual(self.record()["status"], "skipped")
                if label == "declined":
                    self.assertEqual(self.record()["status"], "declined")

    def test_unattended_skips_desktop_with_reason(self):  # (h)
        make_project(self.root)
        ui = finished_ui(unattended=True)
        ui._quit = Mock()
        self.run_offer(ui)
        self.assertNotEqual(ui.prompt_kind, "desktop")
        rec = self.record()
        self.assertEqual(rec["status"], "skipped")
        self.assertIn("unattended", json.dumps(rec))

    def test_disabled_values_do_nothing_and_web_preview_runs(self):  # (i)
        for val in ("0", "false", "no", "off", "OFF", " False "):
            with self.subTest(val=val), tempfile.TemporaryDirectory() as d:
                self.root = make_project(d, launch_json=self.LAUNCH_JSON)
                ui = finished_ui()
                with patch.object(uncle_tui, "CompletionPreview", create=True) as cp:
                    self.run_offer(ui, {"WORKFLOW_PREVIEW_DESKTOP": val})
                    cp.assert_called_once()
                self.assertNotEqual(ui.prompt_kind, "desktop")
                self.assertEqual(list((self.root / ".uncle" / "workflow").glob("desktop-*")), [])
                self.assertNotIn("desktop", self.history_text(ui).lower())


class AttendedAndNonDesktopTests(Base):
    def test_no_stdin_tty_is_unattended_even_if_tui_attended(self):  # (j) DEC-5
        make_project(self.root)
        ui = finished_ui(unattended=False)
        self.tty = False
        self.run_offer(ui)
        self.assertNotEqual(ui.prompt_kind, "desktop")
        self.assertEqual(self.record()["reason"], "unattended")

    def test_non_desktop_project_never_reaches_desktop_path(self):  # (j)
        (self.root / ".uncle" / "workflow").mkdir(parents=True)
        (self.root / "package.json").write_text(json.dumps({"name": "web", "scripts": {"start": "vite"}}))
        ui = finished_ui()
        self.run_offer(ui)
        self.assertNotEqual(ui.prompt_kind, "desktop")
        self.assertEqual(list((self.root / ".uncle" / "workflow").glob("desktop-*")), [])


if __name__ == "__main__":
    unittest.main()
