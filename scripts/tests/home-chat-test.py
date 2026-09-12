import os, sys, tempfile, unittest, queue
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import uncle_tui as tui
from home_chat import HomeRequest

class HomeTests(unittest.TestCase):
    def test_startup_homepage_sends_and_displays_reply(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / 'config'
            config.write_text('derive-brief.runner cline\nderive-brief.model cline-pass/test\nderive-brief.effort high\n')
            with patch.object(tui, '_project_root', return_value=d), patch.object(tui, 'CONFIG_PATH', str(config)), patch.object(tui, 'list_models', return_value=[]), patch.object(tui, 'default_model', return_value=''), patch.object(tui, 'read_keys', return_value={}), patch.object(tui, 'HomeRequest') as request:
                request.return_value.events = queue.Queue()
                ui = tui.UncleTUI(None)
                self.assertEqual(ui.state, 'menu')
                self.assertTrue(ui.chat_open)
                self.assertEqual(ui.chat_focus, 'menu')
                self.assertEqual(ui.sel, 0)
                self.assertTrue(ui.home_menu_open)
                ui.handle_key(9)
                self.assertEqual(ui.chat_focus, 'chat')
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
