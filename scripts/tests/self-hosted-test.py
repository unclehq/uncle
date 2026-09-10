#!/usr/bin/env python3
"""Self-hosted configuration, isolation and existing adapter contracts."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/lib'))
from self_hosted import read_keys, save_keys, settings, aider_invocation, run_aider, response_from_history, discover_models, refresh_models
from process_tree import bash_executable


class SelfHosted(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='self hosted test ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = self.root/'.uncle/config'
        self.config.parent.mkdir()
        self.config.write_text('implementation.runner self-hosted\nimplementation.model local-model:Q4\nimplementation.base_url http://localhost:8123/v1\n', encoding='utf-8')
        save_keys(self.config, {'implementation': 'secret-with-#-characters'})

    def test_config_and_secret_storage(self):
        with patch.dict(os.environ, {}, clear=True):
            values = settings(self.config, 'implementation-step-3')
        self.assertEqual(values['model'], 'local-model:Q4')
        self.assertEqual(values['api_key'], 'secret-with-#-characters')
        self.assertNotIn(values['api_key'], self.config.read_text(encoding='utf-8'))
        self.assertIn('/self-hosted-keys.json', (self.config.parent/'.gitignore').read_text(encoding='utf-8'))
        if os.name != 'nt':
            self.assertEqual((self.config.parent/'self-hosted-keys.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(values['base_url'], 'http://localhost:8123/v1')

    def test_env_overrides_and_validation(self):
        with patch.dict(os.environ, {'UNCLE_SELF_HOSTED_API_KEY':'env-key', 'UNCLE_SELF_HOSTED_MODEL':'other',
                                     'UNCLE_SELF_HOSTED_BASE_URL':'https://example.test/api/v1'}):
            self.assertEqual(settings(self.config, 'implementation')['api_key'], 'env-key')
            self.assertEqual(settings(self.config, 'implementation')['model'], 'other')
            for url in ('', 'file:///tmp/model', 'https://key@example.test/v1', 'https://example.test/v1?key=secret'):
                os.environ['UNCLE_SELF_HOSTED_BASE_URL'] = url
                if url:
                    with self.assertRaises(ValueError): settings(self.config, 'implementation')

    def test_named_connections_and_cli_selection(self):
        self.config.write_text('implementation.runner self-hosted\nimplementation.model qwen\nfinal-audit.runner self-hosted\nfinal-audit.model qwen\n', encoding='utf-8')
        profiles = {'qwen': {'base_url': 'http://localhost:9100/v1', 'api_key': 'named-secret'}}
        save_keys(self.config, {'__aider_models__': profiles})
        with patch.dict(os.environ, {}, clear=True):
            for stage in ('implementation-step-2', 'final-audit'):
                self.assertEqual(settings(self.config, stage), dict(model='qwen', **profiles['qwen']))
            profiles['qwen']['base_url'] = 'http://localhost:9200/v1'
            save_keys(self.config, {'__aider_models__': profiles})
            self.assertEqual(settings(self.config, 'final-audit')['base_url'], 'http://localhost:9200/v1')
            with self.assertRaises(ValueError):
                settings(self.config, 'requirements')
        for selection, success in (('qwen', True), ('cline-only-model', False)):
            result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/lib/self_hosted.py'),
                                     'choose-model', str(self.config)], input=selection+'\n',
                                    text=True,encoding='utf-8', capture_output=True)
            self.assertEqual(result.returncode == 0, success)
            self.assertNotIn('named-secret', result.stdout + result.stderr)
            if success:
                self.assertEqual(result.stdout.strip(), 'qwen')

    def test_discovery_and_failed_refresh_preserves_catalog(self):
        import io
        from urllib.error import HTTPError
        from unittest.mock import Mock
        opener = Mock()
        response = io.BytesIO(b'{"data":[{"id":"model-b"},{"id":"model-a"},{"id":"model-b"},{"id":"openai/model-a"}]}')
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            self.assertEqual(discover_models('http://localhost:1234/v1/', 'dummy-key'), ['openai/model-a','openai/model-b'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://localhost:1234/v1/models')
        self.assertEqual(request.get_header('Authorization'), 'Bearer dummy-key')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 10)
        keys = {'__aider_models__': {'old-model': self.values()}}
        before = json.dumps(keys)
        with patch('urllib.request.build_opener', return_value=opener):
            opener.open.side_effect = HTTPError('http://localhost', 401, 'private details', {}, None)
            with self.assertRaisesRegex(ValueError, 'HTTP 401'):
                refresh_models(keys, 'http://localhost:1234/v1', 'dummy-key')
        self.assertEqual(json.dumps(keys), before)
        with patch('self_hosted.discover_models', return_value=['new-model']):
            refresh_models(keys, 'http://localhost:1234/v1', 'dummy-key')
        self.assertEqual(list(keys['__aider_models__']), ['new-model'])

    def test_discovery_rejects_empty_malformed_and_redirects(self):
        import io
        from unittest.mock import Mock
        for raw in (b'{"data": []}', b'{}', b'not json', b'[]'):
            opener = Mock()
            opener.open.return_value = io.BytesIO(raw)
            with patch('urllib.request.build_opener', return_value=opener):
                with self.assertRaises(ValueError):
                    discover_models('http://localhost:1234/v1', 'dummy-key')
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"data":[{"id":"model"}]}')
        with patch('urllib.request.build_opener', return_value=opener) as build:
            discover_models('http://localhost:1234/v1', 'dummy-key')
        handler = build.call_args.args[0]
        self.assertIsNone(handler.redirect_request(None, None, 302, '', {}, 'https://elsewhere.test'))

    @patch("locale.getencoding", return_value="cp1252")
    def test_workflow_formatters_allow_missing_timing(self, _windows_encoding):
        import re
        import shutil
        if not shutil.which('jq'):
            self.skipTest('jq unavailable')
        for driver in ('stagegate.sh', 'change-workflow.sh'):
            source = (ROOT/'scripts'/driver).read_text(encoding='utf-8')
            formatter = re.search(r"format_claude_stream\(\) \{.*?\n\}", source, re.S).group()
            for duration in (None, 1500, 'invalid'):
                event = dict(type='result', subtype='success', num_turns=1, duration_ms=duration)
                result = subprocess.run([bash_executable(), '-c', formatter+'\nformat_claude_stream'],
                                        input=json.dumps(event)+'\n', capture_output=True, text=True,encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('1s' if duration == 1500 else 'time unknown', result.stdout)
                self.assertIn('—', result.stdout)

    def test_planning_edits_are_validated_before_publication(self):
        import self_hosted
        plan = self.root/'UPDATED_PROJECT_PLAN.md'
        plan.write_text('Original approved content\n')
        valid = '## Verification commands\n```bash\npython3 -m pytest\n```\n## Protected verification paths\n```text\ntests/\n```\n'
        for content in ('## Verification commands\n', '## Verification commands\n```bash\npytest', valid):
            def generate(side, values, prompt, staged, **kwargs):
                self.assertNotEqual(staged, self.root)
                (staged/'UPDATED_PROJECT_PLAN.md').write_text(content)
                (staged/'unwanted.py').write_text('incidental edit')
                return 'response', 1
            with patch.object(self_hosted, '_run_aider', side_effect=generate):
                if content != valid:
                    with self.assertRaises(ValueError):
                        run_aider('agent', self.values(), 'Plan', self.root, stage='updated-plan')
                    self.assertEqual(plan.read_text(encoding='utf-8'), 'Original approved content\n')
                else:
                    run_aider('agent', self.values(), 'Plan', self.root, stage='updated-plan')
                    self.assertEqual(plan.read_text(encoding='utf-8'), valid)
            self.assertFalse((self.root/'unwanted.py').exists())

    def test_plan_crash_and_missing_output_preserve_original(self):
        import self_hosted
        plan = self.root/'UPDATED_PROJECT_PLAN.md'
        plan.write_text('Original\n')
        with patch.object(self_hosted, '_run_aider', side_effect=ValueError('failed')):
            with self.assertRaises(ValueError):
                run_aider('agent', self.values(), 'Plan', self.root, stage='updated-plan')
        with patch.object(self_hosted, '_run_aider', return_value=('no edits', 1)):
            with self.assertRaises(ValueError):
                run_aider('agent', self.values(), 'Plan', self.root, stage='updated-plan')
        self.assertEqual(plan.read_text(encoding='utf-8'), 'Original\n')

    def test_exact_usage_sums_messages_without_console_rounding(self):
        from self_hosted import aider_usage
        path = self.root/'usage.jsonl'
        self.assertEqual(aider_usage(path), {})
        events = [dict(event='startup', properties={}),
                  dict(event='message_send', properties=dict(prompt_tokens=1234,completion_tokens=57)),
                  dict(event='message_send', properties=dict(prompt_tokens=2200,completion_tokens=91))]
        path.write_text('\n'.join(json.dumps(event) for event in events))
        self.assertEqual(aider_usage(path), dict(input_tokens=3434,output_tokens=148,total_tokens=3582))
        events.append(dict(event='message_send',properties={}))
        path.write_text('\n'.join(json.dumps(event) for event in events))
        self.assertEqual(aider_usage(path), {})

    def test_previously_selected_model_resolves_after_prefixed_refresh(self):
        save_keys(self.config, {'__aider_models__': {'openai/local-model:Q4': {k: v for k, v in self.values().items() if k != 'model'}}})
        with patch.dict(os.environ, {}, clear=True):
            values = settings(self.config, 'implementation')
        self.assertEqual(values['model'], 'openai/local-model:Q4')
        with tempfile.TemporaryDirectory() as directory:
            command, _ = aider_invocation('agent', values, 'test', self.root, directory)
        self.assertEqual(command[command.index('--model')+1], 'openai/local-model:Q4')

    def test_requirements_chat_response_is_saved_before_success(self):
        import self_hosted
        text = '# REQUIREMENTS_INTERPRETATION.md\n\n## 10. Definition of done\nPrint Hello World.\n'
        response = 'REQUIREMENTS_INTERPRETATION.md\n```markdown\n' + text + '```'
        with patch.object(self_hosted, '_run_aider', return_value=(response, 1)) as run:
            run_aider('agent', self.values(), 'Interpret', self.root, stage='requirements')
        self.assertEqual(run.call_args.args[0], 'reviewer')
        self.assertEqual((self.root/'REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8'), text)
        with patch.object(self_hosted, '_run_aider', return_value=('Done!', 1)):
            with self.assertRaises(ValueError):
                run_aider('agent', self.values(), 'Interpret', self.root, stage='requirements')
        self.assertEqual((self.root/'REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8'), text)

    def test_document_preamble_and_format_retry(self):
        import self_hosted
        text = '# REQUIREMENTS_INTERPRETATION.md\n\n## 10. Definition of done\nPrint Hello World.\n'
        wrapped = 'Here is the requested document:\n\n```markdown\n' + text + '```\nThat completes it.'
        self.assertEqual(self_hosted.document_response(wrapped, 'REQUIREMENTS_INTERPRETATION.md'), text)
        def generate(*args, **kwargs):
            kwargs['usage'].update(input_tokens=100, output_tokens=20, total_tokens=120)
            return responses.pop(0), 1
        responses = ['Done!', wrapped]
        usage = {}
        with patch.object(self_hosted, '_run_aider', side_effect=generate) as run:
            run_aider('agent', self.values(), 'Interpret', self.root, stage='requirements', usage=usage)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(usage['total_tokens'], 240)
        self.assertEqual((self.root/'REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8'), text)
        rejected = list((self.root/'.uncle/workflow/logs').glob('requirements-rejected-*.md'))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].read_text(encoding='utf-8'), 'Done!')

    def values(self):
        return {'api_key':'test-secret','model':'local-model:Q4','base_url':'http://localhost:8123/v1'}

    def test_aider_config_and_modes(self):
        for side in ('agent','reviewer'):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'OPENAI_API_KEY':'unrelated-key','OPENAI_API_BASE':'https://unrelated.test', 'AIDER_LOAD':'unwanted'}):
                command,env=aider_invocation(side,self.values(),'Test prompt',self.root,directory)
                for flag in ('--model','--weak-model','--editor-model'):
                    self.assertEqual(command[command.index(flag)+1],'openai/local-model:Q4')
                self.assertEqual(command[command.index('--openai-api-base')+1],self.values()['base_url'])
                self.assertEqual(env['OPENAI_API_KEY'],'test-secret')
                self.assertEqual(env['AIDER_OPENAI_API_KEY'],'test-secret')
                self.assertNotIn('AIDER_LOAD',env)
                self.assertNotIn('test-secret',str(command))
                self.assertNotIn('test-secret',Path(directory,'aider.yml').read_text(encoding='utf-8'))
                self.assertIn('--no-show-model-warnings',command)
                self.assertIn('--no-auto-commits',command)
                self.assertIn('--no-dirty-commits',command)
                if side=='reviewer':
                    self.assertEqual(command[command.index('--chat-mode')+1],'ask')
                    self.assertIn('--dry-run',command)
                    self.assertIn('--no-suggest-shell-commands',command)
                else:
                    self.assertEqual(command[command.index('--edit-format')+1],'diff')

    def stub_environment(self):
        stub=self.root/'fake_aider.py'
        stub.write_text("""import json,os,pathlib,sys,time
