"""A small application gets a small plan: tighter step/file targets and section word caps scaled down; everything else is untouched."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import change_class as c
import project_plan_sections as sections


class SmallPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.old)
        Path('.uncle/workflow').mkdir(parents=True)

    def classify(self, cls, family='app'):
        Path('.uncle/workflow/change-class.json').write_text(json.dumps({'class': cls, 'family': family}))

    def test_without_a_class_the_caps_are_unchanged(self):
        for name, cap in sections.WORD_CAP.items():
            self.assertEqual(sections.scaled_cap(name), cap, name)

    def test_a_small_application_gets_much_shorter_sections(self):
        self.classify('small')
        for name, cap in sections.WORD_CAP.items():
            if name == 'commands':
                continue
            scaled = sections.scaled_cap(name)
            self.assertLess(scaled, cap, name)
            self.assertGreaterEqual(scaled, c.PLAN_WORD_FLOOR, name)
        self.assertLessEqual(sum(sections.scaled_cap(n) for n in sections.WORD_CAP), 0.5 * sum(sections.WORD_CAP.values()))

    def test_the_verification_commands_section_is_never_squeezed(self):
        self.classify('small')
        self.assertEqual(sections.scaled_cap('commands'), sections.WORD_CAP['commands'])

    def test_larger_classes_and_change_requests_are_untouched(self):
        for cls in ('standard', 'large', 'risky'):
            self.classify(cls)
            self.assertEqual(sections.scaled_cap('behaviors'), sections.WORD_CAP['behaviors'], cls)
        self.classify('small', family='change')
        self.assertEqual(sections.scaled_cap('behaviors'), sections.WORD_CAP['behaviors'])

    def test_the_note_the_worker_sees_carries_the_scaled_number(self):
        self.classify('small')
        self.assertIn('about %d words' % sections.scaled_cap('tests'), sections.length_note('tests'))
        self.assertNotIn('about %d words' % sections.WORD_CAP['tests'], sections.length_note('tests'))

    def test_the_budget_asks_for_a_small_plan_and_keeps_the_reclassification_ceiling(self):
        self.classify('small')
        text = c.plan_budget('.')
        self.assertIn('at most %d implementation steps and %d owned files' % (c.PLAN_TARGET['steps'], c.PLAN_TARGET['files']), text)
        self.assertIn('beyond %d steps or %d files is reclassified' % (c.APP_SMALL['steps'], c.APP_SMALL['files']), text)
        self.assertLess(c.PLAN_TARGET['steps'], c.APP_SMALL['steps'])
        self.assertLess(c.PLAN_TARGET['files'], c.APP_SMALL['files'])

    def test_no_budget_for_anything_else(self):
        for cls in ('standard', 'large', 'risky'):
            self.classify(cls)
            self.assertEqual(c.plan_budget('.'), '', cls)


if __name__ == '__main__':
    unittest.main()
