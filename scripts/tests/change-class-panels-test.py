"""The class profile sizes the stages after planning: panel lenses, execute workers, and whether to implement in one session."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import change_class as c


def features(**overrides):
    base = {'family': 'change', 'risk_hits': [], 'criteria': 1, 'file_kinds': {'test': 1}}
    base.update(overrides)
    return base


class Profile(unittest.TestCase):
    def test_test_review_is_never_narrowed_because_each_lens_owns_required_rows(self):
        for cls in c.CLASSES:
            self.assertEqual(c.profile(cls, features())['test_review_lenses'], ['coverage', 'assertions', 'oracle'], cls)

    def test_the_small_classes_get_smaller_panels(self):
        docs = c.profile('docs', features())
        self.assertEqual(docs['checklist_lenses'], ['coverage'])
        self.assertEqual(docs['final_audit_lenses'], ['verification', 'waivers'])
        self.assertEqual(docs['test_review_lenses'], ['coverage', 'assertions', 'oracle'])
        self.assertEqual(docs['execute_workers'], 2)
        tests = c.profile('test-only', features())
        self.assertEqual(tests['final_audit_lenses'], ['verification', 'regression', 'waivers'])
        self.assertEqual(c.profile('small', features())['execute_workers'], 4)

    def test_standard_and_above_keep_every_panel_in_full(self):
        for cls in ('standard', 'large', 'risky'):
            p = c.profile(cls, features())
            self.assertEqual(p['checklist_lenses'], list(c.PANEL_FULL['checklist']), cls)
            self.assertEqual(p['final_audit_lenses'], list(c.PANEL_FULL['final_audit']), cls)
            self.assertEqual(p['test_review_lenses'], list(c.PANEL_FULL['test_review']), cls)
            self.assertEqual(p['execute_workers'], 8, cls)
            self.assertEqual(p['implement_mode'], 'auto', cls)

    def test_a_risk_keyword_keeps_everything_full_whatever_the_class(self):
        p = c.profile('docs', features(risk_hits=['delete']))
        self.assertEqual(p['checklist_lenses'], list(c.PANEL_FULL['checklist']))
        self.assertEqual(p['final_audit_lenses'], list(c.PANEL_FULL['final_audit']))
        self.assertEqual(p['execute_workers'], 8)
        self.assertEqual(p['implement_mode'], 'auto')

    def test_only_small_changes_implement_in_one_session(self):
        for cls in ('docs', 'test-only', 'small'):
            self.assertEqual(c.profile(cls, features())['implement_mode'], 'single', cls)
        self.assertEqual(c.profile('small', features(family='app'))['implement_mode'], 'auto')

    def test_every_panel_lens_is_one_the_panel_knows(self):
        for name, table in c.PANELS.items():
            for cls, lenses in table.items():
                self.assertTrue(set(lenses) <= set(c.PANEL_FULL[name]), (name, cls))
                self.assertTrue(lenses, (name, cls))


if __name__ == '__main__':
    unittest.main()
