#!/usr/bin/env python3
"""The run-19 heading-step false gap and bounded ownership repair stay recoverable."""
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
import artifact_json
import plan_model as pm
import plan_ownership_gap as ownership
import updated_plan_ops as ops
from self_hosted_http import conforms

FIXTURE = Path(__file__).with_name('fixtures') / 'run19-structure-scope.json'


class StructureScope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docs = self.root / '.uncle/docs'
        self.docs.mkdir(parents=True)
        self.state = self.root / '.uncle/workflow'
        (self.state / 'documents').mkdir(parents=True)
        (self.state / 'logs').mkdir()
        self.plan = self.state / 'documents/UPDATED_PROJECT_PLAN.json'
        self.view = self.docs / 'UPDATED_PROJECT_PLAN.md'
        self.repair = self.state / 'updated-plan-structure-repair'
        env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
        env['UNCLE_CONFIG'] = str(self.root / 'config')
        environment = patch.dict(os.environ, env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def write_plan(self, plan, model=None):
        self.plan.write_text(json.dumps(plan))
        (self.state / 'documents/PROJECT_PLAN.json').write_text(json.dumps(plan))
        self.view.write_text(artifact_json.render_plan(plan, protected=True))
        if model is not None:
            pm.sidecar(self.plan).write_text(json.dumps(model))

    def fixture(self):
        return json.loads(FIXTURE.read_text())

    def typed_plan(self):
        return {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'dispositions': [],
                'narrative': '# Plan\n\n## Implementation order\n\n'
                '1. **Core** — Write core.\n   Owns: `src/core.js`\n\n'
                '2. **UI** — Write UI.\n   Owns: `src/ui.js`\n',
                'verification_commands': 'npm test', 'protected_verification_paths': 'tests/unknown.test.js'}

    def test_fixture_captures_empty_scope_and_nonexistent_step_in_the_real_packet(self):
        fixture = self.fixture()
        self.assertEqual(fixture['scope']['ids'], [])
        self.assertEqual(fixture['automatic_ops'], [])
        self.assertEqual(fixture['packet']['ops'][0]['id'], 'step-3')
        self.assertNotIn('step-3', pm.index(fixture['model']))
        self.assertEqual(len(fixture['scope']['gaps']), 4)

    def test_real_heading_owned_paths_are_not_reported_as_gaps(self):
        fixture = self.fixture()
        self.write_plan(fixture['plan'], fixture['model'])
        self.assertEqual(ownership.unowned_protected_paths(
            self.view, self.root, fixture['scope']['gaps'], self.state), [])

    def test_real_run19_repairs_without_a_model_or_changing_document_layout(self):
        fixture = self.fixture()
        self.write_plan(fixture['plan'], fixture['model'])
        status = ops.prepare_structure_repair(self.plan, self.root, self.repair, fixture['scope']['problem'])
        self.assertEqual(status, 0)
        repaired = json.loads((self.repair / 'repaired.json').read_text())
        self.assertEqual(repaired['narrative'], fixture['plan']['narrative'])
        self.assertEqual(repaired['protected_verification_paths'], fixture['plan']['protected_verification_paths'])
        self.view.write_text(artifact_json.render_plan(repaired, protected=True))
        self.assertEqual(ownership.unowned_protected_paths(
            self.view, self.root, fixture['scope']['gaps'], self.state), [])

    def test_typed_candidate_owners_are_in_scope_and_dot_paths_are_normalized(self):
        plan = self.typed_plan()
        self.write_plan(plan)
        self.assertEqual(ops.prepare_structure_repair(self.plan, self.root, self.repair,
                         'a protected verification path with no owning implementation step'), 3)
        scope = json.loads((self.repair / 'scope.json').read_text())
        self.assertTrue({'step-1', 'step-2'} <= set(scope['ids']))
        for owns in ('./src/ui.js, ./tests/unknown.test.js', ['./src/ui.js', './tests/unknown.test.js']):
            with self.subTest(owns=owns):
                packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                          'dispositions': [], 'ops': [{'op': 'set_step', 'id': 'step-2',
                          'fields': {'owns': owns}}]}
                (self.repair / 'packet.json').write_text(json.dumps(packet))
                ops.apply_structure_repair(self.repair, self.root)
                repaired = json.loads((self.repair / 'repaired.json').read_text())
                self.plan.write_text(json.dumps(repaired))
                self.view.write_text(artifact_json.render_plan(repaired, protected=True))
                self.assertEqual(ownership.unowned_protected_paths(
                    self.view, self.root, ['tests/unknown.test.js']), [])
                self.assertIn('`src/ui.js`', repaired['narrative'])
                self.assertNotIn('./tests/unknown.test.js', repaired['narrative'])

    def test_legacy_ownership_packet_cannot_hide_unrelated_operation_fields(self):
        self.write_plan(self.typed_plan())
        self.assertEqual(ops.prepare_structure_repair(self.plan, self.root, self.repair,
                         'a protected verification path with no owning implementation step'), 3)
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                  'dispositions': [], 'ops': [{'op': 'set_step', 'id': 'step-1',
                  'fields': {'owns': 'src/core.js, tests/unknown.test.js'}, 'text': 'Unrelated replacement'}]}
        (self.repair / 'packet.json').write_text(json.dumps(packet))
        with self.assertRaises(ops.Conflict):
            ops.apply_structure_repair(self.repair, self.root)

    def test_only_unowned_protected_paths_can_be_removed_during_repair(self):
        plan = self.typed_plan()
        plan['protected_verification_paths'] = 'src/core.js\ntests/unknown.test.js'
        self.write_plan(plan)
        self.assertEqual(ops.prepare_structure_repair(self.plan, self.root, self.repair,
                         'a protected verification path with no owning implementation step'), 3)
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                  'dispositions': [], 'ops': [], 'protected_verification_paths': ''}
        (self.repair / 'packet.json').write_text(json.dumps(packet))
        with self.assertRaises(ops.Conflict):
            ops.apply_structure_repair(self.repair, self.root)
        packet['protected_verification_paths'] = 'src/core.js'
        (self.repair / 'packet.json').write_text(json.dumps(packet))
        ops.apply_structure_repair(self.repair, self.root)
        repaired = json.loads((self.repair / 'repaired.json').read_text())
        self.assertEqual(repaired['protected_verification_paths'], 'src/core.js')
        self.assertEqual(repaired['verification_commands'], plan['verification_commands'])
        self.assertEqual(repaired['dispositions'], plan['dispositions'])
        self.assertEqual(repaired['narrative'], plan['narrative'])

    def test_out_of_scope_delivery_gets_one_retry_with_the_reason(self):
        self.write_plan(self.typed_plan())
        script = self.root / 'driver.sh'
        script.write_text('''#!/usr/bin/env bash
set -euo pipefail
ROOT="$1"
STATE_DIR=.uncle/workflow
LOG_DIR="$STATE_DIR/logs"
. "$ROOT/scripts/lib/updated-plan-repair.sh"
run_claude() {
    printf 'call\\n' >> "$STATE_DIR/calls"
    if [[ "$(wc -l < "$STATE_DIR/calls" | tr -d ' ')" == 1 ]]; then
        printf '%s\\n' '{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-ops-packet","dispositions":[],"ops":[{"op":"set_step","id":"missing-step","fields":{"owns":"tests/unknown.test.js"}}]}' > "$UNCLE_WORKER_PACKET_PATH"
    else
        grep -q 'outside.*scope' "$1"
        printf '%s\\n' '{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-ops-packet","dispositions":[],"ops":[{"op":"set_step","id":"step-1","fields":{"owns":"src/core.js, tests/unknown.test.js"}}]}' > "$UNCLE_WORKER_PACKET_PATH"
    fi
}
run_updated_plan_structure_repair "$STATE_DIR/documents/UPDATED_PROJECT_PLAN.json" \\
    'a protected verification path with no owning implementation step' updated-plan
''')
        result = subprocess.run(['bash', str(script), str(ROOT)], cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.state / 'calls').read_text().splitlines(), ['call', 'call'])
        self.assertEqual(ownership.unowned_protected_paths(
            self.view, self.root, ['tests/unknown.test.js'], self.state), [])

    def test_repair_schema_permits_every_candidate_and_only_ownership_fields(self):
        self.write_plan(self.typed_plan())
        ops.prepare_structure_repair(self.plan, self.root, self.repair, 'no owning implementation step')
        schema = json.loads((self.repair / 'schema.json').read_text())
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                  'dispositions': [], 'ops': [], 'protected_verification_paths': ''}
        for identifier in ('step-1', 'step-2'):
            packet['ops'] = [{'op': 'set_step', 'id': identifier, 'fields': {'owns': ['tests/unknown.test.js']}}]
            conforms(packet, schema)
            packet['ops'][0]['fields']['title'] = 'Unrelated rename'
            with self.assertRaises(ValueError):
                conforms(packet, schema)

    def test_only_unowned_protected_paths_may_be_removed(self):
        plan = self.typed_plan()
        plan['protected_verification_paths'] += '\nsrc/core.js'
        self.write_plan(plan)
        ops.prepare_structure_repair(self.plan, self.root, self.repair, 'no owning implementation step')
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                  'dispositions': [], 'ops': [], 'protected_verification_paths': ''}
        (self.repair / 'packet.json').write_text(json.dumps(packet))
        with self.assertRaisesRegex(ops.Conflict, 'unrelated verification'):
            ops.apply_structure_repair(self.repair, self.root)
        packet['protected_verification_paths'] = 'src/core.js'
        (self.repair / 'packet.json').write_text(json.dumps(packet))
        ops.apply_structure_repair(self.repair, self.root)
        repaired = json.loads((self.repair / 'repaired.json').read_text())
        self.assertEqual(repaired['protected_verification_paths'], 'src/core.js')
        self.assertEqual(repaired['narrative'], plan['narrative'])

    def test_retry_is_bounded_and_receives_the_candidate_schema(self):
        self.write_plan(self.typed_plan())
        script = '''set -euo pipefail
ROOT="$1"
STATE_DIR=.uncle/workflow
LOG_DIR="$STATE_DIR/logs"
. "$ROOT/scripts/lib/updated-plan-repair.sh"
run_claude() {
    test -s "$UNCLE_WORKER_SCHEMA_FILE"
    printf 'call\\n' >> "$STATE_DIR/calls"
    printf '%s\\n' '{"schema":"uncle.artifact/v1","kind":"updated-plan-edit-ops-packet","dispositions":[],"ops":[{"op":"set_step","id":"missing-step","fields":{"owns":"tests/unknown.test.js"}}]}' > "$UNCLE_WORKER_PACKET_PATH"
}
run_updated_plan_structure_repair "$STATE_DIR/documents/UPDATED_PROJECT_PLAN.json" 'no owning implementation step' updated-plan
'''
        result = subprocess.run(['bash', '-c', script, 'test', str(ROOT)], cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside its scope: missing-step', result.stderr)
        self.assertEqual((self.state / 'calls').read_text().splitlines(), ['call', 'call'])


if __name__ == '__main__':
    unittest.main()
