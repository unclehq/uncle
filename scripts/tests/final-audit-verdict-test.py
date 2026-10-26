#!/usr/bin/env python3
"""A final audit blocks on what its workers say blocks, not on the mere existence of a finding."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import worker_packets  # noqa: E402
import self_hosted  # noqa: E402


def audit(packets):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        panel = root / 'panel'; panel.mkdir()
        for name, findings in packets.items():
            body = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit-worker-packet', 'findings': findings}
            (panel / (name + '.json')).write_text(json.dumps(body), encoding='utf-8')
        documents = root / '.uncle/workflow/documents'; documents.mkdir(parents=True)
        (root / '.uncle/docs').mkdir()
        worker_packets.collate(panel, documents / 'FINAL_AUDIT_WORKERS.json', 'final-audit-worker-packet', list(packets))
        subprocess.run([sys.executable, '-B', str(LIB / 'final_audit_packets.py'), str(root)], check=True)
        return json.loads((documents / 'FINAL_AUDIT.json').read_text(encoding='utf-8'))


def finding(identifier, severity=None, summary=None):
    item = {'id': identifier, 'summary': summary or 'issue ' + identifier, 'evidence': 'row MC-1'}
    if severity:
        item['severity'] = severity
    return item


class FinalAuditVerdict(unittest.TestCase):
    def test_no_findings_is_ready(self):
        result = audit({'a': []})
        self.assertEqual((result['verdict'], result['findings']), ('READY', []))

    def test_high_and_critical_block(self):
        for severity in ('High', 'Critical'):
            result = audit({'a': [finding('FA-001', severity)]})
            self.assertEqual(result['verdict'], 'NOT READY', severity)
            self.assertEqual(result['findings'][0]['blocks'], 'YES')

    def test_medium_and_low_alone_do_not_block(self):
        for severity in ('Medium', 'Low'):
            result = audit({'a': [finding('FA-001', severity)]})
            self.assertEqual(result['verdict'], 'READY WITH NON-BLOCKING ISSUES', severity)
            self.assertEqual(result['findings'][0]['blocks'], 'NO')
            self.assertEqual(result['findings'][0]['severity'], severity.upper())

    def test_one_blocking_finding_among_minor_ones_blocks(self):
        result = audit({'a': [finding('FA-001', 'Low', 'nit'), finding('FA-002', 'High', 'a required check fails')]})
        self.assertEqual(result['verdict'], 'NOT READY')
        self.assertEqual({f['id']: f['blocks'] for f in result['findings']}, {'FA-001': 'NO', 'FA-002': 'YES'})

    def test_a_finding_with_no_stated_severity_still_blocks(self):
        # Backward compatible and fail-closed: an omitted field never lets a finding slide.
        result = audit({'a': [finding('FA-001')]})
        self.assertEqual(result['verdict'], 'NOT READY')
        self.assertEqual((result['findings'][0]['severity'], result['findings'][0]['blocks']), ('MEDIUM', 'YES'))

    def test_the_worst_severity_across_workers_wins(self):
        result = audit({'a': [finding('FA-001', 'Low', 'same problem')], 'b': [finding('FA-009', 'High', 'same problem')]})
        self.assertEqual([f['severity'] for f in result['findings']], ['HIGH'])
        self.assertEqual(result['verdict'], 'NOT READY')

    def test_the_result_passes_the_drivers_own_consistency_rules(self):
        context = (LIB / 'final-audit-context.py').read_text()
        self.assertIn("Ready verdict contradicts blocking findings", context)
        for packets in ({'a': [finding('FA-001', 'Low')]}, {'a': [finding('FA-001', 'High')]}, {'a': []}):
            result = audit(packets)
            blocking = [f for f in result['findings'] if f['blocks'] == 'YES']
            self.assertEqual(bool(blocking), result['verdict'] == 'NOT READY')

    def test_worker_schemas(self):
        audit_schema = self_hosted.artifact_schema('final-audit-worker-packet')['properties']['findings']
        self.assertEqual(audit_schema['maxItems'], 8)
        self.assertEqual(audit_schema['items']['properties']['severity']['enum'], ['Critical', 'High', 'Medium', 'Low'])
        review = self_hosted.artifact_schema('test-review-worker-packet')['properties']['rows']
        self.assertEqual((review['maxItems'], review['items']['properties']['evidence']['maxLength']), (4, 800))
        checks = self_hosted.artifact_schema('manual-checklist-worker-packet')['properties']['checks']
        self.assertEqual(checks['maxItems'], 24)
        self.assertGreaterEqual(checks['items']['properties']['exact_action']['maxLength'], 682)
        self.assertGreaterEqual(checks['items']['properties']['expected_result']['maxLength'], 611)


if __name__ == '__main__':
    unittest.main()
