#!/usr/bin/env python3
"""The support popup is opt-in and remembered across workflows/projects."""
import os
import queue
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from uncle_tui import UncleTUI

SUPPORT_URL = "https://github.com/unclehq/uncle"


class SupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, XDG_STATE_HOME=self.temp.name)
        env.start()
        self.addCleanup(env.stop)
        def preview(*args):
            obj = Mock()
            obj.events = queue.Queue()
            obj.events.put(('done', False))
            return obj
        launcher = patch('uncle_tui.CompletionPreview', side_effect=preview)
        launcher.start()
        self.addCleanup(launcher.stop)

    def ui(self, banner="Workflow complete.", code=0):
        ui = UncleTUI.__new__(UncleTUI)
        ui.state = "running"
        ui.prompt_kind = ""
        ui.proc = Mock()
        ui.proc.poll.return_value = code
        ui._read_banner(banner)
        return ui

    def test_once_across_instances_and_dismissals(self):
        ui = self.ui()
        ui._offer_support()
        ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, "support")
        self.assertIn("won't bother you again", ui.prompt_text)
        self.assertIn(SUPPORT_URL, ui.prompt_text)
        with patch("uncle_tui.webbrowser.open") as browser:
            ui.handle_key(27)
            browser.assert_not_called()
        ui._offer_support()
        ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, "")
        other = self.ui("Change workflow complete.")
        other._offer_support()
        other._poll_completion_preview()
        self.assertEqual(other.prompt_kind, "finished")

    def test_pending_failed_and_still_running_do_not_consume_offer(self):
        for banner, code in [("Acceptance BLOCKED", 0), ("Workflow complete.", 1),
                             ("Workflow complete.", None)]:
            ui = self.ui(banner, code)
            ui._offer_support()
            ui._poll_completion_preview()
            self.assertEqual(ui.prompt_kind, "")
        ui = self.ui("Change workflow complete.")
        ui._offer_support()
        ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, "support")

    def test_browser_requires_explicit_action(self):
        ui = self.ui()
        with patch("uncle_tui.threading.Thread") as thread:
            ui._offer_support()
            ui._poll_completion_preview()
            ui.handle_key(10)
            thread.assert_not_called()
            ui.prompt_kind = "support"
            ui.handle_key(ord("s"))
            self.assertEqual(thread.call_args.kwargs["args"], (SUPPORT_URL,))
            thread.return_value.start.assert_called_once()
            self.assertEqual(ui.prompt_kind, "")

    def test_url_fully_visible_at_50_columns_and_painted_as_hyperlink(self):
        ui = self.ui()
        ui._offer_support()
        ui._poll_completion_preview()
        ui.color = {"title": 0, "accent": 0, "sel": 0, "cursor": 0}
        ui.stdscr = Mock()
        ui._draw_modal(24, 50)
        drawn = [(c.args[0], c.args[1], c.args[2], c.args[3])
                 for c in ui.stdscr.addnstr.call_args_list if c.args[2] == SUPPORT_URL]
        self.assertEqual(len(drawn), 1)
        y, x, _, limit = drawn[0]
        self.assertGreaterEqual(limit, len(SUPPORT_URL))
        self.assertLessEqual(x + len(SUPPORT_URL), 50)
        with patch("uncle_tui.os.write") as write:
            ui._paint_support_link()
        payload = write.call_args.args[1]
        self.assertIn(b"\x1b[%d;%dH" % (y + 1, x + 1), payload)
        self.assertIn(b"\x1b]8;;" + SUPPORT_URL.encode() + b"\x1b\\" + SUPPORT_URL.encode()
                      + b"\x1b]8;;\x1b\\", payload)
        ui.prompt_kind = ""
        with patch("uncle_tui.os.write") as write:
            ui._paint_support_link()
            write.assert_not_called()

    def test_exit_poll_preserves_new_completion_dialog(self):
        ui = self.ui()
        ui.proc.returncode = 0
        ui._end_title = Mock()
        ui._ensure_chat = Mock()
        ui.home_history = []
        ui._offer_support()
        ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, 'support')
        ui._poll_workflow()
        self.assertEqual(ui.prompt_kind, 'support')
        self.assertEqual(ui.chat_focus, 'gate')
        self.assertTrue(ui.workflow_exit_reported)
        self.assertEqual(len(ui.home_history), 1)
        ui._poll_workflow()
        self.assertEqual(len(ui.home_history), 1)

    def test_starred_user_gets_finished_and_both_keys_dismiss(self):
        for key in (10, 27):
            ui = self.ui()
            ui._completion_dialog(True)
            self.assertEqual(ui.prompt_kind, 'finished')
            self.assertEqual(ui.prompt_text, 'Finished')
            ui.handle_key(key)
            self.assertEqual(ui.prompt_kind, '')

    def test_preview_precedes_dialog(self):
        ui = self.ui()
        ui._offer_support()
        self.assertEqual(ui.prompt_kind, '')
        ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, 'support')

    def test_unwritable_state_does_not_break_completion(self):
        ui = self.ui()
        with patch("uncle_tui.os.makedirs", side_effect=PermissionError):
            ui._offer_support()
            ui._poll_completion_preview()
        self.assertEqual(ui.prompt_kind, "finished")


if __name__ == "__main__":
    unittest.main()
