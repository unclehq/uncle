#!/usr/bin/env python3
"""TUI tests for the persistent home agent (AC-2, AC-4, AC-5, AC-7, AC-8, AC-9). No real claude is started."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
os.environ.setdefault('UNCLE_HOME_AGENT', '0')
import uncle_tui as tui  # noqa: E402
import supervisor_runner  # noqa: E402
import supervisor as supervision_lib  # noqa: E402


def reply(text, denials=()):
    return {'status': 'reply', 'reply': text, 'usage': None, 'cost': None, 'exit': 0, 'log': '',
            'permission_denials': list(denials)}


class HomeAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        self.current = self.root
        for target in (patch.object(tui, '_project_root', side_effect=lambda: self.current),
                       patch.dict(os.environ, {}, clear=False)):
            target.start()
            self.addCleanup(target.stop)
        self.ui = tui.UncleTUI.__new__(tui.UncleTUI)
        self.ui._ensure_chat()
        self.ui.state, self.ui.proc = 'menu', None
        self.ui._run = Mock()
        self.ui._set_field = Mock()
        self.ui._agent_state()
        self.ui.agent_started = 0.0
        self.ui._switch_project_root = Mock(side_effect=lambda p: setattr(self, 'current', p))

    def apply(self, text, denials=()):
        request = Mock(home_agent=True, generation=self.ui.agent_generation)
        self.ui._record_chat_call = Mock()
        return self.ui._apply_home_agent_reply(request, reply(text, denials))

    def history_text(self):
        return '\n'.join(t for _, t in self.ui.home_history)

    # AC-4: tool result shown, nothing acted on without a validated block
    def test_agent_result_is_shown_verbatim_and_starts_nothing(self):
        self.apply('I ran `gh repo fork`: it failed with exit 1 (auth required).')
        self.assertIn('failed with exit 1', self.history_text())
        self.ui._run.assert_not_called()

    # AC-8: a denied tool becomes a user approval with the verbatim command
    def test_denial_is_surfaced_for_approval(self):
        self.apply('Need permission.', [{'tool_name': 'Bash', 'tool_input': {'command': 'gh repo fork unclehq/uncle'}}])
        self.assertEqual(self.ui.agent_pending['kind'], 'tool')
        self.assertIn('gh repo fork unclehq/uncle', self.history_text())
        self.assertEqual(self.ui.agent_pending['rule'], 'Bash(gh repo fork unclehq/uncle)')

    def test_decline_grants_nothing(self):
        self.apply('x', [{'tool_name': 'Bash', 'tool_input': {'command': 'ls'}}])
        self.ui._supervisor_turn = Mock()
        self.ui.send_home_chat('no thanks')
        self.assertIsNone(self.ui.agent_pending)
        self.assertEqual(self.ui.agent_grants, [])

    # AC-5: validated cwd moves the root; invalid leaves it unchanged
    def test_created_directory_becomes_project_root(self):
        self.ui.agent_started = 0.0
        target = os.path.join(self.root, 'demo')
        os.mkdir(target)
        self.apply('Created it.\n```uncle_cwd\n%s\n```' % json.dumps({'path': target}))
        self.assertEqual(self.current, os.path.realpath(target))

    def test_invalid_cwd_leaves_root_unchanged(self):
        for bad in ('relative/dir', os.path.join(self.root, 'missing'), os.sep):
            self.apply('Done.\n```uncle_cwd\n%s\n```' % json.dumps({'path': bad}))
        self.assertEqual(self.current, self.root)
        self.assertIn('Ignored uncle_cwd', self.history_text())

    def test_two_cwd_blocks_execute_none(self):
        target = os.path.join(self.root, 'a')
        os.mkdir(target)
        block = '```uncle_cwd\n%s\n```' % json.dumps({'path': target})
        self.apply('x\n%s\n%s' % (block, block))
        self.assertEqual(self.current, self.root)

    # AC-6: unvalidated action text is never run; a valid action asks for confirmation
    def test_action_requires_confirmation(self):
        self.ui._next_run_unattended = lambda: False
        self.apply('Plan.\n```uncle_action\n{"uncle_action": "github_issue", "issue": "34", "start": true, "message": "Building issue 34."}\n```')
        self.assertEqual(self.ui.agent_pending['kind'], 'action')
        self.ui._run.assert_not_called()

    def test_action_runs_without_asking_in_auto_mode(self):
        self.ui._next_run_unattended = lambda: True
        self.ui._home_action = Mock()
        self.apply('Plan.\n```uncle_action\n{"uncle_action": "github_issue", "issue": "34", "start": true, "message": "Building issue 34."}\n```')
        self.assertIsNone(self.ui.agent_pending)
        self.ui._home_action.assert_called_once()

    def test_invalid_action_is_ignored(self):
        self.apply('x\n```uncle_action\n{"uncle_action": "github_issue", "issue": "34"}\n```')
        self.assertIsNone(self.ui.agent_pending)
        self.assertIn('Ignored an invalid uncle_action', self.history_text())

    # AC-7: while a build runs the home agent is not used and the supervisor argv has no tools
    def test_running_build_is_not_idle_and_supervisor_has_no_tools(self):
        self.ui.state = 'running'
        self.assertFalse(self.ui._home_agent_idle())
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, 'claude')
            Path(fake).write_text('#!/bin/sh\n')
            os.chmod(fake, 0o755)
            cfg = supervision_lib.Config() if hasattr(supervision_lib, 'Config') else None
            argv, _env, _home = supervisor_runner.build_command(
                cfg, {'PATH': os.environ.get('PATH', ''), 'WORKFLOW_CLAUDE_CMD': fake})
        self.assertEqual(argv[argv.index('--tools') + 1], '')
        self.assertNotIn('--allowedTools', argv)

    def test_quiesce_drops_grants_and_pending(self):
        self.ui.agent_grants = ['Bash(ls)']
        self.ui.agent_pending = {'kind': 'tool', 'generation': 0}
        self.ui._agent_quiesce()
        self.assertEqual((self.ui.agent_grants, self.ui.agent_pending), ([], None))

    # AC-2 / AC-9
    def test_housekeeping_removed_from_ui_and_legacy_config_ignored(self):
        self.assertNotIn('housekeeping', Path(ROOT / 'uncle_tui.py').read_text().lower())
        self.assertFalse(self.ui._slash_choices() and any('housekeeping' in c or c == '/mode' for c in self.ui._slash_choices()))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'config')
            Path(path).write_text('housekeeping.disallow=git push\nhousekeeping.runner=codex\n')
            with patch.dict(os.environ, {'UNCLE_HOUSEKEEPING_SESSION': '1'}):
                config = supervision_lib.load_config(path)
        self.assertEqual(config.runner, supervision_lib.load_config(os.path.join(self.root, 'none')).runner)


class SwitchProjectRootTest(unittest.TestCase):
    def test_switch_survives_run_and_moves_config(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            a, b = os.path.realpath(a), os.path.realpath(b)
            saved = tui.CONFIG_PATH
            self.addCleanup(setattr, tui, 'CONFIG_PATH', saved)
            with patch.dict(os.environ, {'UNCLE_PROJECT_ROOT': a}):
                ui = tui.UncleTUI.__new__(tui.UncleTUI)
                ui.home_history = []
                ui.load_config = Mock()
                ui._launch_root = a  # as left by an earlier _follow_project_root
                ui._switch_project_root(b)
                ui._restore_launch_root()  # what _run() does first
                self.assertEqual(os.environ['UNCLE_PROJECT_ROOT'], b)
                self.assertEqual(tui._project_root(), b)
                self.assertEqual(tui.CONFIG_PATH, os.path.join(b, '.uncle', 'config'))
                self.assertEqual(os.environ['UNCLE_CONFIG'], tui.CONFIG_PATH)
                ui.load_config.assert_called_once()


if __name__ == '__main__':
    unittest.main()
