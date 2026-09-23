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
                ('TEST_REVIEW_WORKERS.json', 'test-review-worker-packet'),
                ('MANUAL_CHECKLIST_WORKERS.json', 'manual-checklist-worker-packet'),
                ('FINAL_AUDIT_WORKERS.json', 'final-audit-worker-packet')),
            'scripts/change-workflow.sh': (
                ('ADVERSARIAL_REVIEW_WORKERS.json', 'adversarial-review-worker-packet'),
                ('MANUAL_CHECKLIST_WORKERS.json', 'manual-checklist-worker-packet'),
                ('FINAL_AUDIT_WORKERS.json', 'final-audit-worker-packet')),
        }
        for source, panels in contracts.items():
            text = (ROOT/source).read_text()
            for artifact, kind in panels:
                self.assertIn(artifact, text)
                self.assertIn('--kind ' + kind, text)
            self.assertGreaterEqual(text.lower().count('do not read the worker directory'), len(panels))
        for prompt, kind in (
            ('adversarial-review-worker.md', 'adversarial-review-worker-packet'),
            ('test-review-worker.md', 'test-review-worker-packet'),
            ('manual-checklist-review-worker.md', 'manual-checklist-worker-packet'),
            ('final-audit-review-worker.md', 'final-audit-worker-packet')):
            text = (ROOT/'prompts/change'/prompt).read_text()
            self.assertIn('"kind":"' + kind + '"', text)
            self.assertIn('empty array when clean', text)

    def test_every_gated_stage_prefers_previous_canonical_json(self):
        gates = (ROOT/'scripts/lib/gates.sh').read_text()
        self.assertIn('# Canonical workflow inputs (binding)', gates)
        self.assertIn('.uncle/workflow/documents/NAME.json', gates)
        self.assertIn('Markdown file is only its rendered approval/review view', gates)


if __name__ == '__main__':
    unittest.main()
