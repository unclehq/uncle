"""`uncle --application TEXT`: the description goes through the homepage
supervisor, whose brief starts the build; anything short of that falls back to
starting from the description as written, so an unattended launch never stalls."""
import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts/lib')]
import uncle_tui as tui  # noqa: E402
from chat import Conversation  # noqa: E402
from generated_input import generated_input_path  # noqa: E402

DESCRIPTION = 'build a groovy calculator webapp with a groovy background'


def drafted_brief():
    return '# Application brief\n\n' + '\n\n'.join(
        '## %s\nA calculator page with a swirling seventies background.' % field
        for field in Conversation.fields['app'])


class StartupAction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        config = self.root / 'config'
        config.write_text('supervision.model sonnet\n')
        for patcher in (patch.object(tui, '_project_root', return_value=str(self.root)),
                        patch.object(tui, 'CONFIG_PATH', str(config)),
                        patch.object(tui, 'list_models', return_value=[]),
                        patch.object(tui, 'default_model', return_value=''),
                        patch.object(tui, 'read_keys', return_value={}),
                        patch.object(tui.UncleTUI, '_viewer_command', return_value='')):
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(tui, 'ChatRequest')
        self.ChatRequest = patcher.start()
        self.addCleanup(patcher.stop)
        self.ChatRequest.return_value.events = queue.Queue()
        patcher = patch.object(tui, 'supervisor_command', return_value=(['fake-claude'], {'PATH': '/bin'}, '/tmp/x'))
        self.command = patcher.start()
        self.addCleanup(patcher.stop)
        self.ui = tui.UncleTUI(None)
        self.ui._run = lambda: setattr(self.ui, 'state', 'running')
        self.ui._startup_action, self.ui._startup_text = 'create_app', DESCRIPTION

    def reply(self, home_action, prose=''):
        self.ChatRequest.return_value.events.put({
            'status': 'reply', 'elapsed': 0, 'exit': 0, 'usage': None, 'cost': None, 'log': '',
            'reply': json.dumps({'schema': 1, 'reply': prose, 'steer': None, 'gate_answer': None,
                                 'home_action': home_action})})
        self.assertTrue(self.ui.poll_home_chat())

    def brief(self):
        return Path(generated_input_path('REQUIREMENTS.md', self.root)).read_text()

    def system_lines(self):
        return [line for role, line in self.ui.home_history if role == 'system']

    def test_description_starts_the_build_immediately(self):
        self.ui._handle_startup_action()
        self.ChatRequest.assert_not_called()
        self.assertIn(DESCRIPTION, self.brief())
        self.assertEqual(self.ui.state, 'running')
        self.assertEqual(self.ui.workflow_idx, 0)
        self.assertEqual(self.ui.chat_error, '')

    def test_no_supervisor_is_needed_for_a_launch_flag(self):
        self.command.side_effect = ValueError('no runner configured')
        self.ui._handle_startup_action()
        self.assertIn(DESCRIPTION, self.brief())
        self.assertEqual(self.ui.state, 'running')
        self.ChatRequest.assert_not_called()

    def test_existing_brief_is_replaced_without_a_proposal(self):
        (self.root / 'REQUIREMENTS.md').write_text('Old brief')
        self.ui._handle_startup_action()
        self.assertIsNone(getattr(self.ui, 'home_replace_proposal', None))
        self.assertIn(DESCRIPTION, self.brief())
        backups = list((self.root / '.uncle/brief-history').glob('*/REQUIREMENTS.md'))
        self.assertEqual([b.read_text() for b in backups], ['Old brief'])
        self.assertEqual(self.ui.state, 'running')

    def test_typed_messages_are_unchanged(self):
        # No launch flag: a drafted-only reply stays a draft, as before.
        self.ui._startup_action = None
        self.ui.send_home_chat('build ' + DESCRIPTION)
        self.reply({'uncle_action': 'create_app', 'document': drafted_brief(), 'start': False, 'message': 'Drafted.'})
        self.assertTrue(Path(generated_input_path('REQUIREMENTS.md', self.root)).is_file())
        self.assertEqual(self.ui.state, 'menu')


if __name__ == '__main__':
    unittest.main()
