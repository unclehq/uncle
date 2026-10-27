#!/usr/bin/env python3
"""A schema-checked run (`claude --json-schema`) through native_stage.py -- every stage under the TUI -- must hand
the validated object back on its result event, or the driver reads nothing and a plan stage falls back."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))

FAKE = '''#!/usr/bin/env python3
import json, os, sys
open(os.environ['ARGV_LOG'], 'w').write(json.dumps(sys.argv[1:]))
def out(value): print(json.dumps(value), flush=True)
for line in sys.stdin:
    event = json.loads(line)
    if event.get('type') != 'user':
        continue
    out({'type': 'user', 'uuid': event['uuid']})
    mode = os.environ.get('FAKE_MODE', 'result')
    if mode != 'none':
        out({'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'StructuredOutput', 'input': {'from': 'tool'}}]}})
    result = {'type': 'result', 'is_error': False, 'usage': {'input_tokens': 5, 'output_tokens': 7}, 'total_cost_usd': 0.01}
    if mode == 'result':
        result['structured_output'] = {'from': 'result'}
    out(result)
    break
'''


class NativeStructuredOutput(unittest.TestCase):
    def run_stage(self, mode, schema=True):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'claude'
            fake.write_text(FAKE)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            args = ['-p', '--effort', 'low', '--output-format', 'stream-json', '--verbose', '--allowedTools', '']
            if schema:
                args += ['--json-schema', '{"type":"object"}']
            env = dict(os.environ, WORKFLOW_CLAUDE_CMD=str(fake), ARGV_LOG=str(Path(tmp) / 'argv.json'), FAKE_MODE=mode,
                       UNCLE_STEERING='1')
            for name in ('UNCLE_STATUS_FILE',):
                env.pop(name, None)
            done = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/native_stage.py'), '--runner', 'claude',
                                   '--side', 'agent', '--stage', 'project-plan-section-outline', '--'] + args,
                                  input='Write the plan.', capture_output=True, text=True, cwd=tmp, env=env, timeout=60)
            argv = json.loads((Path(tmp) / 'argv.json').read_text()) if (Path(tmp) / 'argv.json').exists() else []
            final = [json.loads(line) for line in done.stdout.splitlines() if line.startswith('{"type": "result"')]
            return done, final[-1] if final else {}, argv

    def test_the_schema_reaches_claude_and_the_validated_object_comes_back(self):
        done, result, argv = self.run_stage('result')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('--json-schema', argv)
        self.assertEqual(argv[argv.index('--json-schema') + 1], '{"type":"object"}')
        self.assertEqual(result.get('structured_output'), {'from': 'result'})

    def test_the_tool_call_is_the_fallback(self):
        _, result, _ = self.run_stage('tool')
        self.assertEqual(result.get('structured_output'), {'from': 'tool'})

    def test_a_run_without_a_schema_reports_no_object(self):
        _, result, argv = self.run_stage('none', schema=False)
        self.assertNotIn('--json-schema', argv)
        self.assertNotIn('structured_output', result)

    def test_the_driver_reads_what_native_stage_prints(self):
        import structured_output
        _, result, _ = self.run_stage('result')
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'stage.jsonl'
            log.write_text(json.dumps(result) + '\n')
            self.assertEqual(structured_output.extract(log), {'from': 'result'})


if __name__ == '__main__':
    unittest.main()
