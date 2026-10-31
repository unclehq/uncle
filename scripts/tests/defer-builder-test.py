#!/usr/bin/env python3
"""Finding clocks, selective rollback and structural exhaustion without models."""
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
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import updated_plan_defer as defer
import updated_plan_ops as ops
import updated_plan_edits as edits
import plan_model as pm

spec = importlib.util.spec_from_file_location('order_fixture', ROOT / 'scripts/tests/updated-plan-schema-order-test.py')
order = importlib.util.module_from_spec(spec)
spec.loader.exec_module(order)


class Deferral(unittest.TestCase):
    def test_finding_clock_survives_splitting_and_resolver_attempts(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'UNCLE_CONFIG': tmp + '/config'}, clear=True):
            with patch.object(defer.time, 'monotonic', return_value=100):
                self.assertEqual(defer.remaining(tmp, 'AR-1,AR-2', 'updated-plan'), 360)
            with patch.object(defer.time, 'monotonic', return_value=300):
                self.assertEqual(defer.remaining(tmp, 'AR-2', 'updated-plan-worker-edits-1-2'), 160)
            with patch.object(defer.time, 'monotonic', return_value=470):
                self.assertEqual(defer.remaining(tmp, 'AR-1,AR-2', 'updated-plan-worker-resolve-G1'), 0)

    def test_worker_and_change_options_override_family_with_env_first(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'UNCLE_CONFIG': tmp + '/config'}, clear=True):
            Path(tmp, 'config').write_text('updated-plan.finding-seconds 10\nupdated-change-plan.finding-seconds 20\n')
            stage = 'updated-change-plan-worker-edits-2'
            self.assertEqual(defer.option(stage, 'finding-seconds', 360), '20')
            with patch.dict(os.environ, WORKFLOW_UPDATED_PLAN_FINDING_SECONDS='30'):
                self.assertEqual(defer.option(stage, 'finding-seconds', 360), '30')
                with patch.dict(os.environ, WORKFLOW_UPDATED_PLAN_FINDING_SECONDS_UPDATED_CHANGE_PLAN_WORKER_EDITS_2='40'):
                    self.assertEqual(defer.option(stage, 'finding-seconds', 360), '40')

    def fixture(self, root):
        state = root / '.uncle/workflow'
        directory = state / 'updated-plan-edits'
        for path in (directory / 'prompts', state / 'documents', state / 'logs', root / '.uncle/docs'):
            path.mkdir(parents=True, exist_ok=True)
        plan = dict(schema='uncle.artifact/v1', kind='plan', narrative=order.NARRATIVE,
                    verification_commands='true', protected_verification_paths='tests/a.test.js')
        (directory / 'base-plan.json').write_text(json.dumps(plan))
        (state / 'documents/PROJECT_PLAN.json').write_text(json.dumps(plan))
        (directory / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n')
        return state, directory, plan

    def packet(self, directory, name, operation):
        Path(directory, name + '.json').write_text(json.dumps(dict(ops=[operation], dispositions=[dict(
            finding='AR-' + name, disposition='Accepted', reason='test', plan_change='changed')], commands_replace=[])))

    def test_structural_exhaustion_reverts_implicated_packet_and_keeps_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state, directory, plan = self.fixture(root)
            model = ops.plan_model_of(plan)
            step = next(s for s in ops.implementation_steps(model) if 'tests/a.test.js' in s['owns'])
            self.packet(directory, '1', dict(op='set_fields', id='B-1', fields={'failure': 'SIBLING-KEPT'}))
            operation = ops.ownership_edit(step, ['src/core.js'])
            self.packet(directory, '2', operation)
            env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
            env.update(ROOT=str(ROOT), STATE_DIR=str(state), LOG_DIR=str(state / 'logs'), UNCLE_CONFIG=str(root / 'config'))
            script = '''
set -e
python3 -B "$ROOT/scripts/lib/updated_plan_ops.py" merge "$STATE_DIR/updated-plan-edits/base-plan.json" "$STATE_DIR/updated-plan-edits/slices.tsv" "$STATE_DIR/updated-plan-edits" "$STATE_DIR/updated-plan-edits/merged.json"
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { return 1; }
run_claude() {
    echo called >> "$STATE_DIR/calls"
    echo '{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-ops-packet","dispositions":[],"ops":[{"op":"set_step","id":"missing-step","fields":{"owns":"tests/a.test.js"}}]}' > "$UNCLE_WORKER_PACKET_PATH"
}
workflow_publish_updated_plan updated-plan "$STATE_DIR/updated-plan-edits"
'''
            result = subprocess.run(['bash', '-c', script], cwd=root, env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((state / 'calls').read_text().splitlines(), ['called', 'called'])
            revised = json.loads((state / 'documents/UPDATED_PROJECT_PLAN.json').read_text())
            rows = {row['finding']: row for row in revised['dispositions']}
            self.assertEqual(rows['AR-2']['disposition'], 'Deferred')
            self.assertIn('missing-step', rows['AR-2']['reason'])
            self.assertEqual(rows['AR-1']['disposition'], 'Accepted')
            self.assertIn('SIBLING-KEPT', revised['narrative'])
            self.assertIn('tests/a.test.js', revised['narrative'])
            self.assertFalse((state / 'updated-plan-writers-exhausted').exists())

    def test_resolver_rollback_rebinds_surviving_group_answers(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'UNCLE_CONFIG': tmp + '/config'}, clear=True):
            root = Path(tmp)
            state, directory, plan = self.fixture(root)
            (directory / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n3\tAR-3\n4\tAR-4\n')
            for name, target in [('1', 'B-1'), ('2', 'B-1'), ('3', 'B-2'), ('4', 'B-2')]:
                self.packet(directory, name, dict(op='set_fields', id=target, fields={'failure': name}))
            with self.assertRaises(edits.NeedsResolution):
                ops.merge(directory / 'base-plan.json', directory / 'slices.tsv', directory, directory / 'merged.json')
            groups = json.loads((directory / 'conflicts.json').read_text())
            failed = next(g for g in groups if g['edits'][0]['writer'] == '1')
            good = next(g for g in groups if g['edits'][0]['writer'] == '3')
            (directory / ('resolutions-' + good['id'] + '.json')).write_text(json.dumps(dict(resolutions=[dict(
                group=good['id'], ops=[dict(op='set_fields', id='B-2', fields={'failure': 'RESOLVED-KEPT'})])])))
            defer.resolver_defer(directory, [failed['id']], 'updated-plan', directory / 'base-plan.json', 'updated_plan_ops.py')
            merged = json.loads((directory / 'merged.json').read_text())
            rows = {row['finding']: row for row in merged['dispositions']}
            self.assertEqual([rows['AR-' + str(i)]['disposition'] for i in range(1, 5)], ['Deferred', 'Deferred', 'Accepted', 'Accepted'])
            self.assertIn('RESOLVED-KEPT', json.dumps(merged['patch']))


if __name__ == '__main__':
    unittest.main()
