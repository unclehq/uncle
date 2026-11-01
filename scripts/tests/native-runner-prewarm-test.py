#!/usr/bin/env python3
"""Regression test: unattended prewarming starts only an idle native CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'scripts/lib/native_stage.py'


FAKE_CLAUDE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['PREWARM_MARKER']).write_text(str(os.getpid()))
for line in sys.stdin:
    value = json.loads(line)
    if value.get('type') == 'user':
        print(json.dumps({'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': str(os.getpid())}
        ]}}), flush=True)
        print(json.dumps({'type': 'result', 'is_error': False,
                          'result': json.dumps({'provider_pid': os.getpid()})}), flush=True)
'''


# What the idle CLI is launched with. The real stage reuses this very process, and every test the agent runs inherits its
# environment: a live run's status file in it made a test that drives stagegate.sh or change-workflow.sh write its stage
# events (a second change-plan, requirements, adversarial-review) into the operator's stage panel.
ENV_DUMPING_CLAUDE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['PREWARM_ENV_DUMP']).write_text(json.dumps(sorted(os.environ)))
for line in sys.stdin:
    pass
'''

# Everything a driver exports that names the live run; none of it may reach a runner the agent's commands inherit from.
LIVE_RUN_ENV = {
    'UNCLE_STATUS_FILE': '/tmp/live-status.jsonl', 'UNCLE_PROJECT_ROOT': '/tmp/live-project', 'UNCLE_CONFIG': '/tmp/live-config',
    'UNCLE_STEERING': '1', 'UNCLE_SUPERVISION_NOTE': 'note', 'UNCLE_SUPERVISION_HOST': 'tui',
    'STAGEGATE_RUN_ID': 'run', 'STAGEGATE_ORIGIN_REPO': 'owner/repo', 'STAGEGATE_ORIGIN_ISSUE': '116',
    'DOCUMENT_BUDGET_SOURCE': '/tmp/live-request.md',
}


class NativeRunnerPrewarmEnvironment(unittest.TestCase):
    def prewarm(self, runner_env=None):
        raw = tempfile.mkdtemp(prefix='uncle-native-prewarm-env-')
        self.addCleanup(lambda: __import__('shutil').rmtree(raw, ignore_errors=True))
        root = Path(raw)
        dump = root / 'env.json'
        fake = root / 'claude'
        fake.write_text(ENV_DUMPING_CLAUDE)
        fake.chmod(0o755)
        owner = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        def stop_owner():
            if owner.poll() is None:
                owner.kill()
            owner.wait(timeout=5)
        self.addCleanup(stop_owner)
        env = os.environ | LIVE_RUN_ENV | {
            'WORKFLOW_CLAUDE_CMD': str(fake), 'UNCLE_RUNNER_POOL_OWNER_PID': str(owner.pid), 'UNCLE_RUNNER_REUSE': '1',
            'PREWARM_ENV_DUMP': str(dump),
        }
        result = subprocess.run([sys.executable, '-B', str(NATIVE), '--prewarm', '--runner', 'claude', '--side', 'agent',
                                 '--stage', 'implementation', '--', '-p', '--effort', 'low', '--strict-mcp-config',
                                 '--max-turns', '40', '--output-format', 'stream-json', '--verbose', '--allowedTools', 'Read,Write'],
                                cwd=root, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 5
        while not dump.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(dump.exists(), 'prewarm did not launch the idle CLI')
        return set(json.loads(dump.read_text()))

    def test_the_idle_cli_does_not_inherit_the_live_runs_variables(self):
        names = self.prewarm()
        leaked = sorted(set(LIVE_RUN_ENV) & names)
        self.assertEqual(leaked, [], 'the prewarmed CLI inherited the live run: %s' % leaked)

    def test_the_idle_cli_does_not_inherit_the_pool_owner(self):
        self.assertNotIn('UNCLE_RUNNER_POOL_OWNER_PID', self.prewarm())

    def test_the_idle_cli_keeps_what_it_needs_to_run(self):
        names = self.prewarm()
        self.assertIn('PATH', names)
        self.assertIn('HOME', names)


class NativeRunnerPrewarm(unittest.TestCase):
    def test_prewarm_starts_the_exact_idle_claude_pool_without_a_prompt(self):
        with tempfile.TemporaryDirectory(prefix='uncle-native-prewarm-') as raw:
            root = Path(raw)
            marker = root / 'started'
            fake = root / 'claude'
            fake.write_text(FAKE_CLAUDE)
            fake.chmod(0o755)
            owner = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            def stop_owner():
                if owner.poll() is None:
                    owner.kill()
                owner.wait(timeout=5)
            self.addCleanup(stop_owner)
            env = os.environ | {
                'WORKFLOW_CLAUDE_CMD': str(fake),
                'UNCLE_RUNNER_POOL_OWNER_PID': str(owner.pid),
                'UNCLE_RUNNER_REUSE': '1',
                'PREWARM_MARKER': str(marker),
            }
            result = subprocess.run([
                sys.executable, '-B', str(NATIVE), '--prewarm', '--runner', 'claude',
                '--side', 'agent', '--stage', 'requirements', '--', '-p', '--effort', 'low',
                '--strict-mcp-config', '--max-turns', '40', '--output-format', 'stream-json',
                '--verbose', '--allowedTools', 'Read,Write',
            ], cwd=root, env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(marker.exists(), 'prewarm did not launch the idle CLI')
            warm_pid = marker.read_text()
            descriptors = list((root / '.uncle/workflow/runner-pool').glob('*.json'))
            self.assertEqual(len(descriptors), 1)
            descriptor = json.loads(descriptors[0].read_text())
            self.assertEqual(descriptor['runner'], 'claude')
            self.assertEqual(descriptor['side'], 'agent')
            # No input is sent during warm-up, so the fake CLI remains idle.
            self.assertEqual(result.stdout, '')
            actual = subprocess.run([
                sys.executable, '-B', str(NATIVE), '--runner', 'claude', '--side', 'agent',
                '--stage', 'requirements', '--', '-p', '--effort', 'low', '--strict-mcp-config',
                '--max-turns', '40', '--output-format', 'stream-json', '--verbose',
                '--allowedTools', 'Read,Write',
            ], cwd=root, env=env, input='continue\n', capture_output=True, text=True, timeout=20)
            self.assertEqual(actual.returncode, 0, actual.stderr)
            payload = json.loads(actual.stdout.strip().splitlines()[-1])
            self.assertIn(warm_pid, payload['result'])


if __name__ == '__main__':
    unittest.main()
