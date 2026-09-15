#!/usr/bin/env python3
"""Issue 51: the gate document opens in a configurable viewer.

T-1..T-7 of CHANGE_PLAN.md. No curses, no real viewer, no Git fixture.
"""
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui as tui
from uncle_tui import UncleTUI

PROGRAMS = ("cursor", "code", "glow", "bat", "less", "more", "cat")
KEY = "markdown_viewer"
FILE = "/tmp/a b.md"
Q = shlex.quote(FILE)
CUSTOM_ROW = ("custom", "Custom… (type a command)")


def which_for(*installed):
    return lambda name: "/usr/bin/%s" % name if name in installed else None


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = os.path.join(self.temp.name, "config")
        for p in (patch.object(tui, "CONFIG_PATH", self.config),
                  patch.object(tui, "_project_root", return_value=self.temp.name),
                  patch.object(tui, "read_keys", return_value={}),
                  patch.object(tui, "save_keys")):
            p.start()
            self.addCleanup(p.stop)

    def ui(self, config_text="", **attrs):
        with open(self.config, "w") as fh:
            fh.write(config_text)
        ui = UncleTUI.__new__(UncleTUI)
        ui.load_config()
        ui.state = "config"
        ui.config_section = "misc"
        ui.config_sel = ui.config_scroll = 0
        ui.notice = ""
        ui.input_buf = ""
        ui.pick_filter = ""
        ui.stage_sel = 0
        ui.proc = None
        for k, v in attrs.items():
            setattr(ui, k, v)
        return ui

    def config_lines(self):
        with open(self.config) as fh:
            return [l.rstrip("\n") for l in fh if l.startswith("misc.")]

    def source(self, text="# gate\nbody\n"):
        path = os.path.join(self.temp.name, "AUDIT.md")
        with open(path, "w") as fh:
            fh.write(text)
        return path

    # T-1: each candidate alone, glow with and without less, none.
    def test_t1_each_candidate_alone(self):
        expected = {"cursor": "cursor %s", "code": "code %s", "glow": "glow -p %s",
                    "bat": "bat %s", "less": "less %s", "more": "more %s", "cat": "cat %s"}
        ui = self.ui()
        for name in PROGRAMS:
            with patch("uncle_tui.shutil.which", side_effect=which_for(name)):
                self.assertEqual(ui._viewer_command(FILE), expected[name] % Q, name)
        with patch("uncle_tui.shutil.which", side_effect=which_for("glow", "less")):
            self.assertEqual(ui._viewer_command(FILE), "glow %s | less" % Q)
        with patch("uncle_tui.shutil.which", side_effect=which_for()):
            self.assertEqual(ui._viewer_command(FILE), "")
        self.assertEqual(UncleTUI.VIEWER_PROGRAMS, PROGRAMS)

    # T-2: every adjacent pair, so a dropped or swapped entry fails.
    def test_t2_adjacent_precedence(self):
        ui = self.ui()
        for first, second in zip(PROGRAMS, PROGRAMS[1:]):
            with patch("uncle_tui.shutil.which", side_effect=which_for(first, second)):
                cmd = ui._viewer_command(FILE)
            self.assertTrue(cmd.startswith(first + " "), (first, second, cmd))
        with patch("uncle_tui.shutil.which", side_effect=which_for(*PROGRAMS)):
            self.assertEqual(ui._viewer_command(FILE), "cursor %s" % Q)
        # A configured listed name goes first; one that is missing falls through.
        ui.misc[KEY] = "cat"
        with patch("uncle_tui.shutil.which", side_effect=which_for(*PROGRAMS)):
            self.assertEqual(ui._viewer_command(FILE), "cat %s" % Q)
        with patch("uncle_tui.shutil.which", side_effect=which_for("bat", "less")):
            self.assertEqual(ui._viewer_command(FILE), "bat %s" % Q)

    # T-3: raw custom text survives memory, config and command; blank falls back.
    def test_t3_custom_text_verbatim(self):
        ui = self.ui()
        ui._set_field("!misc", KEY, "  nvim -R  ")
        self.assertEqual(ui.misc[KEY], "  nvim -R  ")
        self.assertIn("misc.markdown_viewer   nvim -R  ", self.config_lines())
        again = UncleTUI.__new__(UncleTUI)
        again.load_config()
        self.assertEqual(again.misc[KEY], "  nvim -R  ")
        with patch("uncle_tui.shutil.which", side_effect=which_for(*PROGRAMS)):
            self.assertEqual(again._viewer_command(FILE), "  nvim -R   " + Q)
        ui._set_field("!misc", KEY, "sh -c 'cat \"$1\" # ro' -")
        again.load_config()
        self.assertEqual(again.misc[KEY], "sh -c 'cat \"$1\" # ro' -")
        ui._set_field("!misc", KEY, "   ")
        self.assertEqual(ui.misc[KEY], "")
        with patch("uncle_tui.shutil.which", side_effect=which_for(*PROGRAMS)):
            self.assertEqual(ui._viewer_command(FILE), "cursor %s" % Q)
        ui._set_field("!misc", "approval_name", "  Brian  ")
        self.assertEqual(ui.misc["approval_name"], "Brian")

    # T-4: the viewer gets a read-only disposable copy; the source survives.
    def test_t4_snapshot_protects_source(self):
        src = self.source()
        seen = {}

        def viewer(cmd, cwd=None):
            path = shlex.split(cmd)[-1]
            seen["cmd"] = cmd
            seen["path"] = path
            seen["mode"] = os.stat(path).st_mode & 0o777
            os.chmod(path, 0o644)
            with open(path, "w") as fh:
                fh.write("EDITED\n")

        ui = self.ui(state="running")
        with patch("uncle_tui.shutil.which", side_effect=which_for("less")), \
             patch.object(ui, "_run_in_terminal", side_effect=viewer) as run:
            ui._open_viewer(src)
        run.assert_called_once()
        self.assertTrue(seen["cmd"].startswith("less "))
        self.assertNotEqual(seen["path"], src)
        self.assertEqual(os.path.basename(seen["path"]), "AUDIT.md")
        self.assertEqual(seen["mode"], 0o444)
        self.assertFalse(os.path.exists(os.path.dirname(seen["path"])))
        with open(src) as fh:
            self.assertEqual(fh.read(), "# gate\nbody\n")
        self.assertEqual(ui.state, "running")

    # DV-1: an editor that returns at once keeps its snapshot.
    def test_t4b_detached_editor_keeps_snapshot(self):
        src = self.source()
        seen = {}
        ui = self.ui(state="running")
        with patch("uncle_tui.shutil.which", side_effect=which_for("code")), \
             patch.object(ui, "_run_in_terminal",
                          side_effect=lambda cmd, cwd=None: seen.setdefault("path", shlex.split(cmd)[-1])):
            ui._open_viewer(src)
        self.addCleanup(shutil.rmtree, os.path.dirname(seen["path"]), True)
        self.assertTrue(os.path.exists(seen["path"]))
        self.assertEqual(os.stat(seen["path"]).st_mode & 0o777, 0o444)

    # T-5: nothing installed explains itself in the built-in pager.
    def test_t5_no_candidate_explains_in_pager(self):
        src = self.source()
        ui = self.ui(state="running")
        made = []
        real_mkdtemp = tempfile.mkdtemp
        with patch("uncle_tui.shutil.which", side_effect=which_for()), \
             patch("uncle_tui.tempfile.mkdtemp",
                   side_effect=lambda **kw: made.append(real_mkdtemp(**kw)) or made[-1]), \
             patch.object(ui, "_run_in_terminal") as run:
            ui._open_viewer(src)
        run.assert_not_called()
        self.assertEqual(len(made), 1)
        self.assertFalse(os.path.exists(made[0]))
        self.assertEqual(ui.state, "viewer")
        for name in PROGRAMS:
            self.assertIn(name, ui.view_lines[0])
        self.assertIn("Miscellaneous", ui.view_lines[1])
        self.assertIn("Markdown viewer", ui.view_lines[1])
        self.assertEqual(ui.view_lines[2:], ["# gate", "body"])
        ui.stdscr = Mock()
        ui.color = {"sel": 0}
        ui._draw_viewer(24, 80)
        drawn = [c.args[2] for c in ui.stdscr.addnstr.call_args_list]
        self.assertIn(ui.view_lines[0], drawn)
        with patch("uncle_tui.shutil.which", side_effect=which_for()):
            ui._open_viewer(os.path.join(self.temp.name, "missing.md"))
        self.assertEqual(len(ui.view_lines), 1)
        self.assertTrue(ui.view_lines[0].startswith("not found: "))

    # T-6: three Misc rows; rows 0/1 unchanged; row 2 is the viewer picker.
    def test_t6_misc_rows_and_picker(self):
        ui = self.ui()
        rows = ui._config_items()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("Auto mode: off"))
        self.assertTrue(rows[1].startswith("Name for approvals: "))
        self.assertEqual(rows[2], "Markdown viewer: auto (first installed)")
        ui.handle_key(10)
        self.assertEqual(ui.misc["auto_mode"], "true")
        self.assertEqual(ui.state, "config")
        ui.config_sel = 1
        ui.handle_key(10)
        self.assertEqual((ui.state, ui.picker_kind, ui.picker_target), ("config_edit", "approval_name", "!misc"))
        ui.state = "config"
        ui.config_sel = 2
        with patch("uncle_tui.shutil.which", side_effect=which_for("glow", "cat", "less")):
            ui.handle_key(10)
            self.assertEqual((ui.state, ui.picker_kind, ui.picker_target), ("picker", KEY, "!misc"))
            self.assertEqual(ui._picker_rows(), [("option", "glow"), ("option", "less"), ("option", "cat"), CUSTOM_ROW])
            ui.handle_key(27)
            self.assertEqual(ui.state, "config")
            self.assertEqual(ui.config_section, "misc")
            ui.handle_key(10)
            ui._picker_move(1)
            ui.handle_key(10)
        self.assertEqual(ui.state, "config")
        self.assertEqual(ui.misc[KEY], "less")
        self.assertIn("misc.markdown_viewer less", self.config_lines())
        self.assertEqual(ui._config_items()[2], "Markdown viewer: less")
        with patch("uncle_tui.shutil.which", side_effect=which_for("glow", "cat", "less")):
            ui.handle_key(10)
            self.assertEqual(ui.pick_sel, 1)
            for ch in "  nvim -R  ":
                ui.handle_key(ord(ch))
            self.assertEqual(ui._picker_filtered(), [CUSTOM_ROW])
            ui.handle_key(10)
        self.assertEqual((ui.state, ui.input_buf), ("config_edit", "  nvim -R  "))
        ui.handle_key(10)
        self.assertEqual((ui.state, ui.misc[KEY]), ("config", "  nvim -R  "))
        self.assertIn("misc.markdown_viewer   nvim -R  ", self.config_lines())
        ui.handle_key(27)
        self.assertEqual((ui.state, ui.config_section), ("config", ""))

    # T-7: the real terminal handoff leaves the pending gate untouched.
    def test_t7_handoff_preserves_pending_ui_and_config(self):
        src = self.source()
        ui = self.ui(state="running", prompt_kind="audit", prompt_text="Approve the audit?",
                     gate_file=src, chat_focus="gate", stdscr=Mock(),
                     poll_home_chat=Mock(), _poll_workflow=Mock())
        proc = Mock()
        proc.poll.side_effect = [None, None, 0]
        with patch("uncle_tui.shutil.which", side_effect=which_for("less")), \
             patch("uncle_tui.curses.def_prog_mode") as save, patch("uncle_tui.curses.endwin"), \
             patch("uncle_tui.curses.reset_prog_mode") as restore, \
             patch("uncle_tui.subprocess.Popen", return_value=proc) as popen, \
             patch("uncle_tui.time.sleep"):
            ui._open_viewer(src)
        popen.assert_called_once()
        self.assertTrue(popen.call_args.args[0].startswith("less "))
        self.assertTrue(popen.call_args.kwargs["shell"])
        save.assert_called_once()
        restore.assert_called_once()
        self.assertGreaterEqual(ui._poll_workflow.call_count, 3)
        self.assertGreaterEqual(ui.poll_home_chat.call_count, 3)
        ui.stdscr.clearok.assert_called_with(True)
        self.assertEqual((ui.state, ui.prompt_kind, ui.prompt_text, ui.gate_file, ui.chat_focus),
                         ("running", "audit", "Approve the audit?", src, "gate"))
        ui._set_field("!misc", KEY, "less")
        again = UncleTUI.__new__(UncleTUI)
        again.load_config()
        self.assertEqual(again.misc[KEY], "less")
        self.assertEqual(self.ui("misc.other x\nmisc.auto_mode true\n").misc, {"auto_mode": "true"})


if __name__ == "__main__":
    unittest.main()
