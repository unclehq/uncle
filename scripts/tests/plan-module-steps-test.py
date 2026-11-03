#!/usr/bin/env python3
"""The planner is told to give a unit-testable source file the same step as its own unit tests.

Run 15: the engine (step 2) and its unit tests (step 5) were separate workers, the tests asserted an exponent form the engine never
produced, and that cost two repairs. A step owning both is what step_groups.is_module recognises. The real prompt texts are read, so this
cannot drift from them; the last case checks the rule is one the driver acts on."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import project_plan_sections as sections  # noqa: E402
import step_groups  # noqa: E402

RULE = 'one step together with its own'
OUTLINE = sections.SPECIFIC['outline'] if isinstance(sections.SPECIFIC['outline'], str) else ' '.join(sections.SPECIFIC['outline'])


class ModuleStepRule(unittest.TestCase):
    def test_outline_prompt_states_the_rule(self):
        text = OUTLINE
        self.assertTrue(text, 'could not find the outline instruction')
        self.assertIn('(an engine, a key map, a formatter) is one step together with its own unit test file', text)

    def test_outline_no_longer_splits_unit_tests_from_their_source(self):
        text = OUTLINE
        self.assertNotIn('independent unit, UI, keyboard, and other', text)

    def test_browser_specs_stay_separate(self):
        text = OUTLINE
        self.assertIn('Browser, keyboard and theme specs need the whole application', text)

    def test_whole_plan_prompts_state_the_rule(self):
        for name in ('project-plan.md', 'project-plan-investigate.md'):
            text = (ROOT / 'prompts' / name).read_text(encoding='utf-8')
            self.assertEqual(text.count(RULE), 1, name)
            self.assertIn('Browser and other\n  whole-application specs stay in their own steps.', text, name)

    def test_such_a_step_is_a_module_to_the_driver(self):
        self.assertTrue(step_groups.is_module(['src/calc.js', 'tests/calc.test.js']))
        self.assertFalse(step_groups.is_module(['src/calc.js']))
        self.assertFalse(step_groups.is_module(['tests/calc.test.js']))


class StateCoverageRule(unittest.TestCase):
    """Run 16: the drafted row said Backspace is ignored in Error, the plan was silent, the code did the opposite."""

    def test_behaviors_worker_covers_every_input_in_every_state(self):
        text = sections.SPECIFIC['behaviors']
        text = text if isinstance(text, str) else ' '.join(text)
        self.assertIn('each kind of input its own behavior row in each state', text)
        self.assertIn('including the inputs that do nothing there', text)

    def test_whole_plan_prompts_say_it_too(self):
        for name in ('project-plan.md', 'project-plan-investigate.md'):
            text = (ROOT / 'prompts' / name).read_text(encoding='utf-8')
            self.assertEqual(text.count('give each kind of input its own\nbehavior in each state'), 1, name)


class AdversarialReviewSettlesAmbiguity(unittest.TestCase):
    """Runs 15 to 17 each failed on a different thing the plan left two ways to read: an overflow format, Backspace in Error, and 12
    significant digits against a 12-character display. Every review worker is asked for those, with the sentence that settles them."""

    def test_worker_prompt_asks_for_unspecified_combinations_and_conflicts(self):
        text = (ROOT / 'prompts/change/adversarial-review-worker.md').read_text(encoding='utf-8')
        self.assertIn('a combination left unspecified', text)
        self.assertIn('two statements that cannot both hold', text)
        self.assertIn('significant digits against display width', text)
        self.assertIn('a decision, not a question', text)

    def test_the_sliced_review_uses_that_same_prompt(self):
        import adversarial_slices
        source = Path(adversarial_slices.__file__).read_text(encoding='utf-8')
        self.assertIn("prompts/change/adversarial-review-worker.md", source)

    def test_requirements_areas_name_both_kinds(self):
        import adversarial_slices
        areas = ' '.join(adversarial_slices.AREAS['requirements'])
        self.assertIn('numeric limits that cannot both hold', areas)
        self.assertIn('every input in every state the plan leaves unspecified', areas)


class KeyboardReadiness(unittest.TestCase):
    """Runs 19 and 20: a keyboard spec failed on the first build because its first key arrived before the app's key listener was attached.
    The app side (synchronous mount) goes in the plan; the spec side (wait for the display) goes to both the planner and the spec worker."""

    def test_the_outline_asks_for_a_synchronous_mount_and_a_wait(self):
        text = OUTLINE
        self.assertIn('`flushSync` around `render`', text)
        self.assertIn('first waits for the display to show its initial value', text)

    def test_the_whole_plan_prompts_say_it_too(self):
        for name in ('project-plan.md', 'project-plan-investigate.md'):
            text = ' '.join((ROOT / 'prompts' / name).read_text(encoding='utf-8').split())
            self.assertEqual(text.count('`flushSync` around `render`'), 1, name)
            self.assertIn('first waits for the display to show its initial value', text, name)

    def test_the_spec_worker_is_told_to_wait_before_pressing_keys(self):
        text = ' '.join((ROOT / 'scripts' / 'stagegate.sh').read_text(encoding='utf-8').split())
        self.assertIn('A spec that presses keys first waits for the page to be ready', text)
        self.assertIn('before the first key press', text)


class ModuleTestsCoverEveryRow(unittest.TestCase):
    """Run 23: the plan said `5 + =` does nothing, the engine computed 5 + 5, and its own tests had no such case; a repair followed."""

    def test_the_outline_has_the_step_say_its_tests_cover_every_row(self):
        text = ' '.join(OUTLINE.split())
        self.assertIn('Say in that step that its tests cover every behavior, invariant and failure row that concerns the module', text)
        self.assertIn('the cases where an input does nothing included', text)


class RepairFixesEveryOpenFailure(unittest.TestCase):
    """Run 26: the first repair added missing tests and left the checklist's display failure "outside this gate's findings"; a second repair fixed it."""

    def setUp(self):
        self.text = ' '.join((ROOT / 'prompts' / 'repair.md').read_text(encoding='utf-8').split())

    def test_the_trigger_comes_first_and_the_others_are_named(self):
        self.assertIn('The repair source is the failure that triggered this pass, and it comes first.', self.text)
        for source in ('`.uncle/docs/TEST_REVIEW.md`', '`.uncle/docs/DEFECTS.md`', '`.uncle/docs/VERIFICATION_REPORT.md`'):
            self.assertIn(source, self.text)

    def test_every_fixable_failure_is_fixed_in_the_one_pass(self):
        self.assertIn('Fix every one that a change to the project\'s files can fix, in this one pass.', self.text)

    def test_an_unfixed_failure_needs_a_stated_reason_and_not_in_this_report_is_not_one(self):
        self.assertIn('An open FAIL you do not fix needs a one-line reason', self.text)
        self.assertIn('"not in this report" is not a reason', self.text)

    def test_the_rule_does_not_lift_the_protections(self):
        self.assertIn('Never weaken acceptance', self.text)
        self.assertIn('Do not edit requirements, approved plans', self.text)


class NoHandComputedDigits(unittest.TestCase):
    """Runs 17, 19 and 30: a long expected value worked out by hand was wrong in the plan and spread to every test and checklist row."""

    def test_the_tests_worker_is_told_to_state_the_rule_and_not_compute_long_numbers(self):
        text = sections.SPECIFIC['tests']
        text = ' '.join((text if isinstance(text, str) else ' '.join(text)).split())
        self.assertIn('Do not work out a long number by hand', text)
        self.assertIn('state the rule and the input in words', text)
        self.assertIn('write digits only when you are certain', text)
        self.assertIn('the driver checks products of whole numbers against the exact value', text)


if __name__ == '__main__':
    unittest.main()
