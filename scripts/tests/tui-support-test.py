#!/usr/bin/env python3
"""The support popup is opt-in and remembered across workflows/projects."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from uncle_tui import UncleTUI


class SupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, XDG_STATE_HOME=self.temp.name)
        env.start()
        self.addCleanup(env.stop)

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
        self.assertEqual(ui.prompt_kind, "support")
        self.assertIn("won't bother you again", ui.prompt_text)
        with patch("uncle_tui.webbrowser.open") as browser:
            ui.handle_key(27)
            browser.assert_not_called()
        ui._offer_support()
        self.assertEqual(ui.prompt_kind, "")
        other = self.ui("Change workflow complete.")
        other._offer_support()
        self.assertEqual(other.prompt_kind, "")

    def test_pending_failed_and_still_running_do_not_consume_offer(self):
        for banner, code in [("Acceptance BLOCKED", 0), ("Workflow complete.", 1),
                             ("Workflow complete.", None)]:
            ui = self.ui(banner, code)
            ui._offer_support()
            self.assertEqual(ui.prompt_kind, "")
        ui = self.ui("Change workflow complete.")
        ui._offer_support()
        self.assertEqual(ui.prompt_kind, "support")

    def test_browser_requires_explicit_action(self):
        ui = self.ui()
        with patch("uncle_tui.threading.Thread") as thread:
            ui._offer_support()
            ui.handle_key(10)
            thread.assert_not_called()
            ui.prompt_kind = "support"
            ui.handle_key(ord("s"))
            self.assertEqual(thread.call_args.kwargs["args"],
                             ("https://github.com/unclehq/uncle",))
            thread.return_value.start.assert_called_once()
            self.assertEqual(ui.prompt_kind, "")

    def test_unwritable_state_does_not_break_completion(self):
        ui = self.ui()
        with patch("uncle_tui.os.makedirs", side_effect=PermissionError):
            ui._offer_support()
        self.assertEqual(ui.prompt_kind, "")


if __name__ == "__main__":
    unittest.main()
