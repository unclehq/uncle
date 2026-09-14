import os, sys, tempfile, unittest, queue, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui as tui
from home_chat import HomeRequest

class HomeTests(unittest.TestCase):
    def test_first_launch_opens_home_without_configuration_or_viewer(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'CONFIG_PATH', str(Path(d) / '.uncle/config')), patch.object(tui, 'list_models', return_value=[]), patch.object(tui, 'default_model', return_value=''), patch.object(tui, 'read_keys', return_value={}), patch.object(tui.UncleTUI, '_viewer_command', return_value=''):
                ui = tui.UncleTUI(None)
                self.assertTrue(ui.first_run)
                self.assertEqual(ui.state, 'menu')
                self.assertTrue(ui.chat_open)
                self.assertEqual(ui.chat_focus, 'chat')
                self.assertEqual(ui.sel, 0)
                self.assertFalse(ui.home_menu_open)

    def test_startup_homepage_sends_and_displays_reply(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('derive-brief.runner cline\nderive-brief.model cline-pass/test\nderive-brief.effort high\n')
            with patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'CONFIG_PATH', str(config)), patch.object(tui, 'list_models', return_value=[]), patch.object(tui, 'default_model', return_value=''), patch.object(tui, 'read_keys', return_value={}), patch.object(tui, 'HomeRequest') as request:
                request.return_value.events = queue.Queue()
                ui = tui.UncleTUI(None)
                self.assertEqual(ui.state, 'menu')
                self.assertTrue(ui.chat_open)
                self.assertEqual(ui.chat_focus, 'chat')
                self.assertEqual(ui.sel, 0)
                self.assertFalse(ui.home_menu_open)
                request.assert_not_called()
                for char in 'Hello':
                    ui.handle_key(ord(char))
                ui.handle_key(10)
                command, prompt, env = request.call_args.args
                self.assertIn('cline-pass/test', command)
                self.assertIn('Hello', prompt)
                self.assertEqual(env['UNCLE_CLINE_EFFORT'], 'high')
                self.assertEqual(ui.chat_composer, '')
                request.return_value.events.put(('reply', 'Hello from the configured model'))
                self.assertTrue(ui.poll_home_chat())
                self.assertIn('Assistant: Hello from the configured model', ui.chat_display())
                self.assertEqual(ui.state, 'menu')

    def test_running_chat_delivers_only_to_active_stage(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            ui = tui.UncleTUI.__new__(tui.UncleTUI)
            ui.state = 'running'
            ui.status_stage = 'implementation'
            ui.steering_channels = {'implementation': d}
            ui.proc = Mock()
            ui.proc.poll.return_value = None
            ui.chat = Mock()
            ui.chat.refs.expand.side_effect = lambda text: text
            ui.home_history = []
            with patch.object(tui, 'HomeRequest') as request:
                ui.send_home_chat('Use the blue theme')
                request.assert_not_called()
            ui.proc.stdin.write.assert_not_called()
            files = list(Path(d).glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['text'], 'Use the blue theme')
            ui.status_stage = 'final-audit'
            with self.assertRaisesRegex(ValueError, 'draft has been kept'):
                ui.send_home_chat('Do not lose this message')
            self.assertEqual(len(list(Path(d).glob('*.json'))), 1)

    def test_pending_dialog_stays_visible_with_chat_focus(self):
        from unittest.mock import Mock
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state = 'running'
        ui.prompt_kind = 'confirm'
        ui.chat_focus = 'chat'
        ui.partial = ''
        ui._build_messages = Mock(return_value=['Latest build output'])
        ui._draw_modal = Mock()
        ui.stdscr = Mock()
        ui.stdscr.getmaxyx.return_value = (40, 120)
        ui._draw_running(25, 90)
        ui._draw_modal.assert_called_once_with(25, 90)
        self.assertEqual(ui.chat_focus, 'chat')
        self.assertEqual(ui.prompt_kind, 'confirm')

    def test_pending_gate_questions_preserve_approval_and_use_stage_model(self):
        from unittest.mock import Mock
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state = 'running'
        ui.prompt_kind = 'confirm'
        ui.prompt_text = 'Ready to approve CHANGE_PLAN.md?'
        ui.gate_file = 'CHANGE_PLAN.md'
        ui.status_stage = 'change-plan'
        ui.steering_channels = {'change-plan': '/stale-channel-from-completed-stage'}
        ui.proc = Mock()
        ui.proc.poll.return_value = None
        ui.home_request = None
        ui.home_history = []
        ui.chat = Mock()
        ui.chat.refs.expand.side_effect = lambda value: value
        ui.chat_model = lambda: ('change-plan', 'codex', 'stage-model', 'low')
        with tempfile.TemporaryDirectory() as d, patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'HomeRequest') as request:
            Path(d, 'CHANGE_PLAN.md').write_text('Plan evidence')
            ui.send_home_chat('Why is this change necessary?')
            command, prompt, env = request.call_args.args
            self.assertIn('stage-model', command)
            self.assertIn('Plan evidence', prompt)
            self.assertIn('Only the user can answer', prompt)
            self.assertEqual(ui.prompt_kind, 'confirm')
            ui.proc.stdin.write.assert_not_called()
            ui.home_request.events = queue.Queue()
            ui.home_request.events.put(('reply', '{"uncle_action":"run_change"}'))
            with patch.object(ui, '_home_action') as action:
                ui.poll_home_chat()
                action.assert_not_called()
            self.assertEqual(ui.prompt_kind, 'confirm')

    def test_running_chat_tracks_live_stage_model(self):
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state = 'running'
        ui.stage_runner = lambda stage: 'cline'
        ui.stage_model = lambda stage: 'configured/' + stage
        ui.stage_effort = lambda stage: 'medium'
        ui.status_stage = 'implementation-step-2'
        ui.status_runner = 'codex'
        ui.status_model = 'live-model'
        ui.status_effort = 'high'
        self.assertEqual(ui.chat_model(), ('implementation', 'codex', 'live-model', 'high'))
        ui.status_stage = 'final-audit'
        ui.status_runner = 'cline'
        ui.status_model = 'audit-model'
        self.assertEqual(ui.chat_model(), ('final-audit', 'cline', 'audit-model', 'high'))
        ui.status_stage = ''
        self.assertEqual(ui.chat_model(), ('', '', '', ''))

    def test_background_reply_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            script=Path(d)/'fake.py'
            script.write_text("import sys; from pathlib import Path; Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('Hello')")
            request=HomeRequest([sys.executable,str(script)],'hello',os.environ.copy())
            self.assertEqual(request.events.get(timeout=5),('reply','Hello'))
            request.thread.join(5)
            self.assertFalse(request.thread.is_alive())
            request=HomeRequest([sys.executable,'-c','raise SystemExit(2)'],'hello',os.environ.copy())
            self.assertEqual(request.events.get(timeout=5)[0],'error')
            request.thread.join(5)
    def test_background_chat_reads_launch_directory_and_keeps_reply_temporary(self):
        with tempfile.TemporaryDirectory(prefix='chat project ') as d:
            root = Path(d)
            (root/'local.txt').write_text('project file contents')
            script = root/'fake.py'
            script.write_text("import sys; from pathlib import Path; "
                              "reply=Path(sys.argv[sys.argv.index('--output-last-message')+1]); "
                              "assert reply.parent != Path.cwd(); "
                              "reply.write_text(Path('local.txt').read_text())")
            request = HomeRequest([sys.executable, str(script)], 'Read local.txt', os.environ.copy(), cwd=d)
            self.assertEqual(request.events.get(timeout=5), ('reply', 'project file contents'))
            request.thread.join(5)
            self.assertFalse((root/'reply.txt').exists())
            self.assertFalse(request.thread.is_alive())
    def test_cancel(self):
        request=HomeRequest([sys.executable,'-c','import time; time.sleep(30)'],'hello',os.environ.copy())
        request.cancel()
        self.assertEqual(request.events.get(timeout=5)[0],'error')
        request.thread.join(5)
        self.assertFalse(request.thread.is_alive())
    def test_selection_context_and_busy(self):
        with tempfile.TemporaryDirectory() as d, patch.object(tui,'_project_root',return_value=d):
            Path(d,'notes.txt').write_text('Attached notes')
            ui=tui.UncleTUI.__new__(tui.UncleTUI)
            ui._ensure_chat()
            ui.state = 'menu'
            ui.stage_runner=lambda stage:'cline'
            ui.stage_model=lambda stage:'chosen-model'
            ui.stage_effort=lambda stage:'high'
            self.assertEqual(ui.homepage_model(),(tui.CONFIG_STAGES[0],'cline','chosen-model','high'))
            with patch.object(tui,'HomeRequest') as request:
                request.return_value.events=queue.Queue()
                ui.send_home_chat('Read @notes.txt')
                command,prompt,env=request.call_args.args
                self.assertIn('chosen-model',command)
                self.assertIn('Attached notes',prompt)
                self.assertEqual(env['UNCLE_CLINE_REVIEWER_MODEL'],'chosen-model')
                with self.assertRaises(ValueError):ui.send_home_chat('busy')
                request.return_value.events.put(('reply','Use @missing.txt as an example'))
                self.assertTrue(ui.poll_home_chat())
                ui.send_home_chat('Explain more')
                self.assertIn('Use @missing.txt',request.call_args.args[1])
                self.assertEqual(len(ui.chat.messages),2)

if __name__=='__main__':unittest.main()
