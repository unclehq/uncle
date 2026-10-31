#!/usr/bin/env python3
"""Run-24 regressions: exhausted edits become visible, bounded deferrals."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import artifact_json
import envelope
import plan_model
import updated_plan_synthesis_prompt as prompt


def fixture(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts/tests' / (name + '-test.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


order = fixture('updated-plan-schema-order')

STUB = r'''import json, os, re, sys, time
from pathlib import Path
text, stage = Path(sys.argv[1]).read_text(), sys.argv[2]
state = Path('.uncle/workflow')
mode = os.environ['DEFER_TEST_MODE']
resolver = '-resolve-' in stage
ids = [] if resolver else re.search(r'You own exactly these findings: ([^.]*)\.', text).group(1).split(', ')
with (state / 'calls.jsonl').open('a') as f:
    f.write(json.dumps({'stage': stage, 'ids': ids, 'time': time.monotonic()}) + '\n')
if resolver:
    if mode == 'resolver':
        print('B-999: resolver cannot apply the overlapping edit', flush=True)
        sys.exit(2)
    print('s3.1 is not a typed rows block', flush=True)
    sys.exit(2)
if 'AR-022' in ids:
    if mode == 'slow':
        print('begin slow finding', flush=True)
        time.sleep(20)
        (state / 'late-child-write').touch()
    if mode in ('transport', 'slow'):
        print('s3.1 is not a typed rows block', flush=True)
        sys.exit(2)
    if mode == 'semantic':
        ops = [{'op': 'insert_row', 'target': 's3.1', 'after': '', 'new': {'id': 'T-022', 'text': 'Add defect injection'}}]
    else:
        ops = [{'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'CONFLICT-022'}}]
elif 'AR-023' in ids:
    ops = [{'op': 'set_fields', 'id': 'B-1', 'fields': {'failure': 'CONFLICT-023'}}]
elif any(i in ids for i in ('AR-002', 'AR-003')):
    ops = []
else:
    ops = [{'op': 'set_fields', 'id': 'B-2', 'fields': {'failure': 'SIBLING-APPLIED'}}]
body = {'dispositions': [{'finding': i, 'disposition': 'Accepted', 'reason': 'apply', 'plan_change': 'row'} for i in ids],
        'ops': ops, 'protected_verification_paths': 'tests/a.test.js'}
Path(os.environ['UNCLE_WORKER_PACKET_PATH']).write_text(json.dumps(body))
'''


class DeferredDrivers(unittest.TestCase):
    def run_driver(self, change=False, mode='transport', runner='local', severity='High', config='', overrides=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / '.uncle/workflow'
        (state / 'documents').mkdir(parents=True)
        (state / 'logs').mkdir()
        (root / '.uncle/docs').mkdir()
        (root / '.uncle/config').write_text(config)
        plan = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan' if change else 'plan',
                'narrative': order.NARRATIVE, 'verification_commands': 'true',
                'protected_verification_paths': 'tests/a.test.js'}
        ids = ['AR-001', 'AR-002', 'AR-003', 'AR-022'] + (['AR-023'] if mode == 'resolver' else [])
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                  'findings': [{'id': i, 'severity': severity, 'title': 'Add defect injection row',
                                'failure': 'test missing', 'fix': 'add a row', 'references': 'Notes',
                                'verify': 'test the failure'} for i in ids]}
        (state / 'documents' / ('CHANGE_PLAN.json' if change else 'PROJECT_PLAN.json')).write_text(json.dumps(plan))
        (state / 'documents/ADVERSARIAL_REVIEW.json').write_text(json.dumps(review))
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        (root / 'prompt.md').write_text(prompt.prompt(plan, review, workers, change=change))
        (root / 'stub.py').write_text(STUB)
        prefix = 'updated_change_plan' if change else 'updated_plan'
        driver = (ROOT / 'scripts' / ('change-workflow.sh' if change else 'stagegate.sh')).read_text()
        names = [prefix + '_launch_writer', 'run_' + prefix + '_edit_writers']
        if not change:
            names.append('updated_plan_warm_prefix')
        functions = '\n'.join(re.search(r'^' + name + r'\(\) \{\n.*?^}', driver, re.M | re.S)[0] for name in names)
        script = functions + r'''
UPDATED_PLAN_PROMPT="$PWD/prompt.md"
MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=
UPDATED_PLAN_ADVISOR_PIDS=()
stage_uses_self_hosted() { [[ "$DEFER_TEST_RUNNER" == local ]]; }
stage_supports_structured_output() { [[ "$DEFER_TEST_RUNNER" == hosted ]]; }
run_claude() { python3 -I "$PWD/stub.py" "$1" "$2"; }
''' + 'run_' + prefix + '_edit_writers\n'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('WORKFLOW_', 'UNCLE_'))}
        env.update(ROOT=str(ROOT), STATE_DIR=str(state), LOG_DIR=str(state / 'logs'),
                   UNCLE_PROJECT_ROOT=str(root), UNCLE_CONFIG=str(root / '.uncle/config'),
                   DEFER_TEST_MODE=mode, DEFER_TEST_RUNNER=runner,
                   WORKFLOW_UPDATED_PLAN_EDIT_SLICE='1', WORKFLOW_UPDATED_PLAN_HEDGE_SECONDS='300',
                   WORKFLOW_PREFIX_WARM_SECONDS='0', WORKFLOW_SELF_HOSTED_STAGE_JOBS='3')
        env.update(overrides or {})
        started = time.monotonic()
        result = subprocess.run(['bash', '-c', script], cwd=root, env=env,
                                capture_output=True, text=True, timeout=75)
        elapsed = time.monotonic() - started
        self.assertTrue((state / 'calls.jsonl').exists(), result.stdout + result.stderr)
        records = [json.loads(line) for line in (state / 'calls.jsonl').read_text().splitlines()]
        return root, result, records, elapsed

    def assert_published(self, root, result, change=False, cause='typed rows block', deferred=('AR-022',)):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = root / '.uncle/workflow'
        name = 'CHANGE_PLAN' if change else 'UPDATED_PROJECT_PLAN'
        canonical = json.loads((state / ('documents/' + name + '.json')).read_text())
        markdown = (root / ('.uncle/docs/' + name + '.md')).read_text()
        rows = {r['finding']: r for r in canonical['dispositions']}
        self.assertEqual(rows['AR-001']['disposition'], 'Accepted')
        self.assertIn('SIBLING-APPLIED', markdown)
        self.assertEqual(len(rows), 3 + len(deferred))
        for finding in deferred:
            self.assertEqual(rows[finding]['disposition'], 'Deferred', rows)
            self.assertIn(cause.lower(), rows[finding]['reason'].lower())
            self.assertIn('review by hand', rows[finding]['reason'].lower())
            self.assertRegex(markdown, r'\|\s*' + finding + r'\s*\|\s*Deferred\s*\|')
            self.assertRegex(result.stdout + result.stderr, finding + r'[^\n]*[Dd]eferred|[Dd]eferred[^\n]*' + finding)
        self.assertNotIn('CONFLICT-022', markdown)
        self.assertNotIn('CONFLICT-023', markdown)
        self.assertNotIn('T-022', markdown)
        self.assertFalse((state / 'updated-plan-writers-exhausted').exists())
        self.assertFalse((state / 'stop-reason').exists())
        logs = '\n'.join(p.read_text() for p in (state / 'logs').glob('UPDATED_PLAN*.log'))
        for finding in deferred:
            self.assertIn(finding, logs)
            self.assertIn('Deferred', logs)
        self.assertRegex(result.stdout + result.stderr, r'(?i)(deferred[^\n]*\b%d\b|\b%d\b[^\n]*deferred)' % (len(deferred), len(deferred)))
        return canonical, markdown

    def test_run24_exhaustion_publishes_sibling_and_visible_deferral_for_both_drivers(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result, calls, _ = self.run_driver(change=change)
                self.assert_published(root, result, change)
                self.assertEqual(sum('AR-001' in c['ids'] for c in calls), 1)
                self.assertEqual(sum('AR-022' in c['ids'] for c in calls), 3)

    def test_schema_rejection_exhaustion_is_also_deferred(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result, calls, _ = self.run_driver(change=change, mode='semantic')
                self.assert_published(root, result, change)
                self.assertGreaterEqual(sum('AR-022' in c['ids'] for c in calls), 3)

    def test_hosted_and_file_runners_defer_after_their_bounded_attempts(self):
        for change in (False, True):
            for runner in ('hosted', 'file'):
                with self.subTest(change=change, runner=runner):
                    root, result, calls, _ = self.run_driver(change=change, runner=runner)
                    self.assert_published(root, result, change)
                    self.assertEqual(sum('AR-022' in c['ids'] for c in calls), 3)

    def test_exhausted_resolvers_defer_only_the_conflicting_findings(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result, calls, _ = self.run_driver(change=change, mode='resolver')
                self.assert_published(root, result, change, cause='resolver', deferred=('AR-022', 'AR-023'))
                self.assertEqual(sum('AR-001' in c['ids'] for c in calls), 1)
                self.assertEqual(sum('-resolve-' in c['stage'] for c in calls), 3)

    def test_critical_deferred_rows_pass_the_existing_disposition_gate(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result, _, _ = self.run_driver(change=change, severity='CRITICAL')
                _, markdown = self.assert_published(root, result, change)
                review = '\n'.join('## %s: Missing test\n\n- Severity: CRITICAL\n' % i for i in ('AR-001', 'AR-022'))
                self.assertEqual(envelope.undispositioned(review, markdown), [])
                (root / 'review.md').write_text(review)
                gate = subprocess.run([sys.executable, '-I', str(ROOT / 'scripts/lib/envelope.py'),
                    'plan-gate', str(root / 'review.md'), str(root / ('.uncle/docs/CHANGE_PLAN.md' if change else '.uncle/docs/UPDATED_PROJECT_PLAN.md'))],
                    capture_output=True, text=True)
                self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

    def test_disabling_deferral_keeps_terminal_exhaustion(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result, calls, _ = self.run_driver(change=change, config='updated-plan.defer-unapplied off\n')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue((root / '.uncle/workflow/updated-plan-writers-exhausted').exists())
                self.assertEqual(sum('AR-022' in c['ids'] for c in calls), 3)

    def test_noncritical_policy_refuses_critical_but_accepts_high(self):
        for change in (False, True):
            for severity in ('CRITICAL', 'High'):
                with self.subTest(change=change, severity=severity):
                    root, result, _, _ = self.run_driver(change=change, severity=severity,
                        config='updated-plan.defer-unapplied non-critical\n')
                    if severity == 'CRITICAL':
                        self.assertNotEqual(result.returncode, 0)
                        self.assertTrue((root / '.uncle/workflow/updated-plan-writers-exhausted').exists())
                    else:
                        self.assert_published(root, result, change)

    def test_stage_config_and_environment_override_family_deferral_policy(self):
        root, result, _, _ = self.run_driver(change=True,
            config='updated-plan.defer-unapplied off\nupdated-change-plan.defer-unapplied on\n')
        self.assert_published(root, result, True)
        root, result, _, _ = self.run_driver(change=True,
            config='updated-plan.defer-unapplied off\nupdated-change-plan.defer-unapplied off\n',
            overrides={'WORKFLOW_UPDATED_PLAN_DEFER_UNAPPLIED': 'on'})
        self.assert_published(root, result, True)
        root, result, _, _ = self.run_driver(change=True,
            overrides={'WORKFLOW_UPDATED_PLAN_DEFER_UNAPPLIED': 'off',
                       'WORKFLOW_UPDATED_CHANGE_PLAN_DEFER_UNAPPLIED': 'on'})
        self.assert_published(root, result, True)

    def test_per_finding_wall_cap_stops_the_child_and_skips_expired_retries(self):
        for change in (False, True):
            for runner in ('local', 'file'):
                with self.subTest(change=change, runner=runner):
                    root, result, calls, elapsed = self.run_driver(change=change, mode='slow', runner=runner,
                        overrides={'WORKFLOW_UPDATED_PLAN_FINDING_SECONDS': '2'})
                    self.assert_published(root, result, change, cause='wall')
                    self.assertLess(elapsed, 12)
                    self.assertEqual(sum('AR-022' in c['ids'] for c in calls), 1)
                    self.assertFalse((root / '.uncle/workflow/late-child-write').exists())


class PreflightStops(unittest.TestCase):
    def test_readonly_violation_still_refuses_speculative_adoption(self):
        previous = fixture('fast4-regressions')
        case = previous.RestartPaths('test_speculative_readonly_violation_stops_without_restart')
        result = unittest.TestResult()
        case.run(result)
        self.assertEqual(result.errors + result.failures, [])


if __name__ == '__main__':
    unittest.main()
