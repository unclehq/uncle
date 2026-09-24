#!/usr/bin/env python3
"""Regression coverage for the JSON-only updated-plan worker boundary."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts/lib' / name)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


PACKETS = load('updated_plan_worker_packets.py')
WORKERS = load('worker_packets.py')
OUTPUT = load('reviewer_output.py')
SELF_HOSTED = load('self_hosted.py')


def packet(identifier='AR-001', evidence='evidence', correction='correct it'):
    return {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packet', 'findings': [{
        'id': identifier, 'gap': 'gap', 'evidence': evidence, 'risk': 'risk',
        'required_correction': correction}]}


class WorkerPackets(unittest.TestCase):
    def write(self, directory, name, value):
        (directory / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')

    def test_four_packets_are_ordered_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); output = directory / 'combined.json'
            for name, ident in zip(('dispositions', 'ownership', 'verification', 'scope'),
                                   ('AR-004', 'AR-002', 'AR-003', 'AR-001')):
                self.write(directory, name, packet(ident, name))
            result = PACKETS.collate(directory, output, ('dispositions', 'ownership', 'verification', 'scope'))
            self.assertEqual([item['id'] for item in result['findings']], ['AR-001', 'AR-002', 'AR-003', 'AR-004'])
            self.assertEqual(len(result['workers']), 4)

    def test_duplicate_preserves_every_source_and_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.write(directory, 'scope', packet(evidence='scope proof', correction='narrow scope'))
            self.write(directory, 'verification', packet(evidence='test proof', correction='add test'))
            result = PACKETS.collate(directory, directory / 'out.json', ('scope', 'verification'))
            finding = result['findings'][0]
            self.assertEqual(finding['sources'], ['scope', 'verification'])
            self.assertEqual(finding['evidence'], ['scope proof', 'test proof'])
            self.assertTrue(finding['conflicting_corrections'])

    def test_missing_and_malformed_packets_name_the_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with self.assertRaisesRegex(PACKETS.PacketError, 'ownership.json: worker packet is missing'):
                PACKETS.collate(directory, directory / 'out.json', ('ownership',))
            (directory / 'scope.json').write_text('{bad', encoding='utf-8')
            with self.assertRaisesRegex(PACKETS.PacketError, 'scope.json: invalid JSON'):
                PACKETS.collate(directory, directory / 'out.json', ('scope',))

    def test_every_reviewer_path_accepts_a_json_packet(self):
        body = json.dumps(packet())
        self.assertEqual(json.loads(OUTPUT.check(body, 'claude'))['kind'], 'updated-plan-worker-packet')
        self.assertEqual(json.loads(OUTPUT.check(body, 'kimi'))['kind'], 'updated-plan-worker-packet')
        self.assertEqual(json.loads(OUTPUT.check(body, 'cline'))['kind'], 'updated-plan-worker-packet')
        self.assertEqual(json.loads(SELF_HOSTED.reviewer_packet(body, 'packet.json'))['kind'], 'updated-plan-worker-packet')
        for runner in ('reviewer-claude.sh', 'reviewer-kimi.sh', 'reviewer-cline.sh'):
            self.assertIn('reviewer_output.py', (ROOT / 'scripts' / runner).read_text())
        for driver in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            self.assertIn('reviewer_output.py" --packet', (ROOT / driver).read_text())

    def test_self_hosted_reviewer_recovers_unfenced_packet_after_narration(self):
        response = 'The dispositions are complete. ' + json.dumps(packet())
        result = json.loads(SELF_HOSTED.reviewer_packet(response, 'packet.json'))
        self.assertEqual(result['kind'], 'updated-plan-worker-packet')

    def test_parents_only_receive_collated_packet(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT / source).read_text()
            start = text.index('run_updated_plan_panel()' if source.endswith('stagegate.sh') else 'run_updated_change_plan_panel()')
            block = text[start:text.index('\n}\n', start) + 2]
            self.assertIn('UPDATED_PLAN_WORKERS.json' if source.endswith('stagegate.sh') else 'UPDATED_CHANGE_PLAN_WORKERS.json', block)
            self.assertIn('Do not read the worker directory', block)

    def test_generic_panel_packets_are_deduplicated_and_worker_specific(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            kind = 'adversarial-review-worker-packet'
            first = {'schema': 'uncle.artifact/v1', 'kind': kind,
                     'findings': [{'id': 'AR-001', 'summary': 'scope gap', 'evidence': 'a.py:1'}]}
            second = {'schema': 'uncle.artifact/v1', 'kind': kind,
                      'findings': [{'id': 'AR-001', 'summary': 'scope gap', 'evidence': 'b.py:2'}]}
            self.write(directory, 'requirements', first); self.write(directory, 'security', second)
            output = directory/'combined.json'
            WORKERS.collate(directory, output, kind, ('requirements', 'security'))
            payload = json.loads(output.read_text())
            self.assertEqual(payload['findings'][0]['sources'], ['requirements', 'security'])
            self.assertEqual(payload['findings'][0]['evidence'], ['a.py:1', 'b.py:2'])
            with self.assertRaisesRegex(WORKERS.PacketError, 'regression.json: worker packet is missing'):
                WORKERS.collate(directory, output, kind, ('requirements', 'regression'))

    def test_worker_packets_reject_placeholder_ids_at_every_runner_boundary(self):
        body = {'schema': 'uncle.artifact/v1', 'kind': 'test-review-worker-packet',
                'rows': [{'id': 'No finding — reviewer to assign ID',
                          'status': 'FAIL', 'evidence': 'report.md'}]}
        serialized = json.dumps(body)
        with self.assertRaisesRegex(ValueError, 'stable finding ID, not placeholder'):
            OUTPUT.worker_packet(serialized, 'claude')
        with self.assertRaisesRegex(SELF_HOSTED.InvalidReviewerDocument, 'stable finding ID, not placeholder'):
            SELF_HOSTED.reviewer_packet(serialized, 'assertions.json')

    def test_manual_checklist_requires_real_json_checks_at_runner_boundary(self):
        narrative = 'I rewrote .uncle/docs/MANUAL_CHECKLIST.md with 13 checks.'
        with self.assertRaisesRegex(ValueError, 'did not return a manual-checklist JSON object'):
            OUTPUT.check(narrative, 'claude', 'MANUAL_CHECKLIST.md')
        body = {'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist', 'checks': []}
        with self.assertRaisesRegex(ValueError, 'requires a nonempty checks array'):
            OUTPUT.check(json.dumps(body), 'claude', 'MANUAL_CHECKLIST.md')
        body['checks'] = [{'id': 'MC-001', 'exact_action': 'Open the page', 'expected_result': 'Calculator loads'}]
        self.assertEqual(json.loads(OUTPUT.check(json.dumps(body), 'claude', 'MANUAL_CHECKLIST.md'))['checks'][0]['id'], 'MC-001')

    def test_generic_packets_repair_only_the_known_transport_quote_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp); kind = 'adversarial-review-worker-packet'
            raw = '{"schema":"uncle.artifact/v1","kind":"adversarial-review-worker-packet","findings":[{"id":"AR-001","summary":"gap","evidence":"proof","}]}'
            # OpenCode's observed stream corruption: a dangling quote follows
            # an otherwise complete field/object delimiter.
            (directory/'requirements.json').write_text(raw)
            WORKERS.collate(directory, directory/'out.json', kind, ('requirements',))
            self.assertEqual(json.loads((directory/'out.json').read_text())['findings'][0]['id'], 'AR-001')

    def test_every_migrated_panel_uses_json_and_binding_collation(self):
        contracts = {
            'scripts/stagegate.sh': (
                ('ADVERSARIAL_REVIEW_WORKERS.json', 'adversarial-review-worker-packet'),
                ('FINAL_AUDIT_WORKERS.json', 'final-audit-worker-packet')),
            'scripts/change-workflow.sh': (
                ('ADVERSARIAL_REVIEW_WORKERS.json', 'adversarial-review-worker-packet'),
                ('FINAL_AUDIT_WORKERS.json', 'final-audit-worker-packet')),
        }
        for source, panels in contracts.items():
            text = (ROOT/source).read_text()
            for artifact, kind in panels:
                self.assertIn(artifact, text)
                self.assertIn('--kind ' + kind, text)
            self.assertGreaterEqual(text.lower().count('do not read the worker directory'), len(panels))
        test_review = (ROOT/'scripts/stagegate.sh').read_text()
        self.assertIn('TEST_REVIEW_WORKERS.json', test_review)
        self.assertIn('test_review_packets.py', test_review)
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT/source).read_text()
            self.assertIn('MANUAL_CHECKLIST_WORKERS.json', text)
            self.assertIn('manual_checklist_packets.py', text)
        for prompt, kind in (
            ('adversarial-review-worker.md', 'adversarial-review-worker-packet'),
            ('test-review-worker.md', 'test-review-worker-packet'),
            ('manual-checklist-review-worker.md', 'manual-checklist-worker-packet'),
            ('final-audit-review-worker.md', 'final-audit-worker-packet')):
            text = (ROOT/'prompts/change'/prompt).read_text()
            self.assertIn('"kind":"' + kind + '"', text)
            if prompt == 'test-review-worker.md':
                self.assertIn('Return every assigned acceptance row', text)
            elif prompt in ('adversarial-review-worker.md', 'final-audit-review-worker.md'):
                self.assertIn('empty array when clean', text)
            else:
                self.assertIn('include every required field', text)
        test_worker = (ROOT/'prompts/change/test-review-worker.md').read_text()
        self.assertIn('Return every assigned acceptance row', test_worker)
        self.assertIn('"id":"COVERAGE"', test_worker)
        for prompt in ('manual-checklist.md', 'change/manual-checklist.md', 'change/manual-checklist-base.md'):
            text = (ROOT/'prompts'/prompt).read_text()
            self.assertIn('not a statement that you wrote', text)
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            self.assertIn('validate_reviewer_artifact', (ROOT/source).read_text())

    def test_manual_checklist_lenses_have_non_overlapping_id_ranges(self):
        expected = (
            "coverage) range='MC-100 through MC-199'",
            "invariants) range='MC-200 through MC-299'",
            "resources) range='MC-300 through MC-399'",
            "regressions) range='MC-400 through MC-499'",
        )
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT/source).read_text()
            for range_clause in expected:
                self.assertIn(range_clause, text)

    def test_worker_prompts_preserve_absolute_paths_and_bypass_supervision(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT/source).read_text()
            self.assertIn('[[ "$p" == /* || -e "$p" ]]', text)
            start = text.index('effective_prompt="$(gated_prompt "$prompt_file" "$log_name")"')
            block = text[start:start + 500]
            self.assertIn('*-worker-*) ;;', block)
            self.assertIn('supervision_prompt "$effective_prompt"', block)

    def test_every_gated_stage_prefers_previous_canonical_json(self):
        gates = (ROOT/'scripts/lib/gates.sh').read_text()
        self.assertIn('# Canonical workflow inputs (binding)', gates)
        self.assertIn('.uncle/workflow/documents/NAME.json', gates)
        self.assertIn('Markdown file is only its rendered approval/review view', gates)

    def test_workers_use_the_compact_json_prompt_path(self):
        gates = (ROOT/'scripts/lib/gates.sh').read_text()
        self.assertIn('*-worker-*)', gates)
        self.assertIn('# Compact worker contract (binding)', gates)
        self.assertIn('Do not enumerate `.uncle/workflow/documents/`', gates)
        self.assertIn('updated-plan-review-worker-*', gates)
        self.assertIn('updated-change-plan-review-worker-*', gates)
        self.assertIn('PROJECT_PLAN.json` and `.uncle/workflow/documents/ADVERSARIAL_REVIEW.json', gates)
        self.assertIn('CHANGE_PLAN.json` and `.uncle/workflow/documents/ADVERSARIAL_REVIEW.json', gates)
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT/source).read_text()
            self.assertIn('case "$log_name" in *-worker-*|', text)

    def test_updated_plan_panels_require_their_canonical_inputs_before_fanout(self):
        stagegate = (ROOT / 'scripts/stagegate.sh').read_text()
        change = (ROOT / 'scripts/change-workflow.sh').read_text()
        self.assertIn('ensure_project_plan_json', stagegate)
        self.assertIn('canonicalize-project-plan "$source" .', stagegate)
        adversarial = stagegate[stagegate.index('        ADVERSARIAL_REVIEW)'):stagegate.index('        UPDATED_PLAN)')]
        self.assertIn('ensure_project_plan_json || exit 1', adversarial)
        self.assertIn('require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json"', stagegate)
        self.assertIn('require_file "$STATE_DIR/documents/CHANGE_PLAN.json"', change)
        self.assertIn('require_file "$STATE_DIR/documents/ADVERSARIAL_REVIEW.json"', change)

    def test_review_parent_synthesis_uses_compact_canonical_path(self):
        gates = (ROOT/'scripts/lib/gates.sh').read_text()
        self.assertIn(
            'updated-plan|updated-change-plan|adversarial-review|test-review|manual-checklist|final-audit)',
            gates,
        )
        self.assertIn('# Compact canonical synthesis contract (binding)', gates)
        self.assertIn('do not conduct a second investigation pass', gates)
        self.assertIn(
            '*-worker-*|updated-change-plan|adversarial-review|final-audit|manual-checklist)',
            (ROOT/'scripts/change-workflow.sh').read_text(),
        )
        self.assertIn(
            '*-worker-*|updated-plan|adversarial-review|test-review|manual-checklist|final-audit)',
            (ROOT/'scripts/stagegate.sh').read_text(),
        )

    def test_test_review_format_retry_reuses_collated_workers(self):
        source = (ROOT / 'scripts/stagegate.sh').read_text()
        start = source.index('        TEST_REVIEW)')
        block = source[start:source.index('        REPAIR)', start)]
        retry = block[block.index('if [[ -s "$STATE_DIR/test-review-format-retry.md" ]]; then',
                                  block.index('else\n                # A malformed acceptance table')):]
        retry = retry[:retry.index('else\n                    run_test_review_panel')]
        self.assertNotIn('run_test_review_panel', retry)
        self.assertIn('test-review-panel/synthesis.md', retry)
        self.assertIn('Retrying test-review formatting only', retry)

    def test_updated_plan_has_no_self_hosted_markdown_investigation_fallback(self):
        stagegate = (ROOT / 'scripts/stagegate.sh').read_text()
        start = stagegate.index('        UPDATED_PLAN)')
        end = stagegate.index('        IMPLEMENT)', start)
        block = stagegate[start:end]
        self.assertIn('run_claude "${UPDATED_PLAN_PROMPT:-prompts/updated-plan.md}" updated-plan', block)
        self.assertNotIn('updated-plan-investigate', block)
        self.assertNotIn('updated-plan-investigation.md', block)
        self.assertNotIn('updated-plan-format', block)

    def test_plan_review_parents_name_canonical_json_not_markdown_inputs(self):
        updated = (ROOT / 'prompts/updated-plan.md').read_text()
        changed = (ROOT / 'prompts/change/updated-change-plan.md').read_text()
        review = (ROOT / 'prompts/adversarial-review.md').read_text()
        self.assertIn('.uncle/workflow/documents/PROJECT_PLAN.json', updated)
        self.assertIn('.uncle/workflow/documents/ADVERSARIAL_REVIEW.json', updated)
        self.assertNotIn('- .uncle/docs/PROJECT_PLAN.md', updated)
        self.assertIn('.uncle/workflow/documents/CHANGE_PLAN.json', changed)
        self.assertIn('.uncle/workflow/documents/CHANGE_SPEC.json', changed)
        self.assertNotIn('- .uncle/docs/CHANGE_PLAN.md', changed)
        self.assertIn('.uncle/workflow/documents/PROJECT_PLAN.json', review)
        self.assertNotIn('- .uncle/docs/PROJECT_PLAN.md', review)


if __name__ == '__main__':
    unittest.main()
