import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import uncle_tui as tui
from chat import Conversation
from home_actions import parse_reply, prompt
from home_chat import IssueSeedRequest


def brief(kind):
    return '# Brief\n\n' + '\n\n'.join('## ' + field + '\n' +
        ('Shared grocery lists with offline support.' if field == 'Summary' else 'None')
        for field in Conversation.fields[kind])


class Actions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        context = patch.object(tui, '_project_root', return_value=str(self.root))
        context.start()
        self.addCleanup(context.stop)
        self.ui = tui.UncleTUI.__new__(tui.UncleTUI)
        self.ui._ensure_chat()
        self.ui.state, self.ui.proc = 'menu', None
        self.ui._run = Mock()
        self.ui._set_field = Mock()

    def test_run_slash_command_accepts_stage_argument(self):
        self.ui.run_named_stage = Mock()
        self.ui.chat_composer = '/run adversarial-review'
        self.assertTrue(self.ui._chat_command(10))
        self.ui.run_named_stage.assert_called_once_with('adversarial-review')
        self.assertEqual(self.ui.chat_composer, '')

    def test_runstage_accepts_a_numbered_implementation_step(self):
        self.ui.run_named_stage = Mock()
        self.ui.chat_composer = '/runstage implementation-step-7'
        self.assertTrue(self.ui._chat_command(10))
        self.ui.run_named_stage.assert_called_once_with('implementation-step-7')
        self.assertEqual(self.ui.chat_composer, '')

    def test_run_completion_leaves_room_for_stage(self):
        self.ui.run_named_stage = Mock()
        self.ui.chat_composer = '/ru'
        self.assertTrue(self.ui._chat_command(10))
        self.assertEqual(self.ui.chat_composer, '/run ')
        self.ui.run_named_stage.assert_not_called()

    def test_backslash_q_quits_when_resume_item_is_present(self):
        # Resume is inserted before Configure and Quit, so command dispatch
        # must not rely on their former fixed menu indices.
        with patch.object(self.ui, '_resume_available', return_value=True):
            self.ui.chat_composer = r'\q'
            self.assertTrue(self.ui._chat_command(10))
        self.assertEqual(self.ui.state, 'quit')

    def test_clear_archives_the_build_and_leaves_source(self):
        wf = self.root/'.uncle/workflow'
        (wf/'approvals').mkdir(parents=True)
        for name in ('state', 'origin', 'keep.txt'):
            (wf/name).write_text('saved')
        (wf/'approvals/PROJECT_PLAN.sha256').write_text('digest')
        (self.root/'.uncle/launch.json').write_text('{"kind":"none"}')
        for doc in ('REQUIREMENTS.md', 'PROJECT_PLAN.md', 'IMPLEMENTATION_NOTES.md'):
            (self.root/doc).write_text(doc)
        (self.root/'src').mkdir()
        (self.root/'src/app.js').write_text('code')
        (self.root/'index.html').write_text('<h1>app</h1>')
        # A document the repository tracks belongs to the project and stays.
        (self.root/'FINAL_AUDIT.md').write_text('committed audit')
        import subprocess
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'FINAL_AUDIT.md'], check=True)
        self.ui.chat_composer = '/clear'
        self.ui._chat_command(10)
        self.assertEqual(self.ui.chat_error, '')
        for doc in ('REQUIREMENTS.md', 'PROJECT_PLAN.md', 'IMPLEMENTATION_NOTES.md'):
            self.assertFalse((self.root/doc).exists(), doc)
        self.assertEqual((self.root/'FINAL_AUDIT.md').read_text(), 'committed audit', 'tracked documents stay')
        self.assertFalse((self.root/'.uncle/launch.json').exists())
        for name in ('state', 'origin', 'keep.txt', 'approvals'):
            self.assertFalse((wf/name).exists(), name)
        self.assertEqual((self.root/'src/app.js').read_text(), 'code', 'source is not a build artifact')
        self.assertTrue((self.root/'index.html').exists())
        archives = list((self.root/'.uncle/workflow-history').iterdir())
        self.assertEqual(len(archives), 1)
        archive = archives[0]
        self.assertEqual((archive/'keep.txt').read_text(), 'saved')
        self.assertTrue((archive/'approvals/PROJECT_PLAN.sha256').exists())
        self.assertEqual((archive/'documents/PROJECT_PLAN.md').read_text(), 'PROJECT_PLAN.md')
        self.assertEqual((archive/'documents/REQUIREMENTS.md').read_text(), 'REQUIREMENTS.md')
        self.assertTrue((archive/'documents/launch.json').exists())
        self.assertIn('archived', self.ui.home_history[-1][1])
        self.ui.chat_composer = '/clear'
        self.ui._chat_command(10)
        self.assertEqual(self.ui.chat_error, '')
        self.assertEqual(len(list((self.root/'.uncle/workflow-history').iterdir())), 1, 'nothing left to archive')
        self.assertIn('Nothing to clear', self.ui.home_history[-1][1])

    def test_clear_targets_a_run_worktree_by_issue(self):
        other = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(other, ignore_errors=True))
        (other/'.uncle/workflow').mkdir(parents=True)
        (other/'.uncle/workflow/state').write_text('70:UPDATED_PLAN\n')
        (other/'CHANGE_PLAN.md').write_text('plan')
        (self.root/'PROJECT_PLAN.md').write_text('mine')
        rows = [dict(path=str(other), issue='70', state='UPDATED_PLAN', locked=False)]
        with patch.object(tui.worktree_runs, 'runs', return_value=rows), \
                patch.object(tui.worktree_runs, 'worktrees', return_value=[str(other)]):
            self.ui.chat_composer = '/clear #70'
            self.ui._chat_command(10)
        self.assertEqual(self.ui.chat_error, '')
        self.assertFalse((other/'.uncle/workflow/state').exists())
        self.assertFalse((other/'CHANGE_PLAN.md').exists())
        self.assertTrue((other/'.uncle/workflow-history').is_dir())
        self.assertTrue((self.root/'PROJECT_PLAN.md').exists(), 'the project the homepage is in is untouched')
        self.assertIn(str(other), self.ui.home_history[-1][1])
        with patch.object(tui.worktree_runs, 'runs', return_value=rows):
            self.ui.chat_composer = '/clear #99'
            self.ui._chat_command(10)
        self.assertIn('No run for #99', self.ui.chat_error)

    def test_resume_targets_a_run_worktree_by_issue(self):
        import shutil
        other = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(other, ignore_errors=True))
        (other/'.uncle/workflow').mkdir(parents=True)
        (other/'.uncle/workflow/state').write_text('70:WAIT_PLAN_APPROVAL\n')
        (other/'.uncle/workflow/family').write_text('change\n')
        rows = [dict(path=str(other), issue='70', state='WAIT_PLAN_APPROVAL', locked=False)]
        with patch.object(tui.worktree_runs, 'runs', return_value=rows), \
                patch.object(tui.worktree_runs, 'worktrees', return_value=[str(other)]), \
                patch.dict(os.environ, {}, clear=False):
            self.ui.chat_composer = '/resume #70'
            self.ui._chat_command(10)
            self.assertEqual(os.environ.get('UNCLE_PROJECT_ROOT'), str(other))
        self.assertEqual(self.ui.chat_error, '')
        self.ui._run.assert_called_once()
        self.assertEqual(self.ui.workflow_idx, 2, 'a change-family run resumes as workflow_idx 2')
        self.assertTrue(self.ui.resume_workflow_pending)
        self.assertIn(str(other), self.ui.home_history[-1][1])
        # An app-family run resumes as workflow_idx 0.
        (other/'.uncle/workflow/family').write_text('app\n')
        self.ui._run.reset_mock()
        with patch.object(tui.worktree_runs, 'runs', return_value=rows), \
                patch.object(tui.worktree_runs, 'worktrees', return_value=[str(other)]), \
                patch.dict(os.environ, {}, clear=False):
            self.ui.chat_composer = '/resume #70'
            self.ui._chat_command(10)
        self.assertEqual(self.ui.chat_error, '')
        self.assertEqual(self.ui.workflow_idx, 0, 'an app-family run resumes as workflow_idx 0')
        self.ui._run.assert_called_once()
        # No run for that issue.
        with patch.object(tui.worktree_runs, 'runs', return_value=[]), patch.dict(os.environ, {}, clear=False):
            self.ui.chat_composer = '/resume #99'
            self.ui._chat_command(10)
        self.assertIn('No run for #99', self.ui.chat_error)
        # A live driver refuses instead of relaunching a second one.
        with patch.object(tui.worktree_runs, 'runs', return_value=rows), \
                patch.object(tui.worktree_runs, 'worktrees', return_value=[str(other)]), \
                patch.object(self.ui, '_run_locked', return_value=True), \
                patch.dict(os.environ, {}, clear=False):
            self.ui.chat_composer = '/resume #70'
            self.ui._chat_command(10)
        self.assertIn('wait for it to finish', self.ui.chat_error)

    def test_bare_resume_slash_command_is_unchanged(self):
        self.ui.workflow_idx = 0
        self.ui.triage_resume = Mock()
        self.ui.chat_composer = '/resume'
        self.ui._chat_command(10)
        self.ui.triage_resume.assert_called_once()
        self.ui._run.assert_not_called()

    def test_bare_resume_without_a_session_build_runs_the_app_in_place(self):
        (self.root/'REQUIREMENTS.md').write_text('# Project brief\n\nA grocery list app.\n')
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('UNCLE_PROJECT_ROOT_LOCKED', None)
            self.ui.chat_composer = '/resume'
            self.ui._chat_command(10)
            self.assertEqual(os.environ.get('UNCLE_PROJECT_ROOT'), str(self.root))
            self.assertEqual(os.environ.get('UNCLE_PROJECT_ROOT_LOCKED'), '1')
        self.assertEqual(self.ui.chat_error, '')
        self.assertEqual(self.ui.workflow_idx, 0)
        self.assertTrue(self.ui.resume_workflow_pending)
        self.ui._run.assert_called_once()
        self.assertEqual(self.ui.home_history[-1],
                         ('system', 'Resuming the application build in %s.' % self.root))

    def test_bare_resume_without_a_session_build_or_brief_still_refuses(self):
        self.ui.chat_composer = '/resume'
        self.ui._chat_command(10)
        self.assertIn('No workflow has run in this session', self.ui.chat_error)
        self.ui._run.assert_not_called()

    def test_resume_build_action_targets_an_issue(self):
        self.ui._resume_build = Mock(return_value='resumed')
        self.reply(uncle_action='resume_build', issue='70')
        self.ui._resume_build.assert_called_once_with('#70')
        self.reply(uncle_action='resume_build')
        self.ui._resume_build.assert_called_with('')
        self.assertEqual(self.ui.home_history[-1], ('system', 'resumed'))

    def test_stop_command_and_actions(self):
        self.ui.stop_workflow = Mock()
        self.ui.chat_composer = '/stop'
        self.ui._chat_command(10)
        self.ui.stop_workflow.assert_not_called()
        self.assertIn('No build is running', self.ui.home_history[-1][1])
        self.ui.proc = Mock()
        self.ui.proc.poll.return_value = None
        self.ui.state = 'running'
        self.ui.status_stage = 'implementation'
        self.ui.chat_composer = '/stop'
        self.ui._chat_command(10)
        self.ui.stop_workflow.assert_called_once()
        self.assertIn('Stopped the build at implementation', self.ui.home_history[-1][1])
        self.assertEqual(self.ui.state, 'menu')
        self.assertEqual(self.ui.chat_composer, '')
        # The supervisor can do the same while a build runs.
        self.ui.stop_workflow.reset_mock()
        self.ui.proc.poll.return_value = None
        self.reply(uncle_action='stop_build')
        self.ui.stop_workflow.assert_called_once()
        self.assertEqual(self.ui.chat_error, '')

    def test_clear_build_action_targets_an_issue(self):
        self.ui._clear_build = Mock(return_value='cleared')
        self.reply(uncle_action='clear_build', issue='70')
        self.ui._clear_build.assert_called_once_with('#70')
        self.reply(uncle_action='clear_build')
        self.ui._clear_build.assert_called_with('')
        self.assertEqual(self.ui.home_history[-1], ('system', 'cleared'))

    def test_clear_during_a_run_leaves_the_build_alone(self):
        (self.root/'PROJECT_PLAN.md').write_text('plan')
        self.ui.proc = Mock()
        self.ui.proc.poll.return_value = None
        self.ui.chat_composer = '/clear'
        self.ui._chat_command(10)
        self.assertEqual(self.ui.chat_error, '')
        self.assertIn('A workflow is running', self.ui.home_history[-1][1])
        self.assertTrue((self.root/'PROJECT_PLAN.md').exists())
        self.assertFalse((self.root/'.uncle/workflow-history').exists())

    def reply(self, **action):
        # TD-4 (Issue 45): the chat worker is the supervisor; a homepage action
        # arrives as the `home_action` of its schema-1 reply.
        self.ui.home_request = Mock(events=queue.Queue(), home_intent=True)
        self.ui.home_request.events.put({'status': 'reply', 'elapsed': 0, 'exit': 0, 'usage': None, 'cost': None, 'log': '',
                                         'reply': json.dumps({'schema': 1, 'reply': '', 'steer': None, 'gate_answer': None,
                                                              'home_action': dict(message='Requested action.', **action)})})
        self.assertTrue(self.ui.poll_home_chat())

    def test_create_and_start_app(self):
        self.reply(uncle_action='create_app', document=brief('app'), start=True)
        self.assertIn('offline support', (self.root/'REQUIREMENTS.md').read_text())
        self.ui._run.assert_called_once()
        self.assertEqual(self.ui.workflow_idx, 0)
        self.assertEqual(self.ui.chat_error, '')

    def test_draft_change_then_run(self):
        self.reply(uncle_action='create_change', document=brief('change'), start=False)
        self.ui._run.assert_not_called()
        self.assertTrue((self.root/'CHANGE_REQUEST.md').exists())
        self.reply(uncle_action='run_change')
        self.ui._run.assert_called_once()
        self.assertEqual(self.ui.workflow_idx, 2)

    def test_run_existing_app(self):
        (self.root/'REQUIREMENTS.md').write_text('User requirements')
        self.reply(uncle_action='run_app')
        self.ui._run.assert_called_once()
        self.assertEqual(self.ui.workflow_idx, 0)

    def test_start_archives_existing_workflow_but_resume_keeps_it(self):
        """Only the recovery path is allowed to reuse a workspace's state."""
        del self.ui._run
        self.ui.workflow_idx = 0
        self.ui.maybe_reload = Mock()
        self.ui._restore_launch_root = Mock()
        self.ui._rerun_pending = Mock(return_value=False)
        self.ui._enter_run_worktree = Mock()
        self.ui.start_workflow = Mock()

        self.ui._run()
        self.assertTrue(self.ui.new_workflow_pending)
        self.ui.start_workflow.assert_called_once()

        self.ui.resume_workflow_pending = True
        self.ui._run()
        self.assertFalse(self.ui.new_workflow_pending)

    def test_issue_build(self):
        self.reply(uncle_action='github_issue', issue='42', start=True)
        self.ui._run.assert_called_once()
        self.assertEqual((self.ui.workflow_idx, self.ui.input_buf, self.ui.state), (1, '42', 'issue'))
        self.assertEqual(self.ui.issue_mode, '')

    def test_explicit_issue_build_starts_auto_without_model(self):
        (self.root / 'CHANGE_REQUEST.md').write_text('Keep this request')
        for reference in ('https://github.com/unclehq/uncle/issues/34', '#34', '34'):
            with self.subTest(reference=reference), patch.object(tui, 'HomeRequest') as request:
                self.ui.state = 'menu'
                self.ui._run.reset_mock()
                self.ui.send_home_chat('build from issue ' + reference)
                self.assertEqual(self.ui.state, 'issue')
                self.assertEqual(self.ui.input_buf, reference.removeprefix('#'))
                self.assertEqual(self.ui.issue, reference.removeprefix('#'))
                self.assertEqual(self.ui.workflow_idx, 1)
                self.assertEqual(self.ui.sel, 0)
                request.assert_not_called()
                self.ui._run.assert_called_once()
                self.assertEqual(self.ui.issue_mode, '')
        self.assertEqual((self.root / 'CHANGE_REQUEST.md').read_text(), 'Keep this request')

    def test_issue_import_without_build(self):
        with patch.object(tui, 'IssueSeedRequest') as worker:
            self.reply(uncle_action='github_issue', issue='42', start=False)
            command, root, env = worker.call_args.args
            self.assertEqual(command[-3:], ['42', '--change', '--seed-only'])
            self.assertEqual(env['UNCLE_PROJECT_ROOT'], root)
            self.ui._run.assert_not_called()

    def test_natural_issue_launch_phrases(self):
        url = 'https://github.com/unclehq/uncle/issues/44'
        for phrase, mode in [('build this issue ', ''), ('build from github issue ', ''),
                             ('start change request from github issue ', '--change'),
                             ('build this ', '')]:
            with self.subTest(phrase=phrase), patch.object(tui, 'HomeRequest') as request:
                self.ui.state = 'menu'
                self.ui._run.reset_mock()
                self.ui.send_home_chat(phrase + url)
                self.ui._run.assert_called_once()
                self.assertEqual(self.ui.issue, url)
                self.assertEqual(self.ui.issue_mode, mode)
                request.assert_not_called()

    def test_build_issue_number_without_issue_keyword(self):
        for text in ('build #45', 'bulid #45', 'please bulid #45', 'build 45', 'implement #45', 'please build #45'):
            with self.subTest(text=text), patch.object(tui, 'HomeRequest') as request:
                self.ui.state = 'menu'
                self.ui._run.reset_mock()
                self.ui.send_home_chat(text)
                self.assertEqual(self.ui.issue, '45')
                self.assertEqual(self.ui.workflow_idx, 1)
                self.ui._run.assert_called_once()
                request.assert_not_called()

    def test_enter_submits_numeric_issue_with_picker_open(self):
        for choices in ([], ['#45 Example']):
            with self.subTest(choices=choices):
                self.ui.state = 'menu'
                self.ui.chat_focus = 'chat'
                self.ui.chat_composer = 'build #45'
                self.ui.chat_picker = True
                self.ui.chat_picker_kind = 'issue'
                self.ui.chat_choices = choices
                self.ui._run.reset_mock()
                self.ui._chat_key(10)
                self.ui._run.assert_called_once()
                self.assertEqual(self.ui.issue, '45')
                self.assertEqual(self.ui.chat_composer, '')

    def test_model_issue_hash_is_normalized(self):
        self.reply(uncle_action='github_issue', issue='#45', start=True)
        self.ui._run.assert_called_once()
        self.assertEqual(self.ui.issue, '45')

    def test_auto_selection_advances_prefilled_issue_to_build(self):
        # Exercise the actual transition, stubbing only reload and launch.
        del self.ui._run
        self.ui.maybe_reload = Mock()
        self.ui.start_workflow = Mock()
        self.ui.send_home_chat('build from issue https://github.com/unclehq/uncle/issues/34')
        self.assertEqual(self.ui.state, 'running')
        self.assertEqual(self.ui.issue, 'https://github.com/unclehq/uncle/issues/34')
        self.assertEqual(self.ui.issue_mode, '')
        self.assertEqual(self.ui.workflow_idx, 1)
        self.ui.start_workflow.assert_called_once()

    def test_existing_document_is_preserved(self):
        target = self.root/'REQUIREMENTS.md'
        target.write_text('Keep this')
        self.reply(uncle_action='create_app', document=brief('app'), start=True)
        self.assertEqual(target.read_text(), 'Keep this')
        self.ui._run.assert_not_called()
        self.assertIn('Waiting for your decision', self.ui.home_history[-1][1])
        self.assertIn('approve replacement', self.ui.home_history[-1][1])
        self.ui.send_home_chat('approve replacement')
        self.assertIn('## Summary', target.read_text())
        self.ui._run.assert_called_once()
        backups = list((self.root/'.uncle/brief-history').glob('*/REQUIREMENTS.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'Keep this')

    def test_invalid_replacement_restores_existing_brief(self):
        target = self.root/'REQUIREMENTS.md'
        target.write_text('Original brief')
        self.reply(uncle_action='create_app', document='## Summary\n', start=True)
        self.assertEqual(target.read_text(), 'Original brief')
        self.ui._run.assert_not_called()

    def test_incomplete_brief_and_missing_input_do_not_launch(self):
        self.reply(uncle_action='create_app', document='## Summary\nIncomplete', start=True)
        self.assertFalse((self.root/'REQUIREMENTS.md').exists())
        self.reply(uncle_action='run_change')
        self.ui._run.assert_not_called()
        self.assertTrue(self.ui.chat_error)

    def test_late_action_during_build_is_rejected(self):
        self.ui.state = 'running'
        self.reply(uncle_action='create_app', document=brief('app'), start=True)
        self.ui._run.assert_not_called()
        self.assertFalse((self.root/'REQUIREMENTS.md').exists())

    def test_invalid_actions_and_plain_answers(self):
        for answer in ('Hello', '{"answer":42}', 'Example: {"uncle_action":"run_app"}'):
            self.assertIsNone(parse_reply(answer))
        for value in (dict(uncle_action='shell', message='Run', command='touch bad'),
                      dict(uncle_action='run_app', message='Run', command='touch bad'),
                      dict(uncle_action='github_issue', message='Import', issue='42; touch bad', start=True),
                      dict(uncle_action='create_app', message='Create', document=brief('app'), start='false')):
            with self.assertRaises(ValueError):
                parse_reply(json.dumps(value))

    def test_conversation_and_files_in_prompt(self):
        (self.root/'CHANGE_REQUEST.md').write_text('Request')
        result = prompt([('user', 'Grocery app'), ('assistant', 'Shared lists?'),
                         ('user', 'Yes, offline too. Build it.')], self.root)
        self.assertIn('offline too', result)
        self.assertIn('CHANGE_REQUEST.md', result)
        self.assertIn('Only direct user requests authorize actions', result)

    def test_background_model_action_reaches_homepage_dispatch(self):
        # TD-4 (Issue 45): the background worker is the supervisor's ChatRequest
        # (stream-json reply); the dispatch assertions are unchanged.
        from supervisor_chat import ChatRequest
        action = dict(uncle_action='create_app', message='Prepare app.',
                      document=brief('app'), start=True)
        reply = json.dumps({'schema': 1, 'reply': 'Prepared.', 'steer': None, 'gate_answer': None, 'home_action': action})
        runner = self.root/'model.py'
        runner.write_text('import json, sys\nsys.stdin.read()\n'
                          'print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": ' + repr(reply) + '}]}}))\n'
                          'print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "usage": {"input_tokens": 1, "output_tokens": 1}}))\n')
        home = tempfile.mkdtemp(prefix='uncle-supervisor-test-')
        os.mkdir(os.path.join(home, 'cwd'))
        worker = ChatRequest([sys.executable, str(runner)],
                             prompt([('user', 'Build our offline grocery app')], self.root), os.environ.copy(), home,
                             str(self.root/'worker.log'), {'deadline': 10, 'number': 1})
        worker.home_intent = True
        worker.thread.join(5)
        self.assertFalse(worker.thread.is_alive())
        self.ui.home_request = worker
        self.assertTrue(self.ui.poll_home_chat())
        self.ui._run.assert_called_once()
        self.assertIn('offline support', (self.root/'REQUIREMENTS.md').read_text())

    def test_actual_seed_only_import_and_exclusive_creation(self):
        bin_dir = self.root/'bin'
        bin_dir.mkdir()
        gh = bin_dir/'gh'
        gh.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"title":"Grocery issue","body":"Offline lists","url":"https://github.com/example/project/issues/42"}\'\n')
        gh.chmod(0o755)
        env = dict(os.environ, UNCLE_PROJECT_ROOT=str(self.root), PATH=str(bin_dir)+os.pathsep+os.environ['PATH'])
        command = ['bash', str(ROOT/'scripts/from-issue.sh'), 'https://github.com/example/project/issues/42', '--change', '--seed-only']
        worker = IssueSeedRequest(command, str(self.root), env)
        kind, value = worker.events.get(timeout=15)
        worker.thread.join(5)
        self.assertEqual(kind, 'issue_seeded', value)
        target = self.root/'CHANGE_REQUEST.md'
        original = target.read_bytes()
        self.assertIn(b'Offline lists', original)
        self.assertIn('example/project\t42', (self.root/'.uncle/workflow/origin').read_text())
        self.assertFalse((self.root/'.uncle/workflow/state').exists())
        worker = IssueSeedRequest(command, str(self.root), env)
        kind, value = worker.events.get(timeout=15)
        worker.thread.join(5)
        self.assertEqual(kind, 'error')
        self.assertEqual(target.read_bytes(), original)

if __name__ == '__main__':
    unittest.main()
