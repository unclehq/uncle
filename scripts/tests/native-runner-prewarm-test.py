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
