#!/usr/bin/env python3
"""Regression coverage for JSON-only combined change planning."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'publish_change_planning_bundle', ROOT / 'scripts/lib/publish_change_planning_bundle.py')
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


def packet():
    return {
        'schema': 'uncle.artifact/v1', 'kind': 'change-planning-bundle',
        'baseline_report': {
            'schema': 'uncle.artifact/v1', 'kind': 'baseline-report',
            'narrative': '# Baseline', 'verification_commands': 'test -f package.json'},
        'change_spec': {
            'schema': 'uncle.artifact/v1', 'kind': 'change-spec', 'narrative': '# Change',
            'acceptance_criteria': [{'id': 'AC-1', 'criterion': 'Works', 'verification': 'Run test'}]},
        'change_plan': {
            'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': '# Plan'},
    }


class BundleTests(unittest.TestCase):
    def write(self, root, payload):
        delivery = root / 'delivery.json'
        delivery.write_text(json.dumps(payload), encoding='utf-8')
        return delivery

    def test_publishes_all_canonical_packets_before_rendering_views(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle.publish(root, self.write(root, packet()))
            for stem in ('BASELINE_REPORT', 'CHANGE_SPEC', 'CHANGE_PLAN'):
                self.assertTrue((root / '.uncle/workflow/documents' / (stem + '.json')).is_file())
                self.assertTrue((root / '.uncle/docs' / (stem + '.md')).is_file())
            # Editing a view cannot alter the canonical plan the workflow uses.
            view = root / '.uncle/docs/CHANGE_PLAN.md'
            view.write_text('human edit', encoding='utf-8')
            data = json.loads((root / '.uncle/workflow/documents/CHANGE_PLAN.json').read_text())
            self.assertEqual(data['narrative'], '# Plan')

    def test_rejects_the_entire_bundle_before_any_partial_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = packet()
            payload['change_spec']['acceptance_criteria'] = []
            with self.assertRaisesRegex(ValueError, 'change_spec'):
                bundle.publish(root, self.write(root, payload))
            self.assertFalse((root / '.uncle/workflow/documents/BASELINE_REPORT.json').exists())


if __name__ == '__main__':
    unittest.main()
