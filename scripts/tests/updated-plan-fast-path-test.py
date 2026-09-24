#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fast', ROOT / 'scripts/lib/updated_plan_fast_path.py')
FAST = importlib.util.module_from_spec(spec); spec.loader.exec_module(FAST)


class UpdatedPlanFastPath(unittest.TestCase):
    def write(self, directory, name, data):
        path = directory / name; path.write_text(json.dumps(data)); return path

    def test_empty_review_copies_plan_without_a_model(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            plan = self.write(directory, 'plan.json', {'schema':'uncle.artifact/v1','kind':'plan','narrative':'# Project plan\n\nKeep it','verification_commands':'test -f app','protected_verification_paths':'tests'})
            review = self.write(directory, 'review.json', {'schema':'uncle.artifact/v1','kind':'adversarial-review','findings':[]})
            output = directory / 'updated.json'
            self.assertTrue(FAST.build(plan, review, output))
            result = json.loads(output.read_text())
            self.assertEqual(result['narrative'].splitlines()[0], '# Updated project plan')
            self.assertEqual(result['dispositions'], [])

    def test_any_finding_requires_parent_judgment(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            plan = self.write(directory, 'plan.json', {'schema':'uncle.artifact/v1','kind':'plan'})
            review = self.write(directory, 'review.json', {'schema':'uncle.artifact/v1','kind':'adversarial-review','findings':[{'id':'AR-1'}]})
            self.assertFalse(FAST.build(plan, review, directory / 'updated.json'))

    def test_empty_review_copies_change_plan_with_explicit_dispositions(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            plan = self.write(directory, 'change-plan.json', {
                'schema':'uncle.artifact/v1', 'kind':'change-plan',
                'narrative':'# Change plan\n\nKeep it', 'steps':[{'id':'S-1'}]
            })
            review = self.write(directory, 'review.json', {
                'schema':'uncle.artifact/v1', 'kind':'adversarial-review', 'findings':[]
            })
            output = directory / 'updated-change.json'
            self.assertTrue(FAST.build_change(plan, review, output))
            result = json.loads(output.read_text())
            self.assertEqual(result['kind'], 'change-plan')
            self.assertEqual(result['narrative'], '# Change plan\n\nKeep it')
            self.assertEqual(result['dispositions'], [])

    def test_change_plan_findings_require_parent_judgment(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            plan = self.write(directory, 'change-plan.json', {
                'schema':'uncle.artifact/v1', 'kind':'change-plan', 'narrative':'# Change plan'
            })
            review = self.write(directory, 'review.json', {
                'schema':'uncle.artifact/v1', 'kind':'adversarial-review', 'findings':[{'id':'AR-1'}]
            })
            self.assertFalse(FAST.build_change(plan, review, directory / 'updated-change.json'))

    def test_driver_attempts_fast_path_before_worker_fanout(self):
        source = (ROOT / 'scripts/stagegate.sh').read_text()
        state = source[source.index('        UPDATED_PLAN)'):source.index('        IMPLEMENT)', source.index('        UPDATED_PLAN)'))]
        self.assertLess(state.index('run_updated_plan_fast_path'), state.index('run_updated_plan_panel'))

    def test_change_driver_attempts_fast_path_before_worker_fanout(self):
        source = (ROOT / 'scripts/change-workflow.sh').read_text()
        state = source[source.index('        UPDATED_PLAN)'):source.index('        VALIDATE_UPDATED_PLAN)', source.index('        UPDATED_PLAN)'))]
        self.assertLess(state.index('run_updated_change_plan_fast_path'), state.index('run_updated_change_plan_panel'))


if __name__ == '__main__':
    unittest.main()
