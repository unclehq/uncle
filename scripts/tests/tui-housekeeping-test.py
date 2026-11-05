#!/usr/bin/env python3
"""Behavioural tests for the TUI /housekeeping slash command, the startup
action and the Miscellaneous menu entry (AC-3, AC-12).  The UI object is built
without a terminal and its workflow launcher is observed, not grepped."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import uncle_tui as tui  # noqa: E402


class HousekeepingTui(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ctx = patch.object(tui, '_project_root', return_value=self.tmp.name)
        ctx.start()
        self.addCleanup(ctx.stop)
        self.ui = tui.UncleTUI.__new__(tui.UncleTUI)
        self.ui._ensure_chat()
        self.ui.state, self.ui.proc = 'menu', None
        self.cmds = []

        def fake_run():  # capture the command the real launcher would execute
            self.cmds.append(self.ui.cmd_for())
        self.ui._run = Mock(side_effect=fake_run)

    def test_slash_command_launches_driver_with_text(self):
        self.ui.chat_composer = '/housekeeping rename repo X to Y'
        self.assertTrue(self.ui._chat_command(10))
        self.assertEqual(len(self.cmds), 1)
        self.assertEqual(self.cmds[0][0], os.path.join(str(tui.ROOT), 'scripts', 'housekeeping-workflow.sh'))
        self.assertEqual(self.cmds[0][1], 'rename repo X to Y')
        self.assertEqual(self.ui.chat_composer, '')
        self.assertEqual(self.ui.chat_error, '')
        self.assertIsNone(self.ui._housekeeping_text)  # not sticky for later runs

    def test_empty_text_refused_without_launch(self):
        for text in ('/housekeeping', '/housekeeping    '):
            self.ui.chat_composer = text
            self.assertTrue(self.ui._chat_command(10))
            self.assertIn('Usage: /housekeeping TEXT', self.ui.chat_error)
        self.ui._run.assert_not_called()

    def test_refused_while_workflow_active(self):
        self.ui.state = 'running'
        self.ui.chat_composer = '/housekeeping do things'
        self.assertTrue(self.ui._chat_command(10))
        self.assertIn('already active', self.ui.chat_error)
        self.ui._run.assert_not_called()

    def test_startup_action_launches_driver(self):
        self.ui._startup_action = 'housekeeping'
        self.ui._startup_text = 'close stale issues'
        self.ui._startup_text_file = ''
        self.ui._handle_startup_action()
        self.assertEqual(len(self.cmds), 1)
        self.assertEqual(self.cmds[0][1], 'close stale issues')
        self.assertTrue(self.cmds[0][0].endswith('housekeeping-workflow.sh'))

    def test_exit_writes_title_once_not_every_poll(self):
        # Regression: a finished run with no completion banner stays on the
        # build page; re-writing the title each tick blocked the tty.
        proc = Mock()
        proc.poll.return_value = 0
        proc.returncode = 0
        self.ui.proc = proc
        self.ui.output = []
        self.ui.home_history = []
        self.ui._maybe_auto_triage = Mock()
        with patch.object(self.ui, '_end_title') as end_title:
            for _ in range(5):
                self.ui._poll_workflow()
        self.assertEqual(end_title.call_count, 1)

    def test_slash_listed(self):
        self.ui.chat_composer = '/house'
        self.assertIn('/housekeeping', self.ui._slash_choices())

    def test_misc_menu_entry_is_last_and_existing_kept(self):
        self.ui.config_section = 'misc'
        items = self.ui._config_items()
        self.assertEqual(len(items), 4)
        self.assertTrue(items[0].startswith('Auto mode: '))
        self.assertTrue(items[1].startswith('Name for approvals: '))
        self.assertTrue(items[2].startswith('Markdown viewer: '))
        self.assertIn('Housekeeping disallow', items[3])
        self.ui.config_section = ''
        self.assertEqual(self.ui._config_items()[:3], ["1. Configure stages", "2. Configure self hosting", "3. Miscellaneous"])

    def test_disallow_list_editable_from_tui(self):
        cfg = os.path.join(self.tmp.name, 'config')
        with patch.object(tui, 'CONFIG_PATH', cfg):
            ui = self.ui
            ui.config_section, ui.config_sel, ui.state = 'misc', 3, 'config'
            ui.picker_kind = ui.picker_target = ''
            ui.state = 'config'
            ui.misc = {}
            ui.config_section = 'housekeeping'
            n = len(tui.hk_config.load(cfg))
            ui.config_sel = n                      # "+ Add a pattern…"
            ui._hk_enter()
            self.assertEqual(ui.state, 'config_edit')
            ui.input_buf = 'git stash drop'
            ui._confirm_text()
            self.assertEqual(ui.state, 'config')
            self.assertIn('git stash drop', tui.hk_config.load(cfg))
            ui.config_sel = n                      # edit it
            ui._hk_enter()
            ui.input_buf = 'git stash clear'
            ui._confirm_text()
            self.assertEqual(tui.hk_config.load(cfg)[n], 'git stash clear')
            ui.input_buf = ''
            ui.config_sel = n
            ui._hk_enter()
            ui.input_buf = 'a | b'                 # rejected, stays in editor
            ui._confirm_text()
            self.assertEqual(ui.state, 'config_edit')
            self.assertIn('rejected', ui.notice)
            ui.state = 'config'
            ui.config_sel = n
            ui._hk_remove()
            self.assertEqual(len(tui.hk_config.load(cfg)), n)


if __name__ == '__main__':
    unittest.main()
