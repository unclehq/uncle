"""Read-only review lenses on hosted runners are asked for their packet through the runner's schema; nothing else is."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import review_schema
import self_hosted

HELPER = ROOT / 'scripts/lib/review_schema.py'


def prompt(kind):
    return 'Review the build.\n\nReturn one JSON object: {"schema":"uncle.artifact/v1","kind":"%s","findings":[]}\n' % kind


class Helper(unittest.TestCase):
    def prepare(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'p.md', Path(tmp) / 's.json'
            source.write_text(text)
            code = subprocess.run([sys.executable, '-B', str(HELPER), 'prepare', str(source), str(out)]).returncode
            return code, (json.loads(out.read_text()) if out.exists() else None)

    def test_every_allowlisted_packet_gets_the_schema_the_self_hosted_loop_uses(self):
        for kind in sorted(review_schema.KINDS):
            code, schema = self.prepare(prompt(kind))
            self.assertEqual(code, 0, kind)
            self.assertEqual(schema, self_hosted.artifact_schema(kind), kind)

    def test_workers_that_need_their_tools_and_unknown_prompts_get_none(self):
        for text in (prompt('checklist-execution-worker-packet'), prompt('preflight-worker-packet'),
                     prompt('project-plan-section-worker-packet'), prompt('updated-plan-edit-ops-packet'),
                     'Review the build. No packet contract here.', ''):
            code, schema = self.prepare(text)
            self.assertEqual((code, schema), (1, None), text[:60])

    def test_a_missing_prompt_is_not_an_error_the_caller_must_handle(self):
        done = subprocess.run([sys.executable, '-B', str(HELPER), 'prepare', '/nonexistent/prompt.md', '/tmp/never.json'])
        self.assertEqual(done.returncode, 1)

    def test_the_allowlist_is_the_read_only_review_packets_only(self):
        self.assertEqual(review_schema.KINDS, {'adversarial-review-worker-packet', 'manual-checklist-worker-packet',
                                               'test-review-worker-packet', 'final-audit-worker-packet',
                                               'updated-plan-worker-packet'})


FAKE = '''#!/usr/bin/env python3
import json, os, sys
open(os.environ['ARGV_LOG'], 'w').write(json.dumps(sys.argv[1:]))
def out(value): print(json.dumps(value), flush=True)
for line in sys.stdin:
    event = json.loads(line)
    if event.get('type') != 'user':
        continue
    out({'type': 'user', 'uuid': event['uuid']})
    packet = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit-worker-packet', 'findings': []}
    out({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'summary only, not the packet'}]}})
    result = {'type': 'result', 'is_error': False, 'usage': {'input_tokens': 5, 'output_tokens': 7}, 'total_cost_usd': 0.01,
              'result': 'summary only, not the packet'}
    if os.environ.get('FAKE_STRUCTURED') == '1':
        result['structured_output'] = packet
    out(result)
    break
'''


class NativeReviewer(unittest.TestCase):
    def run_stage(self, schema=True, delivery='', structured=True):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'claude'
            fake.write_text(FAKE)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            schema_file = Path(tmp) / 'schema.json'
            schema_file.write_text('{"type":"object","title":"packet"}')
            output = Path(tmp) / 'out.json'
            env = dict(os.environ, WORKFLOW_CLAUDE_CMD=str(fake), ARGV_LOG=str(Path(tmp) / 'argv.json'), UNCLE_STEERING='1',
                       UNCLE_ARTIFACT_DELIVERY=delivery, FAKE_STRUCTURED='1' if structured else '0')
            env.pop('UNCLE_STATUS_FILE', None)
            env.pop('UNCLE_OUTPUT_SCHEMA_FILE', None)
            if schema:
                env['UNCLE_OUTPUT_SCHEMA_FILE'] = str(schema_file)
            done = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/native_stage.py'), '--runner', 'claude',
                                   '--side', 'reviewer', '--stage', 'final-audit-review-worker-verification', '--',
                                   'exec', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                                   '--output-last-message', str(output), 'Review it.'],
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=tmp, env=env, timeout=60)
            argv = json.loads((Path(tmp) / 'argv.json').read_text()) if (Path(tmp) / 'argv.json').exists() else []
            return done, argv, output.read_text() if output.exists() else None

    def test_a_schema_reaches_claude_and_the_packet_not_the_summary_is_the_output(self):
        done, argv, text = self.run_stage()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('--json-schema', argv)
        self.assertEqual(argv[argv.index('--json-schema') + 1], '{"type":"object","title":"packet"}')
        self.assertEqual(json.loads(text), {'schema': 'uncle.artifact/v1', 'kind': 'final-audit-worker-packet', 'findings': []})

    def test_the_reviewer_stays_read_only(self):
        _, argv, _ = self.run_stage()
        tools = argv[argv.index('--allowedTools') + 1]
        self.assertEqual(tools, 'Read,Glob,Grep')
        self.assertNotIn('Write', tools)

    def test_without_a_schema_nothing_changes(self):
        done, argv, text = self.run_stage(schema=False, structured=False)
        self.assertNotIn('--json-schema', argv)
        self.assertEqual(text, 'summary only, not the packet')

    def test_a_delivery_file_run_keeps_its_write_tool_and_gets_no_schema_flag(self):
        _, argv, _ = self.run_stage(delivery='/tmp/delivery.json')
        self.assertNotIn('--json-schema', argv)
        self.assertIn('Write', argv[argv.index('--allowedTools') + 1])

    def test_when_the_runner_reports_no_object_the_text_is_kept(self):
        _, _, text = self.run_stage(structured=False)
        self.assertEqual(text, 'summary only, not the packet')


if __name__ == '__main__':
    unittest.main()
