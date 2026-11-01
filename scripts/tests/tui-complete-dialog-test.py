#!/usr/bin/env python3
"""Back navigation from a finished build opens a 'build is complete' dialog (Issue 49).

Leaving for the home page is no longer part of it. Finishing a build used to
discard the screen that build had just produced -- its output, stage history
and the chat about it -- on an Enter or a stray Esc. The dialog still opens
and still stops the workflow; the page stays put, and /homepage leaves.
"""
import curses
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from uncle_tui import UncleTUI


def setUpModule():
    # A run's family is read from <project root>/.uncle/workflow/family. These tests are about the dialog, not about which
    # directory they happen to run in, so they must not depend on whatever marker the checkout holds.
    import uncle_tui
    global _family_patch
    _family_patch = patch.object(uncle_tui, '_workflow_family', return_value='app')
    _family_patch.start()


def tearDownModule():
    _family_patch.stop()

BANNERS = ["Workflow complete.", "Change workflow complete.",
           "Workflow complete with waived acceptance.",
           "Change workflow complete with waived acceptance."]


def build(banner="Workflow complete.", code=0, exited=True, chat_open=True, focus='chat'):
    """A build page after the driver exited; no curses, no Git, no subprocess."""
    ui = UncleTUI.__new__(UncleTUI)
    ui.state = "running"
    ui.prompt_kind = ""
    ui.prompt_text = ""
    ui.gate_file = ""
    ui.proc = Mock()
    ui.proc.poll.return_value = code
    ui.proc.returncode = code
    ui.chat_open = chat_open
    ui.chat_focus = focus
    ui.chat_picker = False
    ui.chat_choices = []
    ui.chat_edit = False
    ui.chat_composer = ''
    ui.chat_error = ''
    ui.chat = Mock()
    ui.recovery_active = False
    ui.workflow_exit_reported = exited
    ui.workflow_exit_code = code
    ui.sel = 3
    if banner:
        ui._read_banner(banner)
    return ui


class CompleteDialogTests(unittest.TestCase):
    def assert_complete(self, ui):
        self.assertEqual(ui.state, "running")
        self.assertEqual(ui.prompt_kind, "complete")
        self.assertIn("complete", ui.prompt_text)
        self.assertIn("Enter", ui.prompt_text)

    def test_esc_opens_dialog_and_enter_stays_on_the_build_page(self):  # T-1 (AC-1, AC-2)
        for chat_open, focus, enter in [(True, 'chat', 10), (True, 'gate', 13), (False, 'chat', 10)]:
            ui = build(chat_open=chat_open, focus=focus)
            ui.handle_key(27)
            self.assert_complete(ui)
            with patch.object(UncleTUI, "stop_workflow", autospec=True) as stop:
                stop.side_effect = lambda self: setattr(self, "proc", None)
                ui.handle_key(enter)
                self.assertEqual(stop.call_count, 1)
            self.assertEqual(ui.state, "running")
            self.assertEqual(ui.prompt_kind, "")
            self.assertIsNone(ui.proc)

    def test_other_keys_keep_dialog_and_send_nothing(self):  # T-2 (AC-4)
        ui = build()
        ui.handle_key(27)
        with patch.object(UncleTUI, "send_home_chat", autospec=True) as home, \
                patch.object(UncleTUI, "_send_raw", autospec=True) as raw, \
                patch.object(UncleTUI, "stop_workflow", autospec=True) as stop:
            for k in (27, 27, curses.KEY_UP, curses.KEY_DOWN, ord("x"), ord("q"), ord(" "), 9):
                ui.handle_key(k)
                self.assert_complete(ui)
            home.assert_not_called()
            raw.assert_not_called()
            stop.assert_not_called()

    def test_every_successful_banner_with_exit_zero_only(self):  # T-3 (AC-1, AC-3, AC-4)
        for banner in BANNERS:
            ui = build(banner)
            ui.handle_key(27)
            self.assert_complete(ui)
            ui = build(banner, code=1)
            ui.handle_key(27)
            self.assertEqual(ui.state, "running")
            self.assertEqual(ui.prompt_kind, "")
        ui = build(banner="")
        ui.handle_key(27)
        self.assertEqual(ui.state, "running")
        self.assertEqual(ui.prompt_kind, "")
        ui = build(banner="Build verdict: PASS")
        ui.handle_key(27)
        self.assertEqual(ui.state, "running")

    def test_unfinished_builds_keep_existing_esc_behavior(self):  # T-4 (AC-3)
        ui = build(code=None, exited=False, chat_open=False)  # still running, no gate
        ui.handle_key(27)
        self.assertEqual((ui.state, ui.prompt_kind), ("running", ""))
        ui = build(code=None, exited=False, chat_open=False)  # live confirm gate
        ui.prompt_kind = "confirm"
        with patch.object(UncleTUI, "answer_prompt", autospec=True) as answer:
            ui.handle_key(27)
            answer.assert_called_once_with(ui, "n")
        self.assertEqual(ui.prompt_kind, "confirm")
        ui = build(code=None, exited=False)  # live preview closes first
        ui.completion_preview = Mock()
        ui.completion_preview.process.poll.return_value = None
        ui.handle_key(27)
        ui.completion_preview.close.assert_called_once()
        self.assertEqual(ui.prompt_kind, "")
        for kind in ("support", "finished"):
            ui = build(chat_open=False)  # chat closed: dismiss first, then complete
            ui.prompt_kind = kind
            ui.chat_focus = "gate"
            ui.handle_key(27)
            self.assertEqual((ui.state, ui.prompt_kind), ("running", ""))
            ui.handle_key(27)
            self.assert_complete(ui)
            ui = build(chat_open=True)  # chat open: _chat_key keeps the build page
            ui.prompt_kind = kind
            ui.chat_focus = "gate"
            ui.handle_key(27)
            self.assertEqual(ui.state, "running")

    def test_exit_poll_preserves_complete_dialog(self):  # D-6
        ui = build(exited=False)
        ui.workflow_completed = True
        ui.workflow_exit_reported = True
        ui.handle_key(27)
        ui.workflow_exit_reported = False
        ui.home_history = []
        ui.supervision_host = None
        ui._poll_workflow()
        self.assertEqual(ui.prompt_kind, "complete")
        self.assertEqual(ui.chat_focus, "gate")

    def test_modal_draws_title_and_enter_footer(self):  # T-5 (AC-5)
        ui = build()
        ui.handle_key(27)
        ui.color = {"title": 0, "accent": 0, "sel": 0, "cursor": 0}
        ui.stdscr = Mock()
        ui._draw_modal(24, 80)
        drawn = [c.args[2] for c in ui.stdscr.addnstr.call_args_list]
        self.assertTrue(any("build complete" in t for t in drawn), drawn)
        self.assertTrue(any("[Enter]" in t and "home" in t for t in drawn), drawn)
        self.assertTrue(any("Build is complete" in t for t in drawn), drawn)


