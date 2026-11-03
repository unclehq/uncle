#!/usr/bin/env python3
"""The Python driver entry point: reading a project, the state file, ported-state dispatch, and the hook in stagegate.sh."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location('driver', LIB / 'driver.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
stages = sys.modules['driver_stages']


def project(files=(), approvals=(), state=None):
    folder = Path(tempfile.mkdtemp())
    for rel in files:
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('x')
    for name in approvals:
        path = folder / '.uncle/workflow/approvals' / (name + '.approved-by')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('unattended\n')
    ctx = driver.context(folder)
    if state:
        ctx.state_dir.mkdir(parents=True, exist_ok=True)
        ctx.state_file.write_text(state + '\n')
    return ctx


class StateFile(unittest.TestCase):
    def test_a_project_with_no_state_starts_at_the_first_state(self):
        self.assertEqual(driver.read_state(project()), 'DERIVE_BRIEF')

    def test_the_state_is_the_first_line(self):
        self.assertEqual(driver.read_state(project(state='IMPLEMENT')), 'IMPLEMENT')

    def test_the_issue_prefix_the_issue_driver_writes_is_not_part_of_the_state(self):
        self.assertEqual(driver.read_state(project(state='42:TEST_REVIEW')), 'TEST_REVIEW')

    def test_a_name_that_merely_contains_a_colon_is_left_alone(self):
        self.assertEqual(driver.read_state(project(state='abc:IMPLEMENT')), 'abc:IMPLEMENT')

    def test_python_has_no_way_to_write_the_state(self):
        self.assertFalse(hasattr(driver, 'write_state'))


class Plan(unittest.TestCase):
    def test_a_new_project_can_only_start_requirements(self):
        self.assertEqual(driver.plan(project())['ready'], ['requirements'])

    def test_implementation_waits_for_the_updated_plan_approval(self):
        files = ['.uncle/docs/REQUIREMENTS_INTERPRETATION.md', '.uncle/docs/PROJECT_PLAN.md',
                 '.uncle/docs/ADVERSARIAL_REVIEW.md', '.uncle/docs/UPDATED_PROJECT_PLAN.md']
        self.assertNotIn('implement', driver.plan(project(files))['ready'])
        self.assertIn('implement', driver.plan(project(files, ['UPDATED_PROJECT_PLAN']))['ready'])

    def test_approvals_are_the_records_stagegate_writes(self):
        ctx = project(approvals=['PROJECT_PLAN', 'ADVERSARIAL_REVIEW'])
        self.assertEqual(driver.approvals_granted(ctx), {'PROJECT_PLAN', 'ADVERSARIAL_REVIEW'})

    def test_a_signature_file_is_not_an_approval(self):
        ctx = project()
        folder = ctx.state_dir / 'approvals'
        folder.mkdir(parents=True)
        (folder / 'PROJECT_PLAN.sha256').write_text('abc')
        self.assertEqual(driver.approvals_granted(ctx), set())

    def test_remaining_time_counts_only_what_is_not_done(self):
        everything = list(stages.ARTIFACT_FILES.values())
        self.assertEqual(driver.plan(project(everything))['remaining_seconds'], 0.0)
        fresh = driver.plan(project())['remaining_seconds']
        self.assertGreater(fresh, 400)

    def test_a_build_stopped_in_the_checklist_has_the_checklist_and_audit_left(self):
        done = [rel for name, rel in stages.ARTIFACT_FILES.items() if name not in ('VERIFICATION_REPORT', 'FINAL_AUDIT')]
        result = driver.plan(project(done, ['UPDATED_PROJECT_PLAN']))
        self.assertEqual(result['remaining_path'], ['execute_checklist', 'final_audit'])


CHECKLIST = (LIB.parent / 'tests' / 'fixtures' / 'manual-checklist-valid.json').read_text()


def without_expected_result():
    """Passes the driver-scope step, fails validation: the case the bash arm answers with one retry."""
    data = json.loads(CHECKLIST)

    def strip(node):
        if isinstance(node, dict):
            if 'expected_result' in node:
                del node['expected_result']
                return True
            return any(strip(v) for v in node.values())
        return isinstance(node, list) and any(strip(v) for v in node)
    assert strip(data)
    return json.dumps(data)


def with_checklist(text=CHECKLIST):
    ctx = project(state='VALIDATE_MANUAL_CHECKLIST')
    (ctx.state_dir / 'documents').mkdir(parents=True)
    (ctx.state_dir / 'documents' / 'MANUAL_CHECKLIST.json').write_text(text)
    (ctx.project_root / '.uncle/docs').mkdir(parents=True, exist_ok=True)
    return ctx


def run_handler(ctx, state='VALIDATE_MANUAL_CHECKLIST'):
    target = ctx.project_root / 'next'
    with unittest.mock.patch.dict(os.environ, {'UNCLE_PY_NEXT_FILE': str(target)}):
        status = driver.run_state(ctx, state)
    return status, (target.read_text().strip() if target.exists() else None)


class Ported(unittest.TestCase):
    def test_an_unported_state_is_refused_with_its_own_exit_code(self):
        self.assertEqual(driver.run_state(project(state='IMPLEMENT'), 'IMPLEMENT'), 3)

    def test_the_manual_checklist_validation_is_the_first_ported_state(self):
        self.assertEqual(sorted(driver.HANDLERS), ['VALIDATE_MANUAL_CHECKLIST'])

    def test_a_valid_checklist_is_rendered_and_hands_back_the_execute_state(self):
        ctx = with_checklist()
        status, following = run_handler(ctx)
        self.assertEqual((status, following), (0, 'EXECUTE_CHECKLIST'))
        rendered = (ctx.project_root / '.uncle/docs/MANUAL_CHECKLIST.md').read_text()
        self.assertIn('MC-', rendered)

    def test_the_state_file_is_left_for_bash_to_write(self):
        ctx = with_checklist()
        run_handler(ctx)
        self.assertEqual(ctx.state_file.read_text().strip(), 'VALIDATE_MANUAL_CHECKLIST')

    def test_a_checklist_that_fails_validation_is_declined_and_nothing_is_rendered_or_handed_back(self):
        ctx = with_checklist(without_expected_result())
        self.assertEqual(run_handler(ctx), (driver.DECLINED, None))
        self.assertFalse((ctx.project_root / '.uncle/docs/MANUAL_CHECKLIST.md').exists())

    def test_each_step_declines_for_its_own_reason(self):
        """Render re-validates, so the outcome alone cannot show which step caught a bad checklist."""
        with self.assertRaisesRegex(driver.Declined, 'checklist invalid'):
            driver.validate_manual_checklist(with_checklist(without_expected_result()))
        with self.assertRaisesRegex(driver.Declined, 'driver scope failed'):
            driver.validate_manual_checklist(with_checklist('{not json'))
        ctx = with_checklist()
        (ctx.project_root / '.uncle/docs/MANUAL_CHECKLIST.md').mkdir()      # the output path cannot be written as a file
        with self.assertRaisesRegex(driver.Declined, 'render failed'):
            driver.validate_manual_checklist(ctx)

    def test_a_missing_checklist_is_declined(self):
        ctx = project(state='VALIDATE_MANUAL_CHECKLIST')
        (ctx.project_root / '.uncle/docs').mkdir(parents=True, exist_ok=True)
        self.assertEqual(run_handler(ctx)[0], driver.DECLINED)

    def test_a_handler_returning_an_unknown_state_is_an_error_and_hands_nothing_back(self):
        ctx = project(state='TEST_REVIEW')
        with unittest.mock.patch.dict(driver.HANDLERS, {'TEST_REVIEW': lambda c: 'BOGUS'}):
            with self.assertRaises(ValueError):
                run_handler(ctx, 'TEST_REVIEW')
        self.assertFalse((ctx.project_root / 'next').exists())

    def test_without_a_place_to_hand_the_state_back_it_fails_rather_than_guessing(self):
        ctx = with_checklist()
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop('UNCLE_PY_NEXT_FILE', None)
            self.assertEqual(driver.run_state(ctx, 'VALIDATE_MANUAL_CHECKLIST'), 2)


class StagegateHook(unittest.TestCase):
    """The dispatch condition is taken from stagegate.sh itself, so this cannot drift from the real line."""

    @classmethod
    def setUpClass(cls):
        lines = (LIB.parent / 'stagegate.sh').read_text().split('\n')
        at = next(i for i, line in enumerate(lines) if 'run-state "$state"' in line)
        cls.condition = next(line.strip() for line in reversed(lines[:at]) if line.strip().startswith('if [['))

    def dispatches(self, state, listed):
        """`listed` None leaves UNCLE_PY_STATES unset, as it is in a normal run."""
        script = 'state=%s\n%s; then\n  exit 0\nfi\nexit 1' % (state, self.condition.rstrip().removesuffix('; then'))
        env = {k: v for k, v in os.environ.items() if k != 'UNCLE_PY_STATES'}
        if listed is not None:
            env['UNCLE_PY_STATES'] = listed
        return subprocess.run(['bash', '-c', script], env=env).returncode == 0

    def test_by_default_the_ported_state_is_dispatched_and_no_other(self):
        self.assertTrue(self.dispatches('VALIDATE_MANUAL_CHECKLIST', None))
        self.assertFalse(self.dispatches('IMPLEMENT', None))

    def test_setting_the_list_empty_returns_every_state_to_bash(self):
        self.assertFalse(self.dispatches('VALIDATE_MANUAL_CHECKLIST', ''))

    def test_a_listed_state_is_dispatched(self):
        self.assertTrue(self.dispatches('IMPLEMENT', 'IMPLEMENT'))
        self.assertTrue(self.dispatches('IMPLEMENT', 'TEST_REVIEW,IMPLEMENT,FINAL_AUDIT'))

    def test_an_unlisted_state_is_not(self):
        self.assertFalse(self.dispatches('IMPLEMENT', 'TEST_REVIEW'))

    def test_an_empty_list_dispatches_nothing(self):
        self.assertFalse(self.dispatches('IMPLEMENT', ''))

    def test_a_listed_name_that_only_contains_the_state_is_not_a_match(self):
        self.assertFalse(self.dispatches('TEST_REVIEW', 'VALIDATE_TEST_REVIEW'))
        self.assertFalse(self.dispatches('REVIEW', 'TEST_REVIEW'))

    def test_the_hook_runs_before_the_case_so_a_ported_state_skips_its_bash_arm(self):
        text = (LIB.parent / 'stagegate.sh').read_text()
        self.assertLess(text.index('run-state "$state"'), text.index('    case "$state" in\n        DERIVE_BRIEF)'))


if __name__ == '__main__':
    unittest.main()
