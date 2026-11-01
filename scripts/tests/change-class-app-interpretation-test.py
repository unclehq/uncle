"""A new application is classified from its approved requirements interpretation, not only from how many files the plan scaffolds."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import change_class as c


def interpretation(requirements=5, criteria=6, required_extra='', non_goals='N-1 Scientific functions. N-2 Backend, accounts.'):
    return {'kind': 'requirements-interpretation', 'schema': 'uncle.artifact/v1', 'sections': {
        'required_functionality': ' '.join('R-%d does something.' % n for n in range(1, requirements + 1)) + required_extra,
        'definition_of_done': '| ID | Criterion |\n|---|---|\n' + '\n'.join('| D-%d | thing %d |' % (n, n) for n in range(1, criteria + 1)),
        'failure_behaviors': 'F-1 Divide by zero shows Error.', 'constraints': 'C-1 Must be React.',
        'explicit_non_goals': non_goals, 'ambiguities': 'AM-1 brief is sparse; we may need to delete assumptions.',
    }}


def plan(steps, files):
    owns = [['f%d.js' % n for n in range(i, files, steps)] for i in range(steps)]
    return '# Plan\n\n## 20. Implementation sequence\n\n' + '\n'.join(
        '%d. Step %d — Owns: %s' % (i + 1, i + 1, ', '.join('`%s`' % p for p in paths) or '`x%d.js`' % i)
        for i, paths in enumerate(owns)) + '\n'


class AppClass(unittest.TestCase):
    def classify(self, interp=None, steps=9, files=17):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.uncle/workflow/documents').mkdir(parents=True)
            (root / '.uncle/docs').mkdir()
            (root / '.uncle/docs/REQUIREMENTS.md').write_text('# Application brief\n\nbuild a calculator\n')
            if interp is not None:
                (root / c.INTERPRETATION).write_text(json.dumps(interp))
            (root / 'plan.md').write_text(plan(steps, files))
            f = c.features('app', root, root / 'plan.md')
            return c.deterministic_class(f), f

    def test_a_small_interpretation_is_small_even_with_a_big_scaffold(self):
        cls, f = self.classify(interpretation())
        self.assertEqual((f['requirements'], f['criteria']), (5, 6))
        self.assertGreaterEqual(f['owned_files'], 15)          # the plan alone would say large
        self.assertEqual(cls, 'small')
        profile = c.profile(cls, f)
        self.assertEqual(profile['execute_workers'], 4)
        self.assertEqual(profile['checklist_lenses'], ['coverage', 'invariants', 'regressions'])

    def test_many_requirements_are_not_small(self):
        self.assertNotEqual(self.classify(interpretation(requirements=9))[0], 'small')
        self.assertNotEqual(self.classify(interpretation(criteria=12))[0], 'small')

    def test_a_ballooned_plan_is_not_small(self):
        self.assertNotEqual(self.classify(interpretation(), steps=14, files=40)[0], 'small')

    def test_a_risk_word_in_a_requirement_makes_it_risky(self):
        cls, f = self.classify(interpretation(required_extra=' R-6 Users sign in with a password.'))
        self.assertEqual(cls, 'risky')
        self.assertIn('password', f['risk_hits'])

    def test_a_risk_word_in_a_non_goal_or_an_assumption_does_not(self):
        cls, f = self.classify(interpretation(non_goals='N-1 No payment processing. N-2 No password login.'))
        self.assertEqual(f['risk_hits'], [])
        self.assertEqual(cls, 'small')

    def test_no_interpretation_keeps_the_plan_size_rule(self):
        cls, f = self.classify(None)
        self.assertEqual((f['requirements'], f['criteria']), (0, 0))
        self.assertEqual(cls, 'large')

    def test_a_malformed_interpretation_is_ignored(self):
        cls, _ = self.classify({'sections': 'not a dict'})
        self.assertEqual(cls, 'large')

    def test_a_change_is_unaffected(self):
        f = {'family': 'change', 'risk_hits': [], 'steps': 9, 'owned_files': 17, 'directories': 3, 'criteria': 6,
             'requirements': 5, 'file_kinds': {'docs': 0, 'test': 0, 'scaffold': 0, 'app': 17}}
        self.assertFalse(c.app_is_small(f))
        self.assertEqual(c.deterministic_class(f), 'large')


if __name__ == '__main__':
    unittest.main()