class UnattendedFinishTests(unittest.TestCase):
    """Issue 107: an unattended finished build opens no dialog and exits 0."""

    def finish(self, unattended, banner="Change workflow complete.", code=0):
        ui = build(banner, code=code)
        ui.workflow_unattended = unattended
        ui.support_checked = False
        ui.proc.poll.return_value = code
        for line in ("Finished build: verdict=READY skipped=2 path=/tmp/p",
                     "READY - 2 blocking findings WAIVED WITHOUT HUMAN REVIEW (the auditor said NOT READY)"):
            ui._read_banner(line)
        return ui

    def test_decision_function(self):
        from uncle_tui import finish_decision
        self.assertEqual(finish_decision(True, True, 0), 'exit')
        self.assertEqual(finish_decision(True, False, 0), 'dialog')
        self.assertEqual(finish_decision(True, True, 1), 'dialog')
        self.assertEqual(finish_decision(True, True, 130), 'dialog')
        self.assertEqual(finish_decision(False, True, 0), 'dialog')  # toggled to attended

    def test_unattended_completed_quits_without_dialog_or_preview(self):
        ui = self.finish(True)
        with patch("uncle_tui.CompletionPreview") as preview:
            ui._offer_support()
            preview.assert_not_called()
        self.assertEqual(ui.state, "quit")
        self.assertNotIn(ui.prompt_kind, ("support", "finished", "complete"))
        self.assertEqual(ui.finished_build_lines(), [
            "Finished build: verdict=READY skipped=2 path=/tmp/p",
            "READY - 2 blocking findings WAIVED WITHOUT HUMAN REVIEW (the auditor said NOT READY)"])

    def test_attended_completed_still_offers_dialog_flow(self):
        ui = self.finish(False)
        with patch("uncle_tui.CompletionPreview") as preview:
            ui._offer_support()
            preview.assert_called_once()
        self.assertEqual(ui.state, "running")
        self.assertIsNone(ui.finished_build_lines())

    def test_unattended_failed_or_nonzero_keeps_todays_flow(self):
        for code in (1, 130):
            ui = self.finish(True, code=code)
            with patch("uncle_tui.CompletionPreview") as preview:
                ui._offer_support()
                preview.assert_not_called()
            self.assertEqual(ui.state, "running")
            self.assertIsNone(ui.finished_build_lines())
        ui = self.finish(True, banner="")
        ui._offer_support()
        self.assertEqual(ui.state, "running")

    def test_help_text_no_longer_claims_publication_stop(self):
        import uncle_tui
        source = Path(uncle_tui.__file__).read_text(encoding="utf-8")
        self.assertNotIn("It stops at the publication boundary", source)
        self.assertIn("accepted without human review", source)
        self.assertIn("nothing is committed, pushed or opened as a PR", source)

    def test_total_time_and_pr_captured_only_in_finished_block(self):
        ui = build(None)
        for line in ("Total time: 1s", "PR: stray"):
            ui._read_banner(line)
        self.assertEqual(getattr(ui, "finished_lines", []), [])
        for line in ("Finished build: verdict=READY skipped=0 path=/tmp/p",
                     "Total time: 1m 2s", "PR: none (not published)"):
            ui._read_banner(line)
        self.assertEqual(ui.finished_lines, [
            "Finished build: verdict=READY skipped=0 path=/tmp/p",
            "Total time: 1m 2s", "PR: none (not published)"])

    def test_auto_and_flag_commands_match(self):
        for auto_mode, expected in (("true", True), ("false", False)):
            ui = UncleTUI.__new__(UncleTUI)
            ui.misc = {"auto_mode": auto_mode}
            ui._startup_unattended = False
            ui.workflow_idx = 0
            self.assertEqual("--unattended" in ui.cmd_for(), expected)
        ui.session_auto_mode = False  # Shift-Tab to attended affects the next run only
        ui.misc = {"auto_mode": "true"}
        self.assertNotIn("--unattended", ui.cmd_for())


if __name__ == "__main__":
    unittest.main()
