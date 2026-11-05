import os, sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts/lib'))
os.environ.pop('UNCLE_HOUSEKEEPING_SESSION', None)
import housekeeping_session as hs
import uncle_tui as tui


class Command(unittest.TestCase):
    def test_deny_list_tools_and_secrets(self):
        with patch('shutil.which', return_value='/bin/claude'):
            argv, env = hs.build_command(str(ROOT), '/nonexistent', 'sonnet', 'low',
                                         {'PATH': '/bin', 'ANTHROPIC_API_KEY': 'k'})
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        self.assertEqual(argv[argv.index('--allowedTools') + 1], hs.TOOLS)
        self.assertIn('Bash(git push --force:*)', argv[argv.index('--disallowedTools') + 1])
        self.assertIn('--output-format', argv)

    def test_missing_claude_is_unavailable(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaises(ValueError):
                hs.build_command(str(ROOT), '/nonexistent', 'sonnet', 'low', {'PATH': '/bin'})


class Vetting(unittest.TestCase):
    def test_denied_commands_are_caught_inside_shell_wrappers_and_chains(self):
        deny = ['git push --force', 'sudo']
        self.assertTrue(hs.command_denied('/bin/zsh -lc "git push --force origin x"', deny))
        self.assertTrue(hs.command_denied('git status && sudo ls', deny))
        self.assertTrue(hs.command_denied('echo "unterminated', deny))
        self.assertFalse(hs.command_denied('git branch -d merged', deny))

    def test_unsupported_runner_is_unavailable(self):
        with self.assertRaises(ValueError):
            hs.persistent_session('aider', str(ROOT), '/nonexistent', 'm', 'low', '.')


class FakeCodex(unittest.TestCase):
    """The Codex session against a scripted app-server, so the protocol handling is exercised without a login."""
    def test_turn_returns_final_answer_and_vets_approvals(self):
        import json, tempfile, threading, time
        script = Path(tempfile.mkdtemp()) / 'fake.py'
        script.write_text(r"""
import sys, json
def out(o): print(json.dumps(o), flush=True)
for line in sys.stdin:
    m = json.loads(line)
    if m.get('method') == 'initialize': out({'id': m['id'], 'result': {}})
    elif m.get('method') == 'thread/start': out({'id': m['id'], 'result': {'thread': {'id': 'T'}}})
    elif m.get('method') == 'turn/start':
        out({'id': m['id'], 'result': {'turn': {}}})
        out({'id': 900, 'method': 'item/commandExecution/requestApproval', 'params': {'command': 'sudo rm x'}})
        reply = json.loads(sys.stdin.readline())
        out({'method': 'item/started', 'params': {'item': {'type': 'agentMessage', 'id': 'a', 'phase': 'final_answer'}}})
        out({'method': 'item/agentMessage/delta', 'params': {'delta': 'done'}})
        out({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'id': 'a', 'text': 'decision=' + reply['result']['decision'], 'phase': 'final_answer'}}})
        out({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
""")
        session = hs.CodexSession([sys.executable, str(script)], dict(os.environ), '.', 'be brief', 'sonnet', 'low', ['sudo'])
        import io, queue
        progress = queue.Queue()
        lines = session.turn('hi', io.BytesIO(), time.monotonic() + 20, threading.Event(), progress)
        session.close()
        self.assertIsNotNone(lines)
        self.assertIn('decision=decline', lines[0])
        self.assertEqual(progress.get_nowait(), 'done')


class Routing(unittest.TestCase):
    def ui(self):
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state, ui.proc, ui.home_request, ui.home_history = 'chat', None, None, []
        return ui

    def test_idle_homepage_defaults_to_housekeeping_and_modes_switch(self):
        ui = self.ui()
        self.assertTrue(ui._housekeeping_idle())
        ui.home_mode = 'supervisor'
        self.assertFalse(ui._housekeeping_idle())
        ui.home_mode, ui.state = 'housekeeping', 'running'
        self.assertFalse(ui._housekeeping_idle())

    def test_prose_goes_to_runner_slash_does_not(self):
        ui = self.ui()
        ui._housekeeping_turn = Mock(return_value=True)
        ui.send_home_chat('delete merged branches')
        ui._housekeeping_turn.assert_called_once_with('delete merged branches')


if __name__ == '__main__':
    unittest.main()
