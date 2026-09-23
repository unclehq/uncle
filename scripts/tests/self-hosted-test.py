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
from self_hosted import read_keys, save_keys, settings, opencode_invocation, run_opencode, response_from_events, discover_models, refresh_models, parse_arguments, reviewer_document
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
        save_keys(self.config, {'__opencode_models__': profiles})
        with patch.dict(os.environ, {}, clear=True):
            self.config.write_text(self.config.read_text(encoding='utf-8') +
                                   'execute-checklist.runner self-hosted\nexecute-checklist.model qwen\n', encoding='utf-8')
            for stage in ('implementation-step-2', 'execute-checklist-worker-MC-001', 'final-audit'):
                self.assertEqual(settings(self.config, stage), dict(model='qwen', **profiles['qwen']))
            profiles['qwen']['base_url'] = 'http://localhost:9200/v1'
            save_keys(self.config, {'__opencode_models__': profiles})
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
                self.assertEqual(result.stdout.strip(), 'local/qwen')

    def test_review_workers_inherit_the_parent_stage_configuration(self):
        parents = ('adversarial-review', 'updated-plan', 'updated-change-plan',
                   'final-audit', 'manual-checklist')
        self.config.write_text(''.join('%s.runner self-hosted\n%s.model deepseek\n' % (stage, stage)
                                       for stage in parents), encoding='utf-8')
        profile = {'base_url': 'http://localhost:9100/v1', 'api_key': 'deepseek-secret'}
        save_keys(self.config, {'__opencode_models__': {'deepseek': profile}})
        with patch.dict(os.environ, {}, clear=True):
            for parent in parents:
                # Every review-panel worker must consume the parent stage's
                # runner/model, never an invented "*-review" config stage.
                self.assertEqual(settings(self.config, parent + '-review-worker-probe'),
                                 dict(model='deepseek', **profile))

    def test_shell_runner_mapping_matches_every_worker_family(self):
        workers_and_parents = (
            ('adversarial-review-worker-security', 'adversarial-review'),
            ('test-review-worker-coverage', 'test-review'),
            ('updated-plan-review-worker-scope', 'updated-plan'),
            ('updated-change-plan-review-worker-scope', 'updated-change-plan'),
            ('manual-checklist-review-worker-base-coverage', 'manual-checklist'),
            ('final-audit-review-worker-verification', 'final-audit'),
            ('execute-checklist-worker-batch-1', 'execute-checklist'),
            ('implementation-step-3', 'implementation'),
            ('implementation-report', 'implementation'),
        )
        parents = tuple(dict.fromkeys(parent for _worker, parent in workers_and_parents))
        self.config.write_text(''.join('%s.runner self-hosted\n%s.model local/deepseek-v4-flash\n' % (stage, stage)
                                       for stage in parents), encoding='utf-8')
        script = '''
source "$ROOT/scripts/lib/stage-config.sh"
for stage in "$@"; do
    runner="$(uncle_stage_runner "$stage")"
    printf '%s=%s:%s:%s:%s\\n' "$stage" "$(uncle_config_stage "$stage")" "$runner" \\
        "$(uncle_stage_model "$stage" "$runner")" "$(uncle_stage_effort "$stage")"
done
'''
        result = subprocess.run([bash_executable(), '-c', script, 'workers', *(worker for worker, _parent in workers_and_parents)],
                                env=dict(os.environ, ROOT=str(ROOT), UNCLE_CONFIG=str(self.config)),
                                text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for worker, parent in workers_and_parents:
            self.assertIn('%s=%s:self-hosted:local/deepseek-v4-flash:none' % (worker, parent), result.stdout)

    def test_every_runner_inherits_every_dynamic_stage_parent(self):
        script = '''
source "$ROOT/scripts/lib/stage-config.sh"
stage="$1"
printf '%s:%s:%s\\n' "$(uncle_stage_runner "$stage")" "$(uncle_stage_side "$stage")" "$(uncle_stage_cmd "$stage")"
'''
        review_workers = ('adversarial-review-worker-probe', 'test-review-worker-probe',
                          'updated-plan-review-worker-probe',
                          'updated-change-plan-review-worker-probe',
                          'final-audit-review-worker-probe',
                          'manual-checklist-review-worker-probe')
        dynamic_stages = review_workers + ('execute-checklist-worker-MC-001',
                                           'implementation-step-3',
                                           'manual-checklist-base', 'manual-checklist-delta')
        parents = {
            **{stage: ('adversarial-review' if stage.startswith('adversarial-review-worker-')
                       else 'test-review' if stage.startswith('test-review-worker-')
                       else stage.split('-review-worker-', 1)[0]) for stage in review_workers},
            'execute-checklist-worker-MC-001': 'execute-checklist',
            'implementation-step-3': 'implementation',
            'manual-checklist-base': 'manual-checklist',
            'manual-checklist-delta': 'manual-checklist',
        }
        commands = {
            'reviewer': {'self-hosted': 'reviewer-self-hosted.sh', 'cline': 'reviewer-cline.sh',
                         'claude': 'reviewer-claude.sh', 'kimi': 'reviewer-kimi.sh', 'codex': 'codex'},
            'agent': {'self-hosted': 'agent-self-hosted.sh', 'cline': 'agent-cline.sh',
                      'claude': 'claude', 'kimi': 'agent-kimi.sh', 'codex': 'agent-codex.sh'},
        }
        for stage in dynamic_stages:
            parent = parents[stage]
            side = 'reviewer' if stage in review_workers or stage.startswith('manual-checklist-') else 'agent'
            for runner, command in commands[side].items():
                self.config.write_text('%s.runner %s\n%s.model configured-model\n' % (parent, runner, parent),
                                       encoding='utf-8')
                result = subprocess.run([bash_executable(), '-c', script, 'worker', stage],
                                        env=dict(os.environ, ROOT=str(ROOT), UNCLE_CONFIG=str(self.config)),
                                        text=True, encoding='utf-8', capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip().split(':')[:2], [runner, side])
                self.assertTrue(result.stdout.strip().endswith(command), result.stdout)

    def test_preview_build_follows_the_first_configured_model_stage(self):
        # The preview is not a Configure row. The shell resolver hands it the
        # first configured model stage's runner and model; reading its own key
        # here must land on the same profile, not refuse the driver's choice.
        self.config.write_text('derive-brief.runner claude\nchange-plan.runner self-hosted\n'
                               'change-plan.model local/deepseek-v4-flash\n'
                               'implementation.runner self-hosted\nimplementation.model qwen\n', encoding='utf-8')
        profiles = {'local/deepseek-v4-flash': {'base_url': 'http://localhost:9100/v1', 'api_key': 'deepseek-secret'},
                    'qwen': {'base_url': 'http://localhost:9200/v1', 'api_key': 'qwen-secret'}}
        save_keys(self.config, {'__opencode_models__': profiles})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(settings(self.config, 'preview-build'),
                             dict(model='deepseek-v4-flash', base_url='http://localhost:9100/v1', api_key='deepseek-secret'))
            with self.assertRaises(ValueError):
                settings(self.config, 'requirements')
        # An explicit preview-build.model still wins.
        self.config.write_text(self.config.read_text(encoding='utf-8') + 'preview-build.model qwen\n', encoding='utf-8')
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(settings(self.config, 'preview-build')['api_key'], 'qwen-secret')

    def test_test_review_investigate_inherits_test_reviews_model(self):
        # Live failure: the two-call test-review split (investigate, then
        # format) added "test-review-investigate" as its own log_name, but
        # config_stage() -- documented as mirroring uncle_config_stage in
        # stage-config.sh -- had no mapping for it, so every attempt raised
        # "Select a configured OpenCode self-hosted model for stage
        # test-review-investigate" before ever reaching the model. The stage
        # must resolve to the same profile as "test-review" itself.
        self.config.write_text('test-review.runner self-hosted\ntest-review.model local/deepseek-v4-flash\n',
                               encoding='utf-8')
        profiles = {'local/deepseek-v4-flash': {'base_url': 'http://localhost:9100/v1', 'api_key': 'deepseek-secret'}}
        save_keys(self.config, {'__opencode_models__': profiles})
        with patch.dict(os.environ, {}, clear=True):
            expected = dict(model='deepseek-v4-flash', base_url='http://localhost:9100/v1', api_key='deepseek-secret')
            self.assertEqual(settings(self.config, 'test-review'), expected)
            self.assertEqual(settings(self.config, 'test-review-investigate'), expected)

    def test_discovery_and_failed_refresh_preserves_catalog(self):
        import io
        from urllib.error import HTTPError
        from unittest.mock import Mock
        opener = Mock()
        response = io.BytesIO(b'{"data":[{"id":"model-b"},{"id":"model-a"},{"id":"model-b"},{"id":"openai/model-a"}]}')
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            self.assertEqual(discover_models('http://localhost:1234/v1/', 'dummy-key'), ['local/model-a','local/model-b'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://localhost:1234/v1/models')
        self.assertEqual(request.get_header('Authorization'), 'Bearer dummy-key')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 10)
        keys = {'__opencode_models__': {'old-model': self.values()}}
        before = json.dumps(keys)
        with patch('urllib.request.build_opener', return_value=opener):
            opener.open.side_effect = HTTPError('http://localhost', 401, 'private details', {}, None)
            with self.assertRaisesRegex(ValueError, 'HTTP 401'):
                refresh_models(keys, 'http://localhost:1234/v1', 'dummy-key')
        self.assertEqual(json.dumps(keys), before)
        with patch('self_hosted.discover_models', return_value=['new-model']):
            refresh_models(keys, 'http://localhost:1234/v1', 'dummy-key')
        self.assertEqual(list(keys['__opencode_models__']), ['new-model'])

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
        plan = self.root/'.uncle/docs/UPDATED_PROJECT_PLAN.md'
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text('Original approved content\n')
        valid = '## Verification commands\n```bash\npython3 -m pytest\n```\n## Protected verification paths\n```text\ntests/\n```\n'
        for content in ('## Verification commands\n', '## Verification commands\n```bash\npytest', valid):
            def generate(side, values, prompt, staged, **kwargs):
                self.assertNotEqual(staged, self.root)
                (staged/'.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text(content)
                (staged/'unwanted.py').write_text('incidental edit')
                return 'response', 1
            with patch.object(self_hosted, '_run_opencode', side_effect=generate):
                if content != valid:
                    with self.assertRaises(ValueError):
                        run_opencode('agent', self.values(), 'Plan', self.root, stage='updated-plan')
                    self.assertEqual(plan.read_text(encoding='utf-8'), 'Original approved content\n')
                else:
                    run_opencode('agent', self.values(), 'Plan', self.root, stage='updated-plan')
                    self.assertEqual(plan.read_text(encoding='utf-8'), valid)
            self.assertFalse((self.root/'unwanted.py').exists())

    def test_plan_format_retry_preserves_evidence_and_usage(self):
        import self_hosted
        invalid = '````markdown\n# Plan\nIncomplete'
        valid = '# Plan\n## Verification commands\n```bash\npytest\n```\n## Protected verification paths\n```text\ntests/\n```\n'
        responses = [invalid, valid]
        def generate(*args, **kwargs):
            kwargs['usage'].update(input_tokens=10, output_tokens=5, total_tokens=15)
            return responses.pop(0), 1
        usage = {}
        with patch.object(self_hosted, '_run_opencode', side_effect=generate) as run:
            _, turns = run_opencode('agent', self.values(), 'Plan', self.root, stage='updated-plan', usage=usage)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(turns, 2)
        self.assertEqual(usage['total_tokens'], 30)
        self.assertEqual((self.root/'.uncle/docs/UPDATED_PROJECT_PLAN.md').read_text(encoding='utf-8'), valid)
        rejected = list((self.root/'.uncle/workflow/logs').glob('updated_project_plan-rejected-*.md'))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].read_text(encoding='utf-8'), invalid)

    def test_plan_written_as_json_directly_to_file_is_still_rendered(self):
        # A model that ignores "do not use file tools" and writes the JSON
        # contract straight into the candidate file must still get the same
        # render-and-validate treatment as one that returned it in chat text
        # -- otherwise validate_plan() sees raw JSON where it expects a
        # '## Verification commands' heading and rejects a genuinely valid
        # response every time.
        import self_hosted, json as json_module
        plan = self.root/'.uncle/docs/UPDATED_PROJECT_PLAN.md'
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text('Original approved content\n')
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## Summary\n\nDo it.',
                   'verification_commands': 'pytest', 'protected_verification_paths': 'tests/'}

        def generate(side, values, prompt, staged, **kwargs):
            (staged/'.uncle/docs/UPDATED_PROJECT_PLAN.md').write_text(json_module.dumps(payload))
            return 'response text is ignored when the file exists', 1
        with patch.object(self_hosted, '_run_opencode', side_effect=generate):
            run_opencode('agent', self.values(), 'Plan', self.root, stage='updated-plan')
        text = plan.read_text(encoding='utf-8')
        self.assertIn('## Summary', text)
        self.assertIn('## Verification commands', text)
        self.assertIn('pytest', text)

    def test_requirements_written_as_json_directly_to_file_is_still_rendered(self):
        import self_hosted, json as json_module
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'requirements-interpretation', 'sections': {
            key: 'x' for key in ('required_functionality', 'optional_functionality', 'constraints',
                                  'user_visible_behaviors', 'system_behaviors', 'failure_behaviors',
                                  'ambiguities', 'assumptions', 'explicit_non_goals', 'definition_of_done')}}

        def generate(side, values, prompt, staged, **kwargs):
            (staged/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').write_text(json_module.dumps(payload))
            return 'response text is ignored when the file exists', 1
        with patch.object(self_hosted, '_run_opencode', side_effect=generate):
            run_opencode('agent', self.values(), 'Requirements', self.root, stage='requirements')
        text = (self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8')
        self.assertIn('## 10. Definition of done', text)

    def test_plan_crash_and_missing_output_preserve_original(self):
        import self_hosted
        plan = self.root/'.uncle/docs/UPDATED_PROJECT_PLAN.md'
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text('Original\n')
        with patch.object(self_hosted, '_run_opencode', side_effect=ValueError('failed')):
            with self.assertRaises(ValueError):
                run_opencode('agent', self.values(), 'Plan', self.root, stage='updated-plan')
        with patch.object(self_hosted, '_run_opencode', return_value=('no edits', 1)):
            with self.assertRaises(ValueError):
                run_opencode('agent', self.values(), 'Plan', self.root, stage='updated-plan')
        self.assertEqual(plan.read_text(encoding='utf-8'), 'Original\n')

    def test_output_at_the_limit_is_a_fragment_not_a_success(self):
        from self_hosted import ensure_output_complete, OutputTruncated, output_token_limit
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS', None)
            self.assertEqual(output_token_limit('implementation'), 64512)
            self.assertEqual(output_token_limit('implementation-step-7'), 64512)
            self.assertEqual(output_token_limit('execute-checklist'), 64512)
            self.assertEqual(output_token_limit('execute-checklist-worker-MC-001'), 64512)
            self.assertEqual(output_token_limit('manual-checklist'), 64512)
            self.assertEqual(output_token_limit('manual-checklist-base'), 64512)
            self.assertEqual(output_token_limit('manual-checklist-delta'), 64512)
            self.assertEqual(output_token_limit('updated-plan'), 64512)
            self.assertEqual(output_token_limit('updated-change-plan'), 64512)
            self.assertEqual(output_token_limit('adversarial-review'), 64512)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS': '12000'}, clear=False):
            self.assertEqual(output_token_limit('implementation'), 12000)
        ensure_output_complete({'output_tokens': 8191}, 8192)
        ensure_output_complete({}, 8192)
        with self.assertRaises(OutputTruncated):
            ensure_output_complete({'output_tokens': 8192}, 8192)
        with self.assertRaises(OutputTruncated):
            ensure_output_complete({'output_tokens': 8342}, 8192)
        path = self.root/'events.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in [
            dict(type='text', part=dict(text='## AR-001\n- Severity: Medium')),
            dict(type='step_finish', part=dict(reason='length', tokens=dict(input=10, output=8192)))]))
        with self.assertRaises(OutputTruncated):
            response_from_events(path)

    def test_truncated_review_is_retried_with_a_larger_output_limit(self):
        env = self.stub_environment()
        out = self.root/'report.md'
        command = [bash_executable(), (ROOT/'scripts/reviewer-self-hosted.sh').as_posix(), 'exec', '--output-last-message', str(out), 'Test prompt']
        result = subprocess.run(command, input='', text=True, encoding='utf-8', capture_output=True, timeout=20, cwd=self.root,
                                env=dict(env, FAKE_OPENCODE_MODE='truncate-once', WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS='8192', WORKFLOW_SELF_HOSTED_RETRY_ON_TRUNCATION='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Retrying with an output limit of 16384 tokens', result.stderr)
        self.assertEqual(out.read_bytes(), b'## Findings\n\nNOT READY\n')
        self.assertIn('"output": 16384', (self.root/'record.config').read_text(encoding='utf-8'), 'the retry ran with the doubled cap')
        # Always truncated: an error result, and no fragment written as the report.
        out.unlink()
        result = subprocess.run(command, input='', text=True, encoding='utf-8', capture_output=True, timeout=20, cwd=self.root,
                                env=dict(env, FAKE_OPENCODE_MODE='truncate', WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS='8192'))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('reached the configured limit', result.stderr)
        self.assertFalse(out.exists(), 'a fragment must not become the reviewer-owned artifact')

    def test_truncation_keeps_escalating_past_one_retry(self):
        # Seen live: a self-hosted adversarial-review overflowed the initial
        # 8192-token cap, then overflowed the doubled 16384-token retry too --
        # real findings, not padding. The old one-shot retry failed the stage
        # outright with room left in the context window; doubling should keep
        # going until either the model finishes or the context ceiling itself
        # is reached, not stop after an arbitrary single attempt.
        env = self.stub_environment()
        out = self.root/'report.md'
        command = [bash_executable(), (ROOT/'scripts/reviewer-self-hosted.sh').as_posix(), 'exec', '--output-last-message', str(out), 'Test prompt']
        result = subprocess.run(command, input='', text=True, encoding='utf-8', capture_output=True, timeout=20, cwd=self.root,
                                env=dict(env, FAKE_OPENCODE_MODE='truncate-twice', WORKFLOW_SELF_HOSTED_OUTPUT_TOKENS='8192', WORKFLOW_SELF_HOSTED_RETRY_ON_TRUNCATION='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Retrying with an output limit of 16384 tokens', result.stderr)
        self.assertIn('Retrying with an output limit of 32768 tokens', result.stderr)
        self.assertEqual(out.read_bytes(), b'## Findings\n\nNOT READY\n')
        self.assertIn('"output": 32768', (self.root/'record.config').read_text(encoding='utf-8'), 'the third attempt ran with the twice-doubled cap')
        self.assertEqual((self.root/'record.calls').read_text(), '3')

    def test_reviewer_document_is_validated_before_it_is_published(self):
        env = self.stub_environment()
        out = self.root/'ADVERSARIAL_REVIEW.md'
        command = [bash_executable(), (ROOT/'scripts/reviewer-self-hosted.sh').as_posix(), 'exec', '--output-last-message', str(out), 'Test prompt']
        result = subprocess.run(command, input='', text=True, encoding='utf-8', capture_output=True, timeout=20, cwd=self.root,
                                env=dict(env, FAKE_OPENCODE_MODE='summary-once', WORKFLOW_SELF_HOSTED_RETRY_ON_INVALID_DOCUMENT='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('not a valid ADVERSARIAL_REVIEW.md', result.stderr)
        self.assertIn('retrying once', result.stderr)
        self.assertEqual((self.root/'record.calls').read_text(), '2')
        self.assertTrue(out.read_text(encoding='utf-8').startswith('## AR-001: Display accepts Infinity'))
        self.assertIn('## Overall assessment', out.read_text(encoding='utf-8'))
        self.assertTrue(list((self.root/'.uncle/workflow/logs').glob('adversarial_review-rejected-*.md')), 'the summary is kept as evidence')
        # Always a summary: an error, and nothing published as the review.
        out.unlink()
        (self.root/'record.calls').unlink()
        result = subprocess.run(command, input='', text=True, encoding='utf-8', capture_output=True, timeout=20, cwd=self.root,
                                env=dict(env, FAKE_OPENCODE_MODE='summary'))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('not a valid ADVERSARIAL_REVIEW.md', result.stderr)
        self.assertFalse(out.exists(), 'a compaction summary must never become the review')
        self.assertEqual((self.root/'record.calls').read_text(), '1', 'invalid reviewer output must not retry by default')

    def test_reviewer_document_prefers_a_fenced_block_over_a_stray_leading_heading(self):
        # A real corruption: think-aloud starting with a heading-shaped
        # fragment ("### ~~MC-005~~ ...") fooled the naive first-heading scan
        # into publishing the whole response, fence markers included, as the
        # document. The real checklist was fenced in full further down.
        response = (
            '### ~~MC-005~~ [DELETED: no dormancy/owner-tracking exists]\n'
            '```\n\n'
            'Let me reconsider the merged checklist once more before finishing.\n\n'
            '```markdown\n'
            '# Manual checklist\n\n'
            '### MC-001 Real check\n'
            '- Priority: P0\n'
            '```\n'
        )
        document = reviewer_document(response)
        self.assertEqual(document, '# Manual checklist\n\n### MC-001 Real check\n- Priority: P0\n')

    def test_reviewer_document_unaffected_by_a_stray_fence_with_no_heading_inside(self):
        response = '```\nsome unrelated code snippet\n```\n\n# Manual checklist\n\nbody\n'
        document = reviewer_document(response)
        self.assertEqual(document, '# Manual checklist\n\nbody\n')

    def test_reviewer_document_keeps_scanning_past_an_earlier_headingless_fence(self):
        # A real corruption: a stub table-of-contents preview, in its own
        # closed fence with no heading inside, followed by narration and a
        # JSON tool-log blob, before the real checklist's own fence further
        # down. Stopping at the first fence abandoned fence-scanning entirely
        # and fell through to the naive whole-response scan, which grabbed
        # the stub's own heading-shaped line and everything after it,
        # narration and JSON included, as "the document".
        response = (
            '```\nSection 1: Smoke checks\nSection 2: ...\n```\n\n'
            'Let me now write the full checklist.\n\n'
            '{"type": "result", "subtype": "success"}\n\n'
            '```markdown\n'
            '# Manual checklist\n\n'
            '### MC-001 Real check\n'
            '- Priority: P0\n'
            '```\n'
        )
        document = reviewer_document(response)
        self.assertEqual(document, '# Manual checklist\n\n### MC-001 Real check\n- Priority: P0\n')

    def test_driver_narration_in_a_candidate_document_is_rejected(self):
        from self_hosted import validate_reviewer_document, InvalidReviewerDocument
        garbage = ('# Manual checklist\n\nSection 1: Smoke checks\n\n'
                   '{"type": "result", "subtype": "success"}\n\n'
                   'Current workflow state: VALIDATE_MANUAL_CHECKLIST\n')
        with self.assertRaises(InvalidReviewerDocument):
            validate_reviewer_document('MANUAL_CHECKLIST.md', garbage)

    def test_exact_usage_sums_messages_without_console_rounding(self):
        from self_hosted import opencode_usage
        path = self.root/'usage.jsonl'
        self.assertEqual(opencode_usage(path), {})
        events = [dict(event='startup', properties={}),
                  dict(type='step_finish', part=dict(tokens=dict(input=1234,output=57))),
                  dict(type='step_finish', part=dict(tokens=dict(input=2200,output=91)))]
        path.write_text('\n'.join(json.dumps(event) for event in events))
        self.assertEqual(opencode_usage(path), dict(input_tokens=3434,output_tokens=148,total_tokens=3582))
        events[1]['part']['tokens'].update(cache={'read': 10, 'write': 2}, reasoning=5)
        path.write_text('\n'.join(json.dumps(event) for event in events))
        self.assertEqual(opencode_usage(path), dict(input_tokens=3446,output_tokens=153,total_tokens=3599))
        events.append(dict(type='step_finish',part={}))
        path.write_text('\n'.join(json.dumps(event) for event in events))
        self.assertEqual(opencode_usage(path), {})

    def test_legacy_catalog_migration(self):
        save_keys(self.config, {'__aider_models__': {'openai/local-model:Q4': {k: v for k, v in self.values().items() if k != 'model'}}})
        with patch.dict(os.environ, {}, clear=True):
            values = settings(self.config, 'implementation')
        self.assertEqual(values['model'], 'local-model:Q4')
        with tempfile.TemporaryDirectory() as directory:
            command, _ = opencode_invocation('agent', values, 'test', self.root, directory)
        self.assertEqual(command[command.index('--model')+1], 'local/local-model:Q4')
        self.assertEqual(command[command.index('--variant')+1], 'none')

    def test_requirements_chat_response_is_saved_before_success(self):
        import self_hosted
        text = '# REQUIREMENTS_INTERPRETATION.md\n\n## 10. Definition of done\nPrint Hello World.\n'
        response = 'REQUIREMENTS_INTERPRETATION.md\n```markdown\n' + text + '```'
        with patch.object(self_hosted, '_run_opencode', return_value=(response, 1)) as run:
            run_opencode('agent', self.values(), 'Interpret', self.root, stage='requirements')
        self.assertEqual(run.call_args.args[0], 'agent')
        self.assertEqual((self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8'), text)
        with patch.object(self_hosted, '_run_opencode', return_value=('Done!', 1)):
            with self.assertRaises(ValueError):
                run_opencode('agent', self.values(), 'Interpret', self.root, stage='requirements')
        self.assertEqual((self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8'), text)

    def test_requirements_file_tools_publish_only_valid_document(self):
        import self_hosted
        document = '# Requirements\n\n## 10. Definition of done\nPrint Hello World.\n'
        def generate(side, values, prompt, staged, **kwargs):
            self.assertEqual(side, 'agent')
            self.assertFalse(kwargs['allow_shell'])
            self.assertNotEqual(staged, self.root)
            (staged/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').write_text(document, encoding='utf-8')
            (staged/'unwanted.txt').write_text('incidental')
            return 'REQUIREMENTS_INTERPRETATION.md', 1
        with patch.object(self_hosted, '_run_opencode', side_effect=generate):
            run_opencode('agent', self.values(), 'Interpret', self.root, stage='requirements')
        self.assertEqual((self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').read_text(), document)
        self.assertFalse((self.root/'unwanted.txt').exists())

    def test_combined_requirements_plan_publishes_the_interpretation(self):
        import self_hosted
        document = '# Requirements\n\n## 10. Definition of done\nPrint Hello World.\n'
        def generate(side, values, prompt, staged, **kwargs):
            (staged/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').write_text(document, encoding='utf-8')
            (staged/'.uncle/docs/PROJECT_PLAN.md').write_text('discarded combined-plan draft', encoding='utf-8')
            return 'Both documents written.', 1
        with patch.object(self_hosted, '_run_opencode', side_effect=generate):
            run_opencode('agent', self.values(),
                         'You perform two consecutive roles in a single pass', self.root,
                         stage='project-plan')
        self.assertEqual((self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').read_text(), document)
        self.assertFalse((self.root/'.uncle/docs/PROJECT_PLAN.md').exists())

    def test_staged_opencode_can_read_generated_requirements(self):
        import self_hosted
        source = self.root/'.uncle/docs/REQUIREMENTS.md'
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('# Requirements\n\nBuild it.\n', encoding='utf-8')
        document = '# Requirements\n\n## 10. Definition of done\nBuild it.\n'
        def generate(side, values, prompt, staged, **kwargs):
            self.assertEqual((staged/'.uncle/docs/REQUIREMENTS.md').read_text(encoding='utf-8'), source.read_text(encoding='utf-8'))
            (staged/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').write_text(document, encoding='utf-8')
            return 'written', 1
        with patch.object(self_hosted, '_run_opencode', side_effect=generate):
            run_opencode('agent', self.values(), 'Interpret', self.root, stage='requirements')

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
        with patch.object(self_hosted, '_run_opencode', side_effect=generate) as run:
            run_opencode('agent', self.values(), 'Interpret', self.root, stage='requirements', usage=usage)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(usage['total_tokens'], 240)
        self.assertEqual((self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').read_text(encoding='utf-8'), text)
        rejected = list((self.root/'.uncle/workflow/logs').glob('requirements-rejected-*.md'))
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].read_text(encoding='utf-8'), 'Done!')

    def test_json_response_is_rendered_to_the_interpretation_document(self):
        import self_hosted, json
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'requirements-interpretation',
                   'sections': {name.lower().replace(' ', '_').replace('-', '_'): 'No additional interpretation.'
                                for name in ('Required functionality', 'Optional functionality', 'Constraints',
                                             'User-visible behaviors', 'System behaviors', 'Failure behaviors',
                                             'Ambiguities', 'Assumptions', 'Explicit non-goals', 'Definition of done')}}
        rendered = self_hosted.document_response(json.dumps(payload), '.uncle/docs/REQUIREMENTS_INTERPRETATION.md')
        self.assertIn('## 1. Required functionality', rendered)
        self.assertIn('## 10. Definition of done', rendered)

    def test_fenced_json_response_still_renders(self):
        import self_hosted, json
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'requirements-interpretation',
                   'sections': {name.lower().replace(' ', '_').replace('-', '_'): 'No additional interpretation.'
                                for name in ('Required functionality', 'Optional functionality', 'Constraints',
                                             'User-visible behaviors', 'System behaviors', 'Failure behaviors',
                                             'Ambiguities', 'Assumptions', 'Explicit non-goals', 'Definition of done')}}
        wrapped = '```json\n' + json.dumps(payload) + '\n```'
        rendered = self_hosted.document_response(wrapped, '.uncle/docs/REQUIREMENTS_INTERPRETATION.md')
        self.assertIn('## 1. Required functionality', rendered)

    def test_json_response_missing_section_is_rejected(self):
        import self_hosted, json
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'requirements-interpretation', 'sections': {}}
        with self.assertRaises(ValueError):
            self_hosted.document_response(json.dumps(payload), '.uncle/docs/REQUIREMENTS_INTERPRETATION.md')

    def test_plan_json_response_is_rendered(self):
        import self_hosted, json
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '## Architecture\n\nA plan.',
                   'verification_commands': 'python3 -m pytest'}
        rendered = self_hosted.document_response(json.dumps(payload), '.uncle/docs/PROJECT_PLAN.md')
        self.assertIn('## Architecture', rendered)
        self.assertIn('## Verification commands', rendered)
        self.assertIn('python3 -m pytest', rendered)
        self.assertNotIn('Protected verification paths', rendered)

    def test_updated_plan_json_response_requires_protected_paths(self):
        import self_hosted, json
        payload = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'verification_commands': 'python3 -m pytest'}
        with self.assertRaises(ValueError):
            self_hosted.document_response(json.dumps(payload), '.uncle/docs/UPDATED_PROJECT_PLAN.md')
        payload['protected_verification_paths'] = 'tests/'
        rendered = self_hosted.document_response(json.dumps(payload), '.uncle/docs/UPDATED_PROJECT_PLAN.md')
        self.assertIn('## Protected verification paths', rendered)
        self.assertIn('tests/', rendered)

    def values(self):
        return {'api_key':'test-secret','model':'local-model:Q4','base_url':'http://localhost:8123/v1'}

    def test_opencode_config_and_modes(self):
        for side in ('agent', 'reviewer'):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as directory:
                command, env = opencode_invocation(side, self.values(), 'Test prompt', self.root, directory)
                self.assertEqual(command[1:4], ['run', '--format', 'json'])
                self.assertEqual(command[command.index('--model')+1], 'local/local-model:Q4')
                self.assertEqual(command[command.index('--variant')+1], 'none')
                self.assertEqual(command[command.index('--dir')+1], str(self.root))
                config = json.loads(env['OPENCODE_CONFIG_CONTENT'])
                self.assertEqual(config['provider']['local']['options']['baseURL'], self.values()['base_url'])
                self.assertEqual(config['provider']['local']['models']['local-model:Q4']['options'],
                                 {'reasoningEffort': 'none'})
                self.assertEqual(env['UNCLE_OPENCODE_API_KEY'], 'test-secret')
                self.assertNotIn('test-secret', str(command) + env['OPENCODE_CONFIG_CONTENT'])
                self.assertEqual(config['permission']['edit'], 'allow' if side == 'agent' else 'deny')
                self.assertEqual(config['permission']['bash'], 'allow' if side == 'agent' else 'deny')
                self.assertEqual(config['permission']['task'] if 'task' in config['permission'] else config['permission']['*'], 'deny')
                self.assertFalse(config['snapshot'])
                self.assertFalse((self.root/'.git').exists())

    def test_effort_reaches_the_opencode_model_options(self):
        with tempfile.TemporaryDirectory() as directory:
            command, env = opencode_invocation('agent', dict(self.values(), effort='high'), 'Test prompt', self.root, directory)
            config = json.loads(env['OPENCODE_CONFIG_CONTENT'])
            self.assertEqual(command[command.index('--model')+1], 'local/local-model:Q4')
            self.assertEqual(command[command.index('--variant')+1], 'high')
            self.assertEqual(config['provider']['local']['models']['local-model:Q4']['options'],
                             {'reasoningEffort': 'high'})

    def test_effort_parsed_from_runner_flags(self):
        import io
        cases = [(['-p', '--effort', 'medium'], 'agent', 'medium'),
                 (['exec', '-c', 'model_reasoning_effort=high', '--output-last-message', 'out.md', 'Do it'], 'reviewer', 'high'),
                 (['exec', '-c', 'model=x', 'Do it'], 'reviewer', '')]
        for args, side, expected in cases:
            with self.subTest(args=args), patch('sys.stdin', io.StringIO('prompt from stdin')):
                self.assertEqual(parse_arguments(side, args)[3], expected)

    def test_reviewer_zero_status_limit_uses_default(self):
        with patch.dict(os.environ, UNCLE_STATUS_STAGE_TURNS='0'):
            self.assertEqual(parse_arguments('reviewer', ['exec', 'Review the checklist'])[2], 80)
            self.assertEqual(parse_arguments('reviewer', ['exec', '--max-turns', '12', 'Review'])[2], 12)
            for limit in ('0', '-1'):
                with self.assertRaisesRegex(ValueError, 'positive turn limit'):
                    parse_arguments('reviewer', ['exec', '--max-turns', limit, 'Review'])
        with patch.dict(os.environ, UNCLE_STATUS_STAGE_TURNS='15'):
            self.assertEqual(parse_arguments('reviewer', ['exec', 'Review'])[2], 15)

    def stub_environment(self):
        stub=self.root/'fake_opencode.py'
        stub.write_text("""import json,os,pathlib,sys,time
args=sys.argv[1:]
assert os.environ['UNCLE_OPENCODE_API_KEY']=='secret-with-#-characters'
config=json.loads(os.environ['OPENCODE_CONFIG_CONTENT'])
assert config['provider']['local']['options']['baseURL']=='http://localhost:8123/v1'
assert args[args.index('--model')+1]=='local/local-model:Q4'
assert args[args.index('--variant')+1]=='none'
assert 'secret-with-#-characters' not in str(args)
assert pathlib.Path(args[args.index('--file')+1]).read_text(encoding='utf-8').startswith('Test prompt')
pathlib.Path(os.environ['RECORD']).write_text(str(pathlib.Path(os.environ['XDG_CONFIG_HOME']).parent),encoding='utf-8')
mode=os.environ.get('FAKE_OPENCODE_MODE','ok')
calls=pathlib.Path(os.environ['RECORD']+'.calls'); n=int(calls.read_text()) if calls.exists() else 0; calls.write_text(str(n+1))
pathlib.Path(os.environ['RECORD']+'.config').write_text(json.dumps(config),encoding='utf-8')
def find_output(o):
    if isinstance(o,dict):
        if isinstance(o.get('limit'),dict) and 'output' in o['limit']: return o['limit']['output']
        for v in o.values():
            r=find_output(v)
            if r: return r
    if isinstance(o,list):
        for v in o:
            r=find_output(v)
            if r: return r
cap=find_output(config) or 8192
if mode=='summary' or (mode=='summary-once' and n==0):
    # A model answering OpenCode's compaction prompt instead of reviewing.
    print(json.dumps(dict(type='text',part=dict(text='## Conversation Summary\\n### Objective\\nReview the plan.\\n### Next Step\\nWrite findings to ADVERSARIAL_REVIEW.md.'))))
    print(json.dumps(dict(type='step_finish', part=dict(reason='stop',tokens=dict(input=1234,output=57)))),flush=True)
    sys.exit(0)
if mode=='summary-once':
    print(json.dumps(dict(type='text',part=dict(text='## AR-001: Display accepts Infinity\\n\\n- Severity: high\\n- References: I-1\\n- Failure: Infinity is shown\\n- Fix: reject it\\n- Verify: unit test\\n\\n## Overall assessment\\n\\nOne blocking finding.'))))
    print(json.dumps(dict(type='step_finish', part=dict(reason='stop',tokens=dict(input=1234,output=57)))),flush=True)
    sys.exit(0)
if mode=='truncate' or (mode=='truncate-once' and n==0) or (mode=='truncate-twice' and n<2):
    # A model cut off at whatever output limit it was given: a fragment, and
    # a token count equal to the cap.
    print(json.dumps(dict(type='text',part=dict(text='## AR-001\\n- Severity: Medium'))))
    print(json.dumps(dict(type='step_finish', part=dict(reason='stop',tokens=dict(input=1234,output=cap)))),flush=True)
    sys.exit(0)
print(json.dumps(dict(type='step_finish', part=dict(reason='stop',tokens=dict(input=1234,output=57)))),flush=True)
if mode=='timeout': time.sleep(30)
if mode=='api-timeout': print('provider timed out')
if mode not in ('empty','api-timeout'):
    print(json.dumps(dict(type='text',part=dict(text='## Findings\\n\\nNOT READY'))))
print('OpenCode banner and costs should not become the report')
sys.exit(7 if mode=='fail' else 0)
""",encoding='utf-8')
        wrapper=self.root/'fake-opencode'
        wrapper.write_bytes(b'#!/usr/bin/env bash\nexec "$TEST_PYTHON" "$TEST_STUB" "$@"\n')
        wrapper.chmod(0o755)
        return dict(os.environ, WORKFLOW_OPENCODE_CMD=str(wrapper), TEST_PYTHON=sys.executable, TEST_STUB=str(stub),
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
                self.assertNotIn('OpenCode banner',result.stdout)
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

    def test_runner_directory_retries_windows_sharing_violation(self):
        import self_hosted
        real_cleanup = tempfile.TemporaryDirectory.cleanup
        calls = []
        def cleanup(directory):
            calls.append(directory.name)
            if len(calls) == 1:
                error = PermissionError('output.log still open')
                error.winerror = 32
                raise error
            real_cleanup(directory)
        with patch.object(tempfile.TemporaryDirectory, 'cleanup', cleanup):
            with self.assertRaisesRegex(ValueError, 'original timeout; diagnostic log:'):
                with self_hosted.runner_directory('uncle-cleanup-test-') as directory:
                    (Path(directory) / 'output.log').write_text('timeout')
                    raise ValueError('original timeout; diagnostic log: saved.log')
        self.assertEqual(len(calls), 2)
        self.assertFalse(Path(directory).exists())

    def test_failures_never_write_a_review(self):
        env=self.stub_environment()
        for mode in ('fail','empty','timeout','api-timeout'):
            with self.subTest(mode=mode):
                out=self.root/(mode+'.md')
                env.update(FAKE_OPENCODE_MODE=mode,WORKFLOW_SELF_HOSTED_SECONDS='1')
                result=subprocess.run([bash_executable(),(ROOT/'scripts/reviewer-self-hosted.sh').as_posix(),
                    'exec','--output-last-message',str(out),'Test prompt'],env=env,cwd=self.root,
                    text=True,encoding='utf-8',capture_output=True,timeout=10)
                self.assertNotEqual(result.returncode,0,result.stdout)
                failure = json.loads(result.stdout.splitlines()[-1])
                self.assertTrue(failure['error_detail'])
                if mode == 'api-timeout':
                    self.assertIn('Model API requests timed out', failure['error_detail'])
                self.assertIsInstance(failure['duration_ms'], int)
                if mode != 'empty':
                    self.assertIn('diagnostic log:', failure['error_detail'])
                diagnostics = list((self.root/'.uncle/workflow/logs').glob('opencode-failure-*.log'))
                self.assertTrue(diagnostics)
                for log in diagnostics:
                    self.assertNotIn('secret-with-#-characters', log.read_text(encoding='utf-8'))
                self.assertFalse(out.exists())
                self.assertFalse(Path((self.root/'record').read_text(encoding='utf-8')).exists())

    def test_json_events_preserve_final_response(self):
        path = self.root/'output.log'
        events = [dict(type='text', part=dict(text='old')),
                  dict(type='step_finish', part=dict(reason='tool-calls')),
                  dict(type='text', part=dict(text='## Final\n| A | B |')),
                  dict(type='step_finish', part=dict(reason='stop'))]
        path.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
        self.assertEqual(response_from_events(path), ('## Final\n| A | B |', 2))
        events.append(dict(type='error', error={'message': 'failed'}))
        path.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
        with self.assertRaises(ValueError):
            response_from_events(path)

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
            self.assertEqual(ui._config_items(), ['1. Configure stages', '2. Configure OpenCode / self hosting', '3. Miscellaneous', '4. Supervision', '5. Recovery'])
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
            self.assertEqual([row.split()[0] for row in ui._config_items()], module.BUILD_CONFIG_STAGES)
            self.assertNotIn('triage', [row.split()[0] for row in ui._config_items()])
            ui.config_section = 'opencode'
            self.assertIn('1 loaded', ui._config_items()[1])
            ui.config_section = 'supervision'
            with patch.object(module, 'runners_for', return_value=['claude', 'codex', 'self-hosted']):
                ui._open_picker('runner', '!supervision')
                self.assertEqual(ui.state, 'picker')
                self.assertEqual(ui._picker_rows(), [('option', 'claude'), ('option', 'codex'), ('option', 'self-hosted')])
            ui._open_picker('effort', '!supervision')
            self.assertEqual(ui._picker_rows()[:4], [('option', 'none'), ('option', 'low'), ('option', 'medium'), ('option', 'high')])
            ui._open_picker('model', '!supervision')
            self.assertIn(('model', 'claude-sonnet-5'), ui._picker_rows())
            self.assertEqual(ui.stage_fields('implementation'),['runner','effort','model'])
            self.assertEqual(ui._field_display('@local/local-model:Q4','api_key'),'********')
            ui.save_config()
            ui.load_config()
            self.assertEqual(ui.stage_model('implementation'),'local/local-model:Q4')
            self.assertEqual(ui.stage_api_keys['__opencode_models__']['local/local-model:Q4']['base_url'],'http://localhost:8123/v1')
            self.assertEqual(read_keys(self.config)['__opencode_models__']['local/local-model:Q4']['api_key'],'secret-with-#-characters')
            ui._open_picker('model','implementation')
            self.assertEqual(ui.state,'picker')
            self.assertEqual(ui._picker_rows(), [('option', 'local/local-model:Q4'), ('custom', 'Custom… (type a model id)')])
            ui._open_stage('@connection')
            self.assertEqual(ui.stage_fields('@connection'), ['base_url', 'api_key'])
            with patch.object(ui, 'maybe_reload'), patch('self_hosted.discover_models', return_value=['local/local-model:Q4', 'local/second-model']):
                ui._set_field('@connection', 'api_key', 'secret-with-#-characters')
            ui._open_picker('model', 'implementation')
            self.assertEqual(ui._picker_rows(), [('option', 'local/local-model:Q4'), ('option', 'local/second-model'), ('custom', 'Custom… (type a model id)')])
            self.assertNotIn('second-secret', str(ui._config_items()))
            self.assertNotIn('second-secret', self.config.read_text(encoding='utf-8'))
            ui.stage_target = 'implementation'
            with patch.object(ui, 'maybe_reload'):
                ui._apply_opencode_to_all_stages()
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
