import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import github_issues as issues
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class Issues(unittest.TestCase):
    def test_github_origin_formats_and_non_github(self):
        for remote in ('git@github.com:owner/project.git','https://github.com/owner/project.git',
                       'ssh://git@github.com/owner/project', 'https://github.com/owner/project/'):
            with self.subTest(remote=remote), patch.object(issues.subprocess,'run',return_value=Mock(returncode=0,stdout=remote)):
                self.assertEqual(issues.repository('/project'),'owner/project')
        for remote in ('https://other.example/owner/project', '/local/repo', 'git@github.com:owner/project.git;bad'):
            with patch.object(issues.subprocess,'run',return_value=Mock(returncode=0,stdout=remote)):
                self.assertIsNone(issues.repository('/project'))

    def test_only_open_issues_across_pages_and_no_prs(self):
        pages=[[{'number':1,'title':'open','state':'open'}, {'number':2,'title':'closed','state':'closed'}],
               [{'number':3,'title':'PR','state':'open','pull_request':{}},
                {'number':4,'title':'Another\nissue','state':'open'}]]
        with patch.object(issues,'gh',return_value=pages) as gh:
            found=issues.open_issues('/project','owner/repo')
        self.assertEqual([i['number'] for i in found],[4,1])
        self.assertEqual(found[0]['title'],'Another issue')
        self.assertIn('state=open',gh.call_args.args[1][-1])
        self.assertIn('--paginate',gh.call_args.args[1])

    def test_number_resolution_and_context(self):
        self.assertEqual(issues.references('Compare #12 with issue 45 and #12'),[12,45])
        self.assertEqual(issues.references('123'),[123])
        self.assertEqual(issues.references('color #abc URL/#12 x#23'),[])
        with patch.object(issues,'repository',return_value='owner/repo'), patch.object(issues,'gh',return_value={
            'number':12,'title':'Bug','body':'Details','state':'OPEN'}) as gh:
            context=issues.issue_context('/project','explain #12')
        self.assertIn('https://github.com/owner/repo/issues/12',context)
        self.assertIn('Details',context)
        self.assertIn('external reference data',context)
        self.assertIn('owner/repo',gh.call_args.args[1])

    def test_missing_repo_does_not_call_github(self):
        with patch.object(issues,'repository',return_value=None), patch.object(issues,'gh') as gh:
            self.assertEqual(issues.issue_context('/project','#12'),'')
            gh.assert_not_called()

    def test_picker_result_delivery_filtering_and_errors(self):
        picker=issues.IssuePicker('/project')
        picker.loading=True
        picker.events.put(('owner/repo',[{'number':12,'title':'Fix window'}, {'number':42,'title':'Tests'}],''))
        self.assertTrue(picker.poll())
        self.assertFalse(picker.loading)
        self.assertEqual(picker.matches('window')[0]['number'],12)
        self.assertEqual(picker.matches('42')[0]['title'],'Tests')
        self.assertEqual(picker.matches('missing'),[])
        with patch.object(issues.subprocess,'run',side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError,'Install GitHub CLI'): issues.gh('/project',[])
        with patch.object(issues.subprocess,'run',side_effect=subprocess.TimeoutExpired('gh',30)):
            with self.assertRaisesRegex(ValueError,'timed out'): issues.gh('/project',[])

    def test_home_request_receives_issue_context_and_keeps_lookup_errors_local(self):
        from home_chat import HomeRequest
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'reply.py'
            script.write_text("import sys; from pathlib import Path; assert 'Issue title and body' in sys.argv[-1]; Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('Issue answer')")
            request = HomeRequest([sys.executable, str(script)], 'Explain #12', os.environ.copy(),
                                  issue_lookup=lambda: 'Issue title and body')
            self.assertEqual(request.events.get(timeout=5), ('reply', 'Issue answer'))
            request.thread.join(5)
            self.assertEqual(request.issue_context, 'Issue title and body')
            with patch('home_chat.start_check') as launch:
                request = HomeRequest([], 'Explain #12', os.environ.copy(),
                                      issue_lookup=Mock(side_effect=ValueError('GitHub unavailable')))
                self.assertEqual(request.events.get(timeout=5), ('error', 'GitHub unavailable'))
                request.thread.join(5)
                launch.assert_not_called()

    def test_homepage_issue_lookup_is_passed_and_retained_for_followup(self):
        import uncle_tui as tui
        with tempfile.TemporaryDirectory() as root, patch.object(tui,'_project_root',return_value=root):
            ui=tui.UncleTUI.__new__(tui.UncleTUI)
            ui.state='menu';ui._ensure_chat()
            ui.chat_model=lambda: ('baseline','cline','model','medium')
            # TD-4 (Issue 45): the chat worker is the supervisor's ChatRequest; assertions unchanged.
            with patch.object(tui,'ChatRequest') as request, patch.object(tui,'supervisor_command',return_value=(['fake-claude'],{},'/tmp/x')), patch.object(tui,'issue_context',return_value='Issue reference data') as lookup:
                ui.send_home_chat('Explain #12')
                self.assertEqual(request.call_args.kwargs['issue_lookup'](), 'Issue reference data')
                lookup.assert_called_once_with(root,'Explain #12')
                request.return_value.issue_context='Issue reference data'
                request.return_value.events=issues.queue.Queue()
                request.return_value.events.put({'status':'reply','elapsed':0,'exit':0,'usage':None,'cost':None,'log':'',
                                                 'reply':'{"schema":1,"reply":"Answer","steer":null,"gate_answer":null,"home_action":null}'})
                ui.poll_home_chat()
                self.assertNotIn('Issue reference data','\n'.join(ui.chat_display()))
                ui.send_home_chat('What is the next step?')
                self.assertIn('Issue reference data',request.call_args.args[1])

    def test_ui_picker_tab_enter_escape_and_loading(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
        import uncle_tui as tui
        with tempfile.TemporaryDirectory() as root, patch.object(tui,'_project_root',return_value=root):
            ui=tui.UncleTUI.__new__(tui.UncleTUI)
            ui.state='menu';ui.proc=None
            ui._ensure_chat()
            ui.issue_picker=issues.IssuePicker(root)
            ui.issue_picker.load=Mock()
            ui.issue_picker.items=[{'number':12,'title':'Fix window'},{'number':42,'title':'Tests'}]
            ui.chat_composer='Please explain #'
            ui._chat_suggestions()
            self.assertEqual(len(ui.chat_choices),2)
            ui.handle_key(tui.curses.KEY_DOWN)
            ui.handle_key(9)
            self.assertEqual(ui.chat_composer,'Please explain #42 ')
            self.assertFalse(ui.chat_picker)
            self.assertFalse(ui.chat.messages)
            ui.chat_composer='#window';ui._chat_suggestions();ui.handle_key(10)
            self.assertEqual(ui.chat_composer,'#12 ')
            ui.chat_composer='#';ui._chat_suggestions();ui.handle_key(27)
            self.assertFalse(ui.chat_picker)
            # A late lookup must not reopen a dismissed picker.
            ui.issue_picker.events.put(('owner/repo',[],''));ui.poll_issue_picker()
            self.assertFalse(ui.chat_picker)
            ui.chat_composer='#';ui.issue_picker.items=[];ui.issue_picker.message='Loading open GitHub issues…'
            ui._chat_suggestions();ui.handle_key(10)
            self.assertIn('Loading',ui.chat_error)
            self.assertFalse(ui.chat.messages)

    def test_slash_command_hash_argument_wins_over_the_issue_picker(self):
        """A #N in ordinary text opens the picker; the same #N as a slash
        command's own argument (`/resume #N`, `/clear #N`) must still reach
        the command, not be swallowed as an issue mention to confirm."""
        import uncle_tui as tui
        with tempfile.TemporaryDirectory() as root, patch.object(tui,'_project_root',return_value=root):
            ui=tui.UncleTUI.__new__(tui.UncleTUI)
            ui.state='menu';ui.proc=None
            ui._ensure_chat()
            ui.issue_picker=issues.IssuePicker(root)
            ui.issue_picker.load=Mock()
            ui.issue_picker.items=[{'number':69,'title':'Some issue'}]
            ui._resume_build=Mock(return_value='resumed!')
            ui._clear_build=Mock(return_value='cleared!')
            ui.send_home_chat=Mock()
            ui.chat_composer='/resume #69'
            ui._chat_suggestions()
            self.assertTrue(ui.chat_picker, 'the #N still opens the picker while typing')
            ui.handle_key(10)
            ui._resume_build.assert_called_once_with('#69')
            ui.send_home_chat.assert_not_called()
            self.assertEqual(ui.chat_composer,'')
            ui.chat_composer='/clear #69'
            ui._chat_suggestions()
            ui.handle_key(10)
            ui._clear_build.assert_called_once_with('#69')
            ui.send_home_chat.assert_not_called()
            # Ordinary text mentioning an issue is unaffected: it still goes
            # through the picker's own confirm-and-send path.
            ui.chat_composer='fix #69 please'
            ui._chat_suggestions()
            ui.handle_key(10)
            ui.send_home_chat.assert_called_once_with('fix #69 please')


if __name__=='__main__': unittest.main()
