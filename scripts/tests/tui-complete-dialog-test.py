#!/usr/bin/env python3
"""Back navigation from a completed build shows a modal; Enter goes home."""
import os
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from uncle_tui import UncleTUI

ESC, ENTER, CR, TAB, CTRL_C = 27, 10, 13, 9, 3
TITLE, FOOTER = " build complete ", "[Enter] return home"
BODY = "The build is complete. Press Enter to return to the home page."


def make_ui(code=0, banner=True, reported=True, chat_open=True, focus="chat"):
    ui = UncleTUI.__new__(UncleTUI)
    ui.state = "running"
    ui.prompt_kind = ""
    ui.prompt_text = ""
    ui.prompt_buf = ""
    ui.prompt_seen = 0
    ui.prompt_scroll = 0
    ui.gate_file = ""
    ui.sel = 3
    ui.partial = ""
    ui.output = []
    ui.proc_done = False
    ui.support_checked = False
    ui.panel_scroll = None
    ui.out_q = queue.Queue()
    ui.proc = Mock()
    ui.proc.poll.return_value = code
    ui.proc.returncode = code
    ui.workflow_exit_reported = reported
    if code is not None and reported:
        ui.workflow_exit_code = code
    ui.workflow_completed = banner
    ui.chat_open = chat_open
    ui.chat_focus = focus
    ui.chat_picker = False
    ui.chat_choices = []
    ui.chat_edit = False
    ui.chat_composer = ""
    ui.chat_error = "old error"
    ui.home_history = []
    ui.chat = Mock(messages=[])
    ui.color = {k: 0 for k in ("title", "accent", "good", "sel", "cursor", "warning", "bad", "muted")}
    return ui


class Preservation(unittest.TestCase):
    """Behaviour the completion modal must leave alone (T-3, T-4, T-11, T-10 live)."""

    def test_live_esc_no_modal(self):  # T-3
        ui = make_ui(code=None, banner=False, reported=False)
        ui.handle_key(ESC)
        self.assertEqual((ui.state, ui.prompt_kind), ("running", ""))

    def test_failed_or_no_banner_esc_returns_menu(self):  # T-4
        for code, banner in [(1, True), (0, False)]:
            ui = make_ui(code=code, banner=banner)
            ui.handle_key(ESC)
            self.assertEqual((ui.state, ui.prompt_kind), ("menu", ""), (code, banner))

    def test_each_conjunct_rejected_independently(self):  # T-11
        cases = [dict(code=0, banner=False), dict(code=1, banner=True),
                 dict(code=None, banner=True, reported=False), dict(code=0, banner=True, reported=False)]
        for kw in cases:
            ui = make_ui(**kw)
            if not kw.get("reported", True):
                ui.workflow_exit_code = 0  # stale code from an earlier run
            self.assertFalse(ui._build_completed(), kw)
            ui.handle_key(ESC)
            self.assertNotEqual(ui.prompt_kind, "complete", kw)
        ui = make_ui(code=0, banner=True)
        del ui.workflow_exit_code  # missing code
        self.assertFalse(ui._build_completed())
        ui.handle_key(ESC)
        self.assertNotEqual(ui.prompt_kind, "complete")

    def test_live_gate_esc_and_answers_unchanged(self):  # T-11 gates
        for kind, key, written in [("confirm", ESC, b"n\n"), ("audit", ESC, b"n\n"),
                                   ("confirm", ord("y"), b"y\n"), ("enter", ENTER, b"\n")]:
            ui = make_ui(code=None, banner=False, reported=False, focus="gate")
            ui.prompt_kind, ui.prompt_text = kind, "Proceed? [Y/N]"
            ui.handle_key(key)
            ui.proc.stdin.write.assert_called_once_with(written)
            self.assertEqual((ui.state, ui.prompt_kind), ("running", ""), kind)
        ui = make_ui(code=None, banner=False, reported=False, focus="gate")
        ui.prompt_kind, ui.prompt_text = "input", "Name:"
        ui.handle_key(ESC)
        self.assertEqual((ui.state, ui.prompt_kind, ui.chat_focus), ("running", "", "chat"))
        ui = make_ui(code=None, banner=False, reported=False, focus="gate")
        ui.prompt_kind, ui.prompt_text = "enter", "Press ENTER"
        with patch.object(UncleTUI, "stop_workflow") as stop:
            ui.handle_key(ESC)  # uncle_tui.py:3301 swallows Esc on a plain enter gate
            stop.assert_not_called()
        self.assertEqual((ui.state, ui.prompt_kind), ("running", "enter"))

    def test_live_tab_q_stops(self):  # T-10 live
        ui = make_ui(code=None, banner=False, reported=False)
        ui.handle_key(TAB)
        self.assertEqual(ui.chat_focus, "gate")
        with patch.object(UncleTUI, "stop_workflow") as stop:
            ui.handle_key(ord("q"))
            stop.assert_called_once()
        self.assertEqual((ui.state, ui.sel), ("menu", 0))

    def test_chat_q_stays_text(self):  # T-10 chat focus
        for kw in [dict(code=0, banner=True), dict(code=None, banner=False, reported=False)]:
            ui = make_ui(**kw)
            ui.handle_key(ord("q"))
            self.assertEqual((ui.chat_composer, ui.prompt_kind, ui.state), ("q", "", "running"), kw)