args=sys.argv[1:]
assert os.environ['OPENAI_API_KEY']=='secret-with-#-characters'
assert args[args.index('--openai-api-base')+1]=='http://localhost:8123/v1'
assert args[args.index('--model')+1]=='openai/local-model:Q4'
assert 'secret-with-#-characters' not in str(args)
prompt=pathlib.Path(args[args.index('--message-file')+1])
assert prompt.read_text(encoding='utf-8')=='Test prompt'
pathlib.Path(os.environ['RECORD']).write_text(str(prompt.parent),encoding='utf-8')
pathlib.Path(args[args.index('--analytics-log')+1]).write_text(json.dumps(dict(event='message_send', properties=dict(prompt_tokens=1234,completion_tokens=57)))+'\\n',encoding='utf-8')
mode=os.environ.get('FAKE_AIDER_MODE','ok')
if mode=='timeout': time.sleep(30)
if mode!='empty':
    pathlib.Path(args[args.index('--llm-history-file')+1]).write_bytes(b'TO LLM 2026-09-09T12:00:00\\nUSER Test prompt\\nLLM RESPONSE 2026-09-09T12:00:01\\nASSISTANT ## Findings\\nASSISTANT \\nASSISTANT NOT READY\\n')
print('Aider banner and costs should not become the report')
sys.exit(7 if mode=='fail' else 0)
""",encoding='utf-8')
        wrapper=self.root/'fake-aider'
        wrapper.write_bytes(b'#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$TEST_STUB" "$@"\n')
        wrapper.chmod(0o755)
        return dict(os.environ, WORKFLOW_AIDER_CMD=str(wrapper), TEST_PYTHON=sys.executable, TEST_STUB=str(stub),
                    UNCLE_CONFIG=str(self.config),UNCLE_STATUS_STAGE='implementation',RECORD=str(self.root/'record'))

    def test_both_adapters_preserve_response_and_cleanup(self):
        env=self.stub_environment()
        for side in ('agent','reviewer'):
            with self.subTest(side=side):
                out=self.root/'report.md'
                command=[bash_executable(),(ROOT/f'scripts/{side}-self-hosted.sh').as_posix()]
                command+=['-p','--model','opus'] if side=='agent' else ['exec','--output-last-message',str(out),'Test prompt']
                result=subprocess.run(command,input='Test prompt' if side=='agent' else '',text=True,encoding='utf-8',
                                      env=env,cwd=self.root,capture_output=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertNotIn('Aider banner',result.stdout)
                self.assertNotIn('secret-with-#-characters',result.stdout+result.stderr)
                self.assertFalse(Path((self.root/'record').read_text(encoding='utf-8')).exists())
                if side=='reviewer':
                    self.assertIn('tokens used\n1291', result.stdout)
                    self.assertEqual(out.read_bytes(),b'## Findings\n\nNOT READY\n')
                else:
                    final=json.loads(result.stdout.splitlines()[-1])
                    self.assertEqual(final['usage'], dict(input_tokens=1234,output_tokens=57,total_tokens=1291))
                    self.assertFalse(final['is_error'])
                    self.assertIsInstance(final['duration_ms'], int)
                    self.assertGreaterEqual(final['duration_ms'], 0)
                    self.assertEqual(final['result'],'## Findings\n\nNOT READY')
                    self.assertIsNone(final['total_cost_usd'])

    def test_failures_never_write_a_review(self):
        env=self.stub_environment()
        for mode in ('fail','empty','timeout'):
            with self.subTest(mode=mode):
                out=self.root/(mode+'.md')
                env.update(FAKE_AIDER_MODE=mode,WORKFLOW_SELF_HOSTED_SECONDS='1')
                result=subprocess.run([bash_executable(),(ROOT/'scripts/reviewer-self-hosted.sh').as_posix(),
                    'exec','--output-last-message',str(out),'Test prompt'],env=env,cwd=self.root,
                    text=True,encoding='utf-8',capture_output=True,timeout=10)
                self.assertNotEqual(result.returncode,0,result.stdout)
                failure = json.loads(result.stdout.splitlines()[-1])
                self.assertTrue(failure['error_detail'])
                self.assertIsInstance(failure['duration_ms'], int)
                if mode != 'empty':
                    self.assertIn('diagnostic log:', failure['error_detail'])
                diagnostics = list((self.root/'.uncle/workflow/logs').glob('aider-failure-*.log'))
                self.assertTrue(diagnostics)
                for log in diagnostics:
                    self.assertNotIn('secret-with-#-characters', log.read_text(encoding='utf-8'))
                self.assertFalse(out.exists())
                self.assertFalse(Path((self.root/'record').read_text(encoding='utf-8')).exists())

    def test_history_uses_last_response_preserving_markdown(self):
        path=self.root/'llm.log'
        path.write_bytes(b'LLM RESPONSE 2026-09-09T12:00:00\r\nASSISTANT old\r\nTO LLM 2026-09-09T12:01:00\r\nUSER question\r\nLLM RESPONSE 2026-09-09T12:01:01\r\nASSISTANT ## Final\r\nASSISTANT | A | B |\r\n')
        self.assertEqual(response_from_history(path),('## Final\n| A | B |',2))
        path.write_bytes(b'LLM RESPONSE 2026-09-09T12:00:00\n')
        with self.assertRaises(ValueError): response_from_history(path)

    def test_stage_dispatch(self):
        for side, stage in (('agent','implementation'),('reviewer','final-audit')):
            result = subprocess.run([bash_executable(), '-c',
                '. "$1/scripts/lib/stage-config.sh"; ROOT="$1"; uncle_runner_cmd self-hosted "$2"',
                '_',ROOT.as_posix(),side],capture_output=True,text=True,encoding='utf-8',check=True)
            self.assertTrue(result.stdout.endswith(f'{side}-self-hosted.sh'))

    def test_tui_roundtrip_and_masking(self):
        try:
            import curses
        except ImportError:
            self.skipTest('curses unavailable')
        spec=importlib.util.spec_from_file_location('self_hosted_tui',ROOT/'uncle_tui.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module,'CONFIG_PATH',str(self.config)):
            ui=module.UncleTUI.__new__(module.UncleTUI)
            ui.load_config()
            self.assertEqual(ui._config_items(), ['1. Configure stages', '2. Configure Aider / self hosting', '3. Miscellaneous'])
            ui.config_section = 'misc'
            with patch.object(ui, 'maybe_reload'):
                ui._set_field('!misc', 'auto_mode', 'true')
                ui._set_field('!misc', 'approval_name', 'Test Reviewer')
            ui.load_config()
            self.assertEqual(ui.misc, dict(auto_mode='true', approval_name='Test Reviewer'))
            self.assertEqual(ui.stage_env()['UNCLE_APPROVAL_NAME'], 'Test Reviewer')
            for index in range(len(module.WORKFLOWS)):
                ui.workflow_idx = index
                ui.issue, ui.issue_mode = '123', '--change'
                self.assertIn('--unattended', ui.cmd_for())
            from unittest.mock import Mock
            ui.stdscr = Mock()
            ui.color = {'title': 1}
            ui._draw_logo(60, 160)
            ui.stdscr.addnstr.assert_any_call(len(module.LOGO), (module.LOGO_W-5)//2, 'uncle', 5, 1)
            ui.config_section = 'stages'
            self.assertEqual(len(ui._config_items()), len(module.CONFIG_STAGES))
            ui.config_section = 'aider'
            self.assertIn('1 loaded', ui._config_items()[1])
            self.assertEqual(ui.stage_fields('implementation'),['runner','model'])
            self.assertEqual(ui._field_display('@local-model:Q4','api_key'),'********')
            ui.save_config()
            ui.load_config()
            self.assertEqual(ui.stage_model('implementation'),'local-model:Q4')
            self.assertEqual(ui.stage_api_keys['__aider_models__']['local-model:Q4']['base_url'],'http://localhost:8123/v1')
            self.assertEqual(read_keys(self.config)['__aider_models__']['local-model:Q4']['api_key'],'secret-with-#-characters')
            ui._open_picker('model','implementation')
            self.assertEqual(ui.state,'picker')
            self.assertEqual(ui._picker_rows(), [('option', 'local-model:Q4')])
            ui._open_stage('@connection')
            self.assertEqual(ui.stage_fields('@connection'), ['base_url', 'api_key'])
            with patch.object(ui, 'maybe_reload'), patch('self_hosted.discover_models', return_value=['local-model:Q4', 'second-model']):
                ui._set_field('@connection', 'api_key', 'secret-with-#-characters')
            ui._open_picker('model', 'implementation')
            self.assertEqual(ui._picker_rows(), [('option', 'local-model:Q4'), ('option', 'second-model')])
            self.assertNotIn('second-secret', str(ui._config_items()))
            self.assertNotIn('second-secret', self.config.read_text(encoding='utf-8'))
            ui.stage_target = 'implementation'
            with patch.object(ui, 'maybe_reload'):
                ui._apply_aider_to_all_stages()
            ui.load_config()
            for stage in module.CONFIG_STAGES:
                self.assertEqual(ui.stage_runner(stage), 'self-hosted')
                with patch.dict(os.environ, {}, clear=True):
                    connection = settings(self.config, stage)
                self.assertEqual(connection['model'], 'local-model:Q4')
                self.assertEqual(connection['base_url'], 'http://localhost:8123/v1')
                self.assertEqual(connection['api_key'], 'secret-with-#-characters')


if __name__ == '__main__':
    unittest.main()
