#!/usr/bin/env python3
"""The adversarial review is built from worker packets without duplicating or inventing text."""
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


def packet(findings):
    return {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet', 'findings': findings}


class ReviewShrink(unittest.TestCase):
    def build(self, packets):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            panel = root / 'panel'; panel.mkdir()
            for name, findings in packets.items():
                (panel / (name + '.json')).write_text(json.dumps(packet(findings)), encoding='utf-8')
            documents = root / '.uncle/workflow/documents'; documents.mkdir(parents=True)
            (root / '.uncle/docs').mkdir()
            worker_packets.collate(panel, documents / 'ADVERSARIAL_REVIEW_WORKERS.json', 'adversarial-review-worker-packet',
                                   list(packets))
            subprocess.run([sys.executable, '-B', str(LIB / 'adversarial_packets.py'), str(root)], check=True)
            return json.loads((documents / 'ADVERSARIAL_REVIEW.json').read_text(encoding='utf-8'))

    def test_title_is_a_short_label_not_a_copy_of_the_failure(self):
        long = 'The plan has no test for contrast. ' + 'It matters because readers cannot see the text. ' * 8
        finding = self.build({'a': [{'id': 'AR-001', 'summary': long, 'evidence': 'plan B-14'}]})['findings'][0]
        self.assertEqual(finding['title'], 'The plan has no test for contrast.')
        self.assertEqual(finding['failure'], long.strip())
        self.assertLessEqual(len(finding['title']), 120)

    def test_a_workers_severity_is_kept_and_the_worst_wins(self):
        review = self.build({'a': [{'id': 'AR-001', 'severity': 'Low', 'summary': 'same issue', 'evidence': 'x'}],
                             'b': [{'id': 'AR-009', 'severity': 'High', 'summary': 'same issue', 'evidence': 'y'}]})
        self.assertEqual([f['severity'] for f in review['findings']], ['HIGH'])

    def test_no_stated_severity_is_medium_as_before(self):
        review = self.build({'a': [{'id': 'AR-001', 'summary': 'issue', 'evidence': 'x'}]})
        self.assertEqual(review['findings'][0]['severity'], 'MEDIUM')

    def test_an_unknown_severity_word_is_ignored(self):
        review = self.build({'a': [{'id': 'AR-001', 'severity': 'Catastrophic', 'summary': 'issue', 'evidence': 'x'}]})
        self.assertEqual(review['findings'][0]['severity'], 'MEDIUM')

    def test_boilerplate_fields_are_short(self):
        finding = self.build({'a': [{'id': 'AR-001', 'summary': 'issue', 'evidence': 'x'}]})['findings'][0]
        self.assertLessEqual(len(finding['fix']) + len(finding['verify']), 40)

    def test_worker_schemas_cap_findings_and_field_sizes(self):
        adversarial = self_hosted.artifact_schema('adversarial-review-worker-packet')['properties']['findings']
        self.assertEqual(adversarial['maxItems'], 8)
        self.assertEqual(adversarial['items']['properties']['summary']['maxLength'], 400)
        self.assertEqual(adversarial['items']['properties']['evidence']['maxLength'], 700)
        updated = self_hosted.artifact_schema('updated-plan-worker-packet')['properties']['findings']['items']['properties']
        self.assertEqual([updated[k]['maxLength'] for k in ('gap', 'evidence', 'risk', 'required_correction')],
                         [300, 400, 300, 500])
        dispositions = self_hosted.DISPOSITIONS['items']['properties']
        self.assertEqual((dispositions['reason']['maxLength'], dispositions['plan_change']['maxLength']), (300, 300))


if __name__ == '__main__':
    unittest.main()
