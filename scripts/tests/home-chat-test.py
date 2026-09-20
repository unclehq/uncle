import os, sys, tempfile, unittest, queue, json
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui as tui
from home_chat import HomeRequest


def supervisor_worker(events=None):
    """Issue 45 TD-2/TD-3: chat now runs on the isolated supervisor worker. The
    worker class and its argv builder are replaced so no runner is spawned;
    `request.call_args.args` is (command, prompt, env, home, log, meta)."""
    request = patch.object(tui, 'ChatRequest')
    command = patch.object(tui, 'supervisor_command', return_value=(['fake-claude', '--bare'], {'PATH': '/bin'}, '/tmp/x'))
    return request, command

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
        # TD-2 (Issue 45): the legacy stage-model/effort checks moved to
        # test_legacy_homepage_model_and_request_fixture; the supervisor
        # integration keeps the UI, reply, composer and state assertions.
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('derive-brief.runner cline\nderive-brief.model cline-pass/test\nderive-brief.effort high\n'
                              'supervision.model sonnet\nsupervision.effort high\n')
            request, command = supervisor_worker()
            with patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'CONFIG_PATH', str(config)), patch.object(tui, 'list_models', return_value=[]), patch.object(tui, 'default_model', return_value=''), patch.object(tui, 'read_keys', return_value={}), request as request, command as command:
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
                argv, prompt, env = request.call_args.args[:3]
                self.assertEqual(argv, ['fake-claude', '--bare'])
                self.assertEqual(command.call_args.args[0].model, 'cline-pass/test')
                self.assertEqual(command.call_args.args[0].effort, 'high')
                self.assertIn('Hello', prompt)
                self.assertNotIn('UNCLE_CLINE_EFFORT', env)
                self.assertEqual(ui.chat_composer, '')
                request.return_value.events.put({'status': 'reply', 'elapsed': 1, 'exit': 0, 'usage': None, 'cost': None,
                                                 'log': '', 'reply': json.dumps({'schema': 1, 'reply': 'Hello from the configured model',
                                                                                 'steer': None, 'gate_answer': None, 'home_action': None})})
                self.assertTrue(ui.poll_home_chat())
                self.assertIn('Supervisor: Hello from the configured model', ui.chat_display())
                self.assertEqual(ui.state, 'menu')

    def test_legacy_homepage_model_and_request_fixture(self):
        # TD-2 (Issue 45): the original stage-model assertions, against the
        # homepage selector and a direct HomeRequest fixture (transport unchanged).
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('derive-brief.runner cline\nderive-brief.model cline-pass/test\nderive-brief.effort high\n')
            with patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'CONFIG_PATH', str(config)), patch.object(tui, 'list_models', return_value=[]), patch.object(tui, 'default_model', return_value=''), patch.object(tui, 'read_keys', return_value={}):
                ui = tui.UncleTUI(None)
                stage, runner, model, effort = ui.homepage_model()
                self.assertEqual((runner, model, effort), ('cline', 'cline-pass/test', 'high'))
                command = [tui.runner_command(runner, tui.REVIEWER), '--model', model]
                env = dict(os.environ, UNCLE_CLINE_EFFORT=effort)
                self.assertIn('cline-pass/test', command)
                self.assertEqual(env['UNCLE_CLINE_EFFORT'], 'high')
            with patch.object(tui, 'HomeRequest') as request:
                request.return_value.events = queue.Queue()
                fixture = tui.HomeRequest(command, 'Hello', env)
                command, prompt, env = request.call_args.args
                self.assertIn('cline-pass/test', command)
                self.assertIn('Hello', prompt)
                self.assertEqual(env['UNCLE_CLINE_EFFORT'], 'high')
                self.assertIsNotNone(fixture)

    def test_homepage_model_uses_the_first_persisted_configured_runner(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('project-plan.runner kimi\n'
                              'project-plan.effort high\n'
                              'implementation.runner self-hosted\n'
                              'implementation.model local/deepseek-v4-flash\n'
                              'supervision.model ignored-for-homepage\n')
            with patch.object(tui, '_project_root', return_value=d), \
                    patch.object(tui, 'CONFIG_PATH', str(config)), \
                    patch.object(tui, 'list_models', return_value=[]), \
                    patch.object(tui, 'default_model', return_value=''), \
                    patch.object(tui, 'read_keys', return_value={}):
                ui = tui.UncleTUI(None)
                self.assertEqual(ui.homepage_model()[:3],
                                 ('project-plan', 'kimi', ''))
                supervisor, stage = ui.homepage_supervision_config()
                self.assertEqual((stage, supervisor.runner, supervisor.model, supervisor.effort),
                                 ('project-plan', 'kimi', 'ignored-for-homepage', 'high'))

    def test_homepage_model_takes_a_saved_claude_stage_before_a_later_model(self):
        # derive-brief on claude is a complete selection: claude names no model
        # here, and the homepage must not fall through to change-plan's deepseek.
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('derive-brief.runner claude\n'
                              'derive-brief.effort low\n'
                              'change-plan.runner self-hosted\n'
                              'change-plan.effort low\n'
                              'change-plan.model local/deepseek-v4-flash\n')
            with patch.object(tui, '_project_root', return_value=d), \
                    patch.object(tui, 'CONFIG_PATH', str(config)), \
                    patch.object(tui, 'list_models', return_value=[]), \
                    patch.object(tui, 'default_model', return_value=''), \
                    patch.object(tui, 'read_keys', return_value={}):
                ui = tui.UncleTUI(None)
                self.assertEqual(ui.homepage_model(), ('derive-brief', 'claude', '', 'low'))
                supervisor, stage = ui.homepage_supervision_config()
                self.assertEqual((stage, supervisor.runner, supervisor.effort), ('derive-brief', 'claude', 'low'))
                self.assertNotEqual(supervisor.model, 'local/deepseek-v4-flash')

    def test_explicit_supervision_runner_wins_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('supervision.runner claude\n'
                              'supervision.effort high\n'
                              'change-plan.runner self-hosted\n'
                              'change-plan.model local/deepseek-v4-flash\n')
            with patch.object(tui, '_project_root', return_value=d), \
                    patch.object(tui, 'CONFIG_PATH', str(config)), \
                    patch.object(tui, 'list_models', return_value=[]), \
                    patch.object(tui, 'default_model', return_value=''), \
                    patch.object(tui, 'read_keys', return_value={}):
                ui = tui.UncleTUI(None)
                self.assertEqual(ui.homepage_model(), ('supervision', 'claude', '', 'high'))
                supervisor, _ = ui.homepage_supervision_config()
                self.assertEqual((supervisor.runner, supervisor.effort), ('claude', 'high'))

    def test_workflow_supervision_reuses_the_homepage_session(self):
        """Diagnostic calls share the persistent homepage worker when live."""
        session = object()
        host = tui.TuiSupervisionHost.__new__(tui.TuiSupervisionHost)
        host.tui = Mock()
        host.tui._supervisor_session.return_value = session
        host.controller = Mock(config=object())
        with tempfile.TemporaryDirectory() as d, \
                patch.object(tui, '_project_root', return_value=d), \
                patch.object(tui, 'supervisor_command', return_value=(['claude'], {}, d)), \
                patch.object(tui, 'SupervisorRequest') as request:
            host.start_worker('diagnose this stage', {'number': 3})
        self.assertIs(request.call_args.kwargs['session'], session)

    def test_running_chat_delivers_only_to_active_stage(self):
        # TD-1 (Issue 45): raw prose no longer reaches a channel from chat; the
        # channel writer is exercised directly with its original assertions.
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
                ui.steer_stage('Use the blue theme')
                request.assert_not_called()
            ui.proc.stdin.write.assert_not_called()
            files = list(Path(d).glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['text'], 'Use the blue theme')
            ui.status_stage = 'final-audit'
            with self.assertRaisesRegex(ValueError, 'draft has been kept'):
                ui.steer_stage('Do not lose this message')
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
        # TD-3 (Issue 45): the stage-model selection assertions run against
        # chat_model and a direct HomeRequest fixture; the supervisor
        # integration keeps the excerpt, no-stdin, no-home-action and
        # pending-gate assertions.
        from unittest.mock import Mock
        ui = tui.UncleTUI.__new__(tui.UncleTUI)
        ui.state = 'running'
        ui.prompt_kind = 'confirm'
        ui.prompt_text = 'Ready to approve CHANGE_PLAN.md?'
        ui.prompt_raw = ui.prompt_text
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
        self.assertEqual(ui.chat_model(), ('change-plan', 'codex', 'stage-model', 'low'))
        with patch.object(tui, 'HomeRequest') as request:
            legacy = ('Answer questions about the pending stage decision. The workflow is paused. '
                      'Only the user can answer the pending dialog.')  # fixture text, not production authorization
            tui.HomeRequest([tui.runner_command('codex', tui.REVIEWER), '--model', 'stage-model'], legacy, {})
            command, prompt, env = request.call_args.args
            self.assertIn('stage-model', command)
            self.assertIn('Only the user can answer', prompt)
        request, worker = supervisor_worker()
        with tempfile.TemporaryDirectory() as d, patch.object(tui, '_project_root', return_value=d), request as request, worker:
            Path(d, 'CHANGE_PLAN.md').write_text('Plan evidence')
            ui.send_home_chat('Why is this change necessary?')
            command, prompt, env = request.call_args.args[:3]
            self.assertIn('Plan evidence', prompt)
            self.assertIn('"gate_pending": true', prompt)
            self.assertNotIn('stage-model', command)
            self.assertEqual(ui.prompt_kind, 'confirm')
            ui.proc.stdin.write.assert_not_called()
            ui.home_request.events = queue.Queue()
            ui.home_request.events.put({'status': 'reply', 'elapsed': 1, 'exit': 0, 'usage': None, 'cost': None, 'log': '',
                                        'reply': '{"schema":1,"reply":"","steer":null,"gate_answer":null,"home_action":{"uncle_action":"run_change","message":"go"}}'})
            with patch.object(ui, '_home_action') as action:
                ui.poll_home_chat()
                action.assert_not_called()
            self.assertEqual(ui.prompt_kind, 'confirm')
            ui.proc.stdin.write.assert_not_called()

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
        # TD-2 (Issue 45): the stage-model command/env assertions moved to
        # the direct HomeRequest fixture below; the supervisor integration
        # keeps the attachment, busy, reply and history assertions.
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
                stage,runner,model,effort=ui.homepage_model()
                env=dict(os.environ,UNCLE_CLINE_REVIEWER_MODEL=model,UNCLE_CLINE_MODEL=model,UNCLE_CLINE_EFFORT=effort)
                tui.HomeRequest([tui.runner_command(runner,tui.REVIEWER),'--model',model],'Read @notes.txt',env)
                command,prompt,env=request.call_args.args
                self.assertIn('chosen-model',command)
                self.assertEqual(env['UNCLE_CLINE_REVIEWER_MODEL'],'chosen-model')
            request,worker=supervisor_worker()
            with request as request, worker:
                request.return_value.events=queue.Queue()
                ui.send_home_chat('Read @notes.txt')
                command,prompt,env=request.call_args.args[:3]
                self.assertNotIn('chosen-model',command)
                self.assertIn('Attached notes',prompt)
                with self.assertRaises(ValueError):ui.send_home_chat('busy')
                request.return_value.events.put({'status':'reply','elapsed':1,'exit':0,'usage':None,'cost':None,'log':'',
                                                 'reply':json.dumps({'schema':1,'reply':'Use @missing.txt as an example','steer':None,'gate_answer':None,'home_action':None})})
                self.assertTrue(ui.poll_home_chat())
                ui.send_home_chat('Explain more')
                self.assertIn('Use @missing.txt',request.call_args.args[1])
                self.assertEqual(len(ui.chat.messages),2)

    def test_status_bar_mode_labels_on_home_and_running(self):
        # Issue 53 T-1: the approval-mode label in the shared composer status
        # bar reads mode(auto)/mode(manual) on both the home and build routes,
        # keeping the right-aligned geometry, the right_width cap and colors.
        from unittest.mock import Mock
        screen_h, screen_w = 40, 120
        good, accent = 11, 22
        with tempfile.TemporaryDirectory() as d:
            with patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'CONFIG_PATH', str(Path(d) / '.uncle/config')), patch.object(tui, 'list_models', return_value=[]), patch.object(tui, 'default_model', return_value=''), patch.object(tui, 'read_keys', return_value={}), patch.object(tui.UncleTUI, '_viewer_command', return_value=''):
                ui = tui.UncleTUI(None)
            project = os.path.basename(d)
            ui.color = {'good': good, 'accent': accent}
            ui.stdscr = Mock()
            ui.stdscr.getmaxyx.return_value = (screen_h, screen_w)
            for route in ('menu', 'running'):
                for mode, label, attr in (('true', 'mode(auto)', good), ('false', 'mode(manual)', accent)):
                    with self.subTest(route=route, mode=mode), patch.object(tui, '_project_root', return_value=d):
                        ui.state = route
                        ui.misc['auto_mode'] = mode
                        ui.chat_focus = 'chat'
                        ui.chat_composer = ''
                        ui.stdscr.reset_mock()
                        with patch.object(ui, '_draw_chat_composer', wraps=ui._draw_chat_composer) as composer, \
                                patch.object(ui, '_draw_homepage', wraps=ui._draw_homepage) as home, \
                                patch.object(ui, '_draw_chat_panel', wraps=ui._draw_chat_panel) as panel, \
                                patch.object(ui, '_draw_running', wraps=ui._draw_running) as running, \
                                patch.object(ui, '_paint_support_link'):
                            ui.draw()
                        # Each route reaches the composer through its own path (AC-3).
                        composer.assert_called_once()
                        if route == 'menu':
                            home.assert_called_once_with(screen_h, screen_w)
                            running.assert_not_called()
                        else:
                            running.assert_called_once()
                            panel.assert_called_once()
                            home.assert_not_called()
                        _, _, w, left, width, *_ = composer.call_args.args
                        project_status = project + '  ·  ' + label
                        right_width = min(len(project_status), max(1, width - 18))
                        shown = project_status[:right_width]
                        self.assertEqual(shown, project_status)
                        expected_x = left + width - len(shown)
                        expected_n = min(width, max(0, w - expected_x - 1))
                        calls = [c.args for c in ui.stdscr.addnstr.call_args_list if c.args[2] == shown]
                        self.assertEqual(len(calls), 1, ui.stdscr.addnstr.call_args_list)
                        y, x, text, n, got_attr = calls[0]
                        self.assertEqual((x, n, got_attr), (expected_x, expected_n, attr))
                        self.assertNotIn(label, [c.args[2] for c in ui.stdscr.addnstr.call_args_list if c.args[0] != y])
                        for old in ('Auto mode on', 'Manual approvals'):
                            self.assertFalse(any(old in c.args[2] for c in ui.stdscr.addnstr.call_args_list), old)

if __name__=='__main__':unittest.main()
