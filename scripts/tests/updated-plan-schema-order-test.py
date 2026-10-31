#!/usr/bin/env python3
"""Hermetic driver attempts: generic first, scoped only after semantic rejection."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import updated_plan_synthesis_prompt as prompt

NARRATIVE = '''# Project plan

## Observable behaviors

| ID | Trigger | Observable result | Failure behavior | Requirement IDs |
|---|---|---|---|---|
| B-1 | click | appended | unchanged | UB-1 |
| B-2 | key | same | same | UB-2 |

## Implementation order

1. **Scaffold** — Create package.json.
   Owns: `package.json`

2. **Core** — Create core.js.
   Owns: `src/core.js`, `tests/a.test.js`
   Depends on: 1

## Notes

Kept.
'''

STUB = '''import json, os, re, sys, time
from pathlib import Path
text, stage = Path(sys.argv[1]).read_text(), sys.argv[2]
root = Path('.uncle/workflow')
mode = os.environ['SCHEMA_TEST_MODE']
schema = json.loads(Path(os.environ['UNCLE_WORKER_SCHEMA_FILE']).read_text())
resolver = '-resolve-' in stage
record = root / ('attempts-' + stage + '.jsonl')
prior = [json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []
ops = (schema['properties']['resolutions']['items']['properties']['ops'] if resolver else schema['properties']['ops'])
variants = ops['items'].get('anyOf', [ops['items']])
strict = not any('enum' in variant.get('properties', {}).get('op', {}) for variant in variants)
with record.open('a') as out:
    out.write(json.dumps({'stage': stage, 'strict': strict, 'prompt': text, 'started': time.monotonic_ns()}) + '\\n')
if resolver:
    group = re.search(r'^## Group (G[0-9]+)', text, re.M).group(1)
    # Only G1 needs repair; G2 must survive untouched.
    invalid = mode == 'resolver-invalid' and group == 'G1' and not stage.endswith('-retry')
    if mode == 'resolver-transport' and group == 'G1' and not stage.endswith('-retry'):
        sys.exit(1)
    body = {'resolutions': [{'group': group, 'ops': [{'op': 'set_fields', 'id': 'B-999' if invalid else 'B-' + group[1:],
             'fields': {'failure': 'RESOLVED'}}]}]}
else:
    ids = re.search(r'You own exactly these findings: ([^.]*)\\.', text).group(1).split(', ')
    n = stage.split('-edits-')[1]
    if mode == 'writer-transport' and n == '1' and not prior:
        sys.exit(1)
    row = 'B-1' if 'AR-1' in ids else 'B-2'
    invalid = mode == 'writer-invalid' and 'AR-1' in ids and not prior and '-retry' not in stage
    if invalid:
        row = 'B-999'
    edits = [{'op': 'set_fields', 'id': row, 'fields': {'failure': 'UPDATED'}}]
    if mode.startswith('resolver-'):
        edits = [{'op': 'set_fields', 'id': 'B-' + str(i), 'fields': {'failure': n}} for i in (1, 2)]
    body = {'dispositions': [{'finding': i, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'} for i in ids],
            'ops': edits, 'protected_verification_paths': 'tests/a.test.js'}
    if mode == 'writer-insert':
        (root / ('started-' + n)).touch()
        deadline = time.monotonic() + 20
        while len(list(root.glob('started-*'))) < 2:
            if time.monotonic() > deadline:
                raise AssertionError('both writers must be active together')
            time.sleep(.01)
        body['ops'] = [{'op': 'insert_step', 'after': 'step-1', 'new': {
            'title': 'Added ' + n, 'text': 'Implement the finding.', 'owns': ['src/added-' + n + '.js'],
            'depends_on': ['step-2']}}]
Path(os.environ['UNCLE_WORKER_PACKET_PATH']).write_text(json.dumps(body))
'''


class AttemptOrder(unittest.TestCase):
    def run_driver(self, mode='ok', change=False, runner='local', config='', overrides=None):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            state = directory / '.uncle/workflow'
            (state / 'documents').mkdir(parents=True)
            (state / 'logs').mkdir()
            (directory / '.uncle/docs').mkdir()
            (directory / '.uncle/config').write_text(config)
            plan = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan' if change else 'plan',
                    'narrative': NARRATIVE, 'verification_commands': 'npm test',
                    'protected_verification_paths': 'tests/a.test.js'}
            review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                      'findings': [{'id': 'AR-%d' % n} for n in range(1, 7)]}
            (state / 'documents' / ('CHANGE_PLAN.json' if change else 'PROJECT_PLAN.json')).write_text(json.dumps(plan))
            (state / 'documents/ADVERSARIAL_REVIEW.json').write_text(json.dumps(review))
            workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
            (directory / 'prompt.md').write_text(prompt.prompt(plan, review, workers, change=change))
            driver = (ROOT / 'scripts' / ('change-workflow.sh' if change else 'stagegate.sh')).read_text()
            prefix = 'updated_change_plan' if change else 'updated_plan'
            wanted = [prefix + '_launch_writer', 'run_' + prefix + '_edit_writers']
            if not change:
                wanted.append('updated_plan_warm_prefix')
            functions = '\n'.join(re.search(r'^' + name + r'\(\) \{\n.*?^}', driver, re.M | re.S)[0] for name in wanted)
            (directory / 'functions.sh').write_text(functions)
            (directory / 'stub.py').write_text(STUB)
            (directory / 'run.sh').write_text('''#!/usr/bin/env bash
set -uo pipefail
STATE_DIR=.uncle/workflow
LOG_DIR="$STATE_DIR/logs"
UPDATED_PLAN_PROMPT="$PWD/prompt.md"
MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=
UPDATED_PLAN_ADVISOR_PIDS=()
stage_uses_self_hosted() { [[ "$SCHEMA_TEST_RUNNER" == local ]]; }
stage_supports_structured_output() { [[ "$SCHEMA_TEST_RUNNER" == hosted ]]; }
run_claude() { python3 -I "$PWD/stub.py" "$1" "$2"; }
. ./functions.sh
''' + 'run_' + prefix + '_edit_writers\n')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
            env.update(ROOT=str(ROOT), SCHEMA_TEST_MODE=mode, SCHEMA_TEST_RUNNER=runner,
                       WORKFLOW_UPDATED_PLAN_OPS='1', WORKFLOW_UPDATED_PLAN_EDITS='1',
                       WORKFLOW_UPDATED_PLAN_EDIT_SLICE='3', WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS='300',
                       WORKFLOW_SELF_HOSTED_STAGE_JOBS='2')
            env.update(overrides or {})
            run = subprocess.run(['bash', 'run.sh'], cwd=directory, env=env, capture_output=True, text=True, timeout=75)
            records = [json.loads(line) for path in sorted(state.glob('attempts-*.jsonl')) for line in path.read_text().splitlines()]
            records.sort(key=lambda row: row['started'])
            logs = '\n'.join(path.read_text() for path in (state / 'logs').glob('*.log'))
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr + logs)
            name = 'CHANGE_PLAN.md' if change else 'UPDATED_PROJECT_PLAN.md'
            self.assertTrue((directory / '.uncle/docs' / name).exists(), run.stdout + run.stderr)
            self.document = (directory / '.uncle/docs' / name).read_text()
            return records

    def test_concurrent_writer_insertions_publish_rewritten_dependencies(self):
        import plan_model
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_driver(mode='writer-insert', change=change)
                self.assertEqual(len(rows), 2)
                steps = plan_model.steps_of(plan_model.import_markdown(self.document))
                self.assertEqual([s['title'] for s in steps], ['Scaffold', 'Added 1', 'Added 2', 'Core'])
                self.assertEqual([s['depends_on'] for s in steps], [[], [4], [4], [1]])
                self.assertEqual([s['id'] for s in steps], ['step-1', 'step-2', 'step-3', 'step-4'])

    def test_default_writers_use_generic_on_both_drivers(self):
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_driver(change=change)
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(not row['strict'] for row in rows), rows)

    def test_invalid_writer_retries_only_that_group_with_precise_scoped_feedback(self):
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_driver(mode='writer-invalid', change=change)
                self.assertFalse(any('-resolve-' in row['stage'] for row in rows), rows)
                repaired = [row for row in rows if 'AR-1' in re.search(r'You own exactly these findings: ([^.]*)\.', row['prompt'])[1]]
                sibling = [row for row in rows if row not in repaired]
                self.assertEqual([row['strict'] for row in repaired], [False, True], rows)
                self.assertIn('B-999', repaired[1]['prompt'])
                self.assertEqual(len(sibling), 1)
                self.assertFalse(sibling[0]['strict'])

    def test_resolver_retries_only_rejected_group_with_strict_schema(self):
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_driver(mode='resolver-invalid', change=change)
                group1 = [row for row in rows if '-resolve-G1' in row['stage']]
                group2 = [row for row in rows if '-resolve-G2' in row['stage']]
                self.assertEqual([row['strict'] for row in group1], [False, True], rows)
                self.assertIn('B-999', group1[1]['prompt'])
                self.assertEqual([row['strict'] for row in group2], [False])
                self.assertTrue(all(not row['strict'] for row in rows if '-edits-' in row['stage']))

    def test_transport_failures_do_not_enable_strict_schema(self):
        for change in (False, True):
            for mode in ('writer-transport', 'resolver-transport'):
                with self.subTest(change=change, mode=mode):
                    rows = self.run_driver(mode=mode, change=change)
                    self.assertGreater(len(rows), 2)
                    self.assertTrue(all(not row['strict'] for row in rows), rows)

    def test_hosted_runners_keep_scoped_schema(self):
        for change in (False, True):
            for runner in ('hosted', 'file'):
                with self.subTest(change=change, runner=runner):
                    rows = self.run_driver(change=change, runner=runner)
                    self.assertEqual(len(rows), 2)
                    self.assertTrue(all(row['strict'] for row in rows))

    def test_config_always_and_env_override_use_existing_precedence(self):
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_driver(change=change, config='updated-plan.strict-schema always\n')
                self.assertTrue(all(row['strict'] for row in rows))
                rows = self.run_driver(change=change, config='updated-plan.strict-schema always\n',
                                       overrides={'WORKFLOW_UPDATED_PLAN_STRICT_SCHEMA': 'retry'})
                self.assertTrue(all(not row['strict'] for row in rows))

    def test_change_stage_setting_overrides_family_and_env_overrides_config(self):
        config = 'updated-plan.strict-schema always\nupdated-change-plan.strict-schema retry\n'
        rows = self.run_driver(change=True, config=config)
        self.assertTrue(all(not row['strict'] for row in rows))
        rows = self.run_driver(change=True, config=config, overrides={'WORKFLOW_UPDATED_PLAN_STRICT_SCHEMA': 'always'})
        self.assertTrue(all(row['strict'] for row in rows))
        rows = self.run_driver(change=True, config=config, overrides={
            'WORKFLOW_UPDATED_PLAN_STRICT_SCHEMA': 'always', 'WORKFLOW_UPDATED_CHANGE_PLAN_STRICT_SCHEMA': 'retry'})
        self.assertTrue(all(not row['strict'] for row in rows))


if __name__ == '__main__':
    unittest.main()
