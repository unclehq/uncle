#!/usr/bin/env python3
"""Hermetic driver confinement and writer-watchdog regressions."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent
import preflight_readonly
import self_hosted
import self_hosted_http


class Builder(unittest.TestCase):
    def test_driver_rejects_worker_edits_without_touching_live_inputs(self):
        source = (ROOT / 'scripts/stagegate.sh').read_text()
        function = re.search(r'^run_preflight_readonly_worker\(\) \{\n.*?^}', source, re.M | re.S)[0]
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / 'tests').mkdir()
            (project / 'tests/app.spec.js').write_text('protected')
            state = project / '.uncle/workflow'
            (state / 'logs').mkdir(parents=True)
            script = function + '''
run_claude() { printf changed > tests/app.spec.js; }
run_preflight_readonly_worker "$PWD/prompt" preflight-worker-browser "$STATE_DIR/packet.json"
'''
            env = dict(os.environ, ROOT=str(ROOT), STATE_DIR=str(state), LOG_DIR=str(state / 'logs'))
            result = subprocess.run(['bash', '-c', script], cwd=project, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('preflight-worker-browser', result.stderr)
            self.assertIn('tests/app.spec.js', result.stderr)
            self.assertEqual((project / 'tests/app.spec.js').read_text(), 'protected')
            self.assertTrue((state / 'preflight-readonly-violation').exists())
            self.assertTrue((state / 'stop-reason').exists())
            self.assertEqual((state / 'stop-reason').read_text(),
                             'preflight-worker-browser: read-only preflight violation\n')

    def test_unattended_launcher_does_not_restart_exhausted_writers(self):
        launcher = re.search(r'^launch\(\) \{\n.*?^}', (ROOT / 'uncle').read_text(), re.M | re.S)[0]
        for driver in ('stagegate.sh', 'change-workflow.sh'):
            with self.subTest(driver=driver), tempfile.TemporaryDirectory() as temp:
                source = (ROOT / 'scripts' / driver).read_text()
                exhausted = re.search(r'^        if \[\[ "\$failed" != 0 \]\]; then\n'
                                      r'            if stage_uses_self_hosted updated-(?:change-)?plan AGENT; then\n'
                                      r'.*?^        fi', source, re.M | re.S)[0]
                state = Path(temp) / '.uncle/workflow'
                state.mkdir(parents=True)
                (state / 'state').write_text('UPDATED_PLAN')
                (state / 'completed-packet.json').write_text('{"kept":true}')
                script = launcher + '''
stage_uses_self_hosted() { return 0; }
driver() {
    local failed=1
    echo attempt >> attempts
''' + exhausted + '''
}
C_RED= C_YELLOW= C_RESET= UNCLE_LAUNCH_RETRY_DELAY=0
launch driver --unattended
'''
                env = dict(os.environ, STATE_DIR=str(state))
                result = subprocess.run(['bash', '-c', script], cwd=temp, env=env,
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((Path(temp) / 'attempts').read_text(), 'attempt\n')
                stage = 'updated-plan' if driver == 'stagegate.sh' else 'updated-change-plan'
                self.assertEqual((state / 'stop-reason').read_text(), stage + ': writer attempts exhausted\n')
                self.assertEqual((state / 'completed-packet.json').read_text(), '{"kept":true}')
                self.assertNotIn('resuming automatically', result.stdout)

    def test_writer_watchdog_kills_descendants_and_returns_to_caller(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, ROOT=str(ROOT), WORKFLOW_SELF_HOSTED_WRITER_SECONDS='1')
            script = '''
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { return 0; }
run_claude() { (sleep 3; echo leaked > leaked) & wait; }
workflow_model_writer updated-plan run_claude prompt updated-plan-worker-edits-3
'''
            start = time.monotonic()
            result = subprocess.run(['bash', '-c', script], cwd=temp, env=env, capture_output=True, text=True, timeout=5)
            self.assertLess(time.monotonic() - start, 3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('updated-plan-worker-edits-3', result.stderr)
            self.assertIn('wall-clock budget', result.stderr)
            time.sleep(2.2)
            self.assertFalse((Path(temp) / 'leaked').exists())

    def test_exhausted_batch_does_not_restart_the_whole_plan(self):
        source = (ROOT / 'scripts/stagegate.sh').read_text()
        function = re.search(r'^run_updated_plan_adaptive\(\) \{\n.*?^}', source, re.M | re.S)[0]
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            state = project / '.uncle/workflow'
            (state / 'documents').mkdir(parents=True)
            (state / 'documents/PROJECT_PLAN.json').write_text(json.dumps({
                'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': '# Plan\n\n## Notes\n\nKept.',
                'verification_commands': 'true', 'protected_verification_paths': 'tests/a.py'}))
            (state / 'documents/ADVERSARIAL_REVIEW.json').write_text(json.dumps({
                'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                'findings': [{'id': 'AR-%d' % n} for n in range(6)]}))
            script = function + '''
stage_uses_self_hosted() { return 0; }
ensure_project_plan_json() { return 0; }
require_file() { test -f "$1"; }
run_updated_plan_edit_writers() { touch "$STATE_DIR/updated-plan-writers-exhausted"; return 1; }
run_updated_plan_compact() { touch restarted; }
run_updated_plan_adaptive
'''
            env = dict(os.environ, ROOT=str(ROOT), STATE_DIR=str(state), WORKFLOW_SELF_HOSTED_STAGE_JOBS='2')
            result = subprocess.run(['bash', '-c', script], cwd=project, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((state / 'updated-plan-writers-exhausted').exists(), result.stderr)
            self.assertFalse((project / 'restarted').exists())

    def test_cheap_retry_disables_thinking_even_with_configured_effort(self):
        with patch.dict(os.environ, {'UNCLE_UPDATED_PLAN_CHEAP_RETRY': '1',
                        'WORKFLOW_SELF_HOSTED_REASONING_EFFORT': 'on'}, clear=True):
            values = self_hosted_http.configure_request_options({'_request_options': {
                'chat_template_kwargs': {'enable_thinking': True, 'other': 'kept'}}})
            self.assertEqual(values['_request_options']['chat_template_kwargs'],
                             {'enable_thinking': False, 'other': 'kept'})
            self.assertIsNone(self_hosted_http.reasoning_effort(values, 'high'))

    def test_preflight_probe_state_persists_but_project_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_STATUS_STAGE': 'preflight-worker-tooling',
                'UNCLE_CONFIG': str(Path(temp) / 'config'), 'UNCLE_PROJECT_ROOT': temp}, clear=True):
            root = Path(temp)
            (root / 'input').write_text('original')
            _, policy, _, _, _, _ = self_hosted._http_setup('agent', {}, '', root, True, 'preflight-worker-packet')
            try:
                first = http_agent.run_tool(policy, 'bash', {'command': 'echo scratch > input'})
                self.assertIn('exit status 0', first)
                self.assertIn('scratch', http_agent.run_tool(policy, 'bash', {'command': 'cat input'}))
                self.assertEqual((root / 'input').read_text(), 'original')
                scratch = Path(policy.preflight_scratch.name)
            finally:
                policy.cleanup()
            self.assertFalse(scratch.exists())

    def test_snapshot_uses_untracked_files_and_rewrites_internal_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'source'
            root.mkdir()
            (root / 'untracked').write_text('not committed')
            (root / 'link').symlink_to(root / 'untracked')
            staged = preflight_readonly.prepare(root)
            try:
                self.assertEqual((staged / 'link').resolve(), staged / 'untracked')
                (staged / 'link').write_text('scratch')
                self.assertEqual((root / 'untracked').read_text(), 'not committed')
                with self.assertRaisesRegex(ValueError, 'preflight-worker-data'):
                    preflight_readonly.check(staged, 'preflight-worker-data')
            finally:
                preflight_readonly.main(['remove', str(staged)])


if __name__ == '__main__':
    unittest.main()