class CompleteDialog(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, XDG_STATE_HOME=self.temp.name)
        env.start()
        self.addCleanup(env.stop)

    def marker(self):
        return os.path.join(self.temp.name, "uncle", "star-prompt-shown")

    def test_completed_esc_opens_modal(self):  # T-1
        for focus in ("chat", "gate"):
            ui = make_ui(focus=focus)
            ui.handle_key(ESC)
            self.assertEqual((ui.state, ui.prompt_kind), ("running", "complete"), focus)
            self.assertEqual(ui.prompt_text, BODY)
        ui = make_ui(chat_open=False)
        ui.handle_key(ESC)
        self.assertEqual((ui.state, ui.prompt_kind), ("running", "complete"))

    def test_enter_returns_home(self):  # T-2
        for key in (ENTER, CR):
            ui = make_ui()
            ui.handle_key(ESC)
            ui.handle_key(key)
            self.assertEqual((ui.state, ui.prompt_kind, ui.chat_error, ui.chat_focus, ui.sel),
                             ("menu", "", "", "chat", 0), key)

    def test_modal_survives_esc_and_other_keys(self):  # T-5
        ui = make_ui()
        for k in (ESC, ESC, ESC, ord("q"), ord("s"), ord("y"), ord("n"), TAB, ord(" "), 127):
            ui.handle_key(k)
            self.assertEqual((ui.state, ui.prompt_kind, ui.prompt_text), ("running", "complete", BODY), k)
        self.assertEqual(ui.chat_composer, "")

    def test_esc_replaces_support_popup(self):  # T-6
        ui = make_ui()
        ui.support_checked = False
        # The offer now arrives through the completion preview's event queue.
        preview = Mock()
        preview.events = queue.Queue()
        preview.events.put(("done", False))
        with patch("uncle_tui.CompletionPreview", return_value=preview):
            ui._offer_support()
        ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, "support")
        with patch("uncle_tui.webbrowser.open") as browser:
            ui.handle_key(ESC)
            browser.assert_not_called()
        self.assertEqual((ui.state, ui.prompt_kind, ui.prompt_text), ("running", "complete", BODY))

    def test_draw_modal_text_and_geometry(self):  # T-7
        ui = make_ui()
        ui.handle_key(ESC)
        ui.stdscr = Mock()
        ui._draw_modal(24, 80)
        calls = [c.args for c in ui.stdscr.addnstr.call_args_list]
        texts = [a[2] for a in calls]
        self.assertTrue(any(TITLE in t for t in texts), texts)
        self.assertIn(BODY, texts)
        # Every modal footer carries the chat-focus hint after its own keys.
        self.assertTrue(any(t.startswith(FOOTER) for t in texts), texts)
        body_len = len(BODY) + 6
        box_w = max(min(80 - 4, body_len), 30)
        box_h = 3 + 4  # body, blank, footer + 4
        top_row, left_col = (24 - box_h) // 2, (80 - box_w) // 2
        self.assertEqual(calls[0][:2], (top_row, left_col))
        self.assertEqual(calls[-1][:2], (top_row + 2 + 2, left_col + 3))  # footer row
        self.assertEqual(ui.state, "running")
        ui.stdscr = Mock()
        ui._draw_modal(5, 20)  # narrow: must not raise
        ui.handle_key(ESC)
        self.assertEqual(ui.prompt_kind, "complete")
        ui.handle_key(ENTER)
        self.assertEqual(ui.state, "menu")

    def test_ctrl_c_quits(self):  # T-8
        ui = make_ui()
        ui.handle_key(ESC)
        ui.handle_key(CTRL_C)
        self.assertEqual(ui.state, "quit")

    def test_eof_drains_preserve_modal(self):  # T-9
        for marker in ("absent", "existing", "denied"):
            ui = make_ui()
            if marker == "existing":
                os.makedirs(os.path.dirname(self.marker()), exist_ok=True)
                with open(self.marker(), "w") as fh:
                    fh.write("shown\n")
            if marker == "denied":
                os.environ["XDG_STATE_HOME"] = os.path.join(self.temp.name, "nope")
                open(os.environ["XDG_STATE_HOME"], "w").close()  # file, not dir
            ui.handle_key(ESC)
            ui.out_q.put("Workflow complete.\n")
            ui.out_q.put(None)
            before = os.path.exists(self.marker())
            for _ in range(3):
                ui.drain_output()
                self.assertEqual((ui.state, ui.prompt_kind, ui.prompt_text, ui.chat_focus),
                                 ("running", "complete", BODY, "gate"), marker)
            self.assertEqual(os.path.exists(self.marker()), before, marker)
            ui.handle_key(ESC)
            self.assertEqual(ui.prompt_kind, "complete")
            ui.handle_key(ENTER)
            self.assertEqual(ui.state, "menu")
            os.environ["XDG_STATE_HOME"] = self.temp.name
            if os.path.exists(self.marker()):
                os.remove(self.marker())

    def test_completed_tab_q_opens_modal(self):  # T-10 completed
        for key in (ord("q"), ord("Q")):
            ui = make_ui()
            ui.handle_key(TAB)
            self.assertEqual(ui.chat_focus, "gate")
            with patch.object(UncleTUI, "stop_workflow") as stop:
                ui.handle_key(key)
                stop.assert_not_called()
            self.assertEqual((ui.state, ui.prompt_kind), ("running", "complete"), key)
        ui = make_ui(chat_open=False)
        with patch.object(UncleTUI, "stop_workflow") as stop:
            ui.handle_key(ord("q"))
            stop.assert_not_called()
        self.assertEqual((ui.state, ui.prompt_kind), ("running", "complete"))


if __name__ == "__main__":
    unittest.main()
