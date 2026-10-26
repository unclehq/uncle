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


class ChangeRequestStartup(StartupAction):
    # Shares StartupAction.setUp; its own tests are not re-run here.
    test_description_starts_the_build_immediately = None
    test_no_supervisor_is_needed_for_a_launch_flag = None
    test_existing_brief_is_replaced_without_a_proposal = None
    test_typed_messages_are_unchanged = None

    TEXT = 'Fix the bug.\r\nNo heading here\n\n  trailing  '

    def setUp(self):
        super().setUp()
        self.private = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.private, ignore_errors=True))
        self.private.chmod(0o700)
        self.file = self.private / 'cr'
        self.file.write_bytes(b'Fix the bug.\nNo heading here\n\n  trailing  ')
        self.ui._startup_action = 'change_request'
        self.ui._startup_text_file = str(self.file)

    def target(self):
        return Path(generated_input_path('CHANGE_REQUEST.md', self.root))

    def test_starts_change_workflow_with_exact_bytes_and_no_github(self):
        with patch('subprocess.run') as run, patch('subprocess.Popen') as popen:
            self.ui._handle_startup_action()
        run.assert_not_called()
        popen.assert_not_called()
        self.assertEqual(self.target().read_bytes(), b'Fix the bug.\nNo heading here\n\n  trailing  ')
        self.assertEqual(self.ui.workflow_idx, 2)
        self.assertEqual(self.ui.state, 'running')
        self.assertFalse(self.file.exists())
        self.ChatRequest.assert_not_called()

    def test_existing_request_refused_untouched(self):
        existing = self.root / 'CHANGE_REQUEST.md'
        existing.write_text('old')
        with self.assertRaises(tui.StartupRefused) as ctx:
            self.ui._handle_startup_action()
        self.assertIn('CHANGE_REQUEST.md already exists', str(ctx.exception))
        self.assertEqual(existing.read_text(), 'old')
        self.assertFalse((self.root / '.uncle/brief-history').exists())
        self.assertEqual(self.ui.state, 'menu')

    def test_dangling_symlink_refused(self):
        (self.root / 'CHANGE_REQUEST.md').symlink_to(self.root / 'nowhere')
        with self.assertRaises(tui.StartupRefused):
            self.ui._handle_startup_action()
        self.assertTrue((self.root / 'CHANGE_REQUEST.md').is_symlink())

    def test_untrusted_paths_refused_and_not_deleted(self):
        link_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(link_dir, ignore_errors=True))
        link_dir.chmod(0o700)
        victim = link_dir / 'victim'
        victim.write_text('keep')
        link = self.private / 'link'
        link.symlink_to(victim)
        open_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(open_dir, ignore_errors=True))
        open_dir.chmod(0o755)
        loose = open_dir / 'f'
        loose.write_text('keep')
        for path in (str(link), str(self.private), str(loose), 'relative', '', None):
            self.ui._startup_action = 'change_request'
            self.ui._startup_text_file = path
            with self.assertRaises(tui.StartupRefused):
                self.ui._handle_startup_action()
        self.assertEqual(victim.read_text(), 'keep')
        self.assertEqual(loose.read_text(), 'keep')
        self.assertFalse(self.target().exists())

    def test_app_and_issue_unchanged_with_text_file_set(self):
        self.ui._startup_action, self.ui._startup_text = 'create_app', DESCRIPTION
        self.ui._handle_startup_action()
        self.assertIn(DESCRIPTION, self.brief())
        self.assertEqual(self.ui.workflow_idx, 0)
        self.assertTrue(self.file.exists())


if __name__ == '__main__':
    unittest.main()
