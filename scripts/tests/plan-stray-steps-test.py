"""A steps block outside the implementation sequence (a rollback list that names files) is demoted to a list, not rejected for reusing step numbers."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import plan_model as pm


def steps(*titles, owns=None):
    return {'kind': 'steps', 'steps': [{'number': n, 'title': t, 'text': 'do it', 'owns': (owns or {}).get(n, 'src/a.js'),
                                        'depends_on': ''} for n, t in enumerate(titles, 1)]}


def prose(text):
    return {'kind': 'prose', 'text': text}


def plan(*sections):
    return pm.model_from_flat([{'heading': h, 'blocks': b} for h, b in sections], 'Plan')


class StrayStepBlocks(unittest.TestCase):
    def test_a_rollback_list_that_names_files_no_longer_collides_with_the_sequence(self):
        model = plan(('Summary', [prose('x')]),
                     ('Rollback plan', [steps('Revert the commit', 'Restore the ignore file', owns={2: '.gitignore'})]),
                     ('Implementation sequence', [steps('Edit', 'Test', 'Docs', 'Verify')]))
        self.assertEqual([s['number'] for s in pm.steps_of(model)], [1, 2, 3, 4])
        rollback = model['sections'][1]['blocks'][0]
        self.assertEqual(rollback['kind'], 'list')
        self.assertTrue(rollback['ordered'])

    def test_the_demoted_list_keeps_its_text_numbers_and_files(self):
        model = plan(('Rollback plan', [steps('Revert the commit', 'Restore the ignore file', owns={2: '.gitignore'})]),
                     ('Implementation sequence', [steps('Edit', 'Test')]))
        items = model['sections'][0]['blocks'][0]['items']
        self.assertEqual([i['number'] for i in items], [1, 2])
        self.assertIn('Revert the commit', items[0]['text'])
        self.assertIn('Files: .gitignore', items[1]['text'])
        self.assertIn('Restore the ignore file', pm.render(model))

    def test_the_implementation_section_wins_wherever_it_is(self):
        model = plan(('Implementation sequence', [steps('Edit', 'Test')]),
                     ('Manual verification', [steps('Open it', 'Click', 'Look')]))
        self.assertEqual([s['title'] for s in pm.steps_of(model)], ['Edit', 'Test'])

    def test_with_no_implementation_heading_the_largest_steps_block_is_the_sequence(self):
        model = plan(('Work', [steps('A', 'B', 'C')]), ('Rollback', [steps('Undo')]))
        self.assertEqual([s['title'] for s in pm.steps_of(model)], ['A', 'B', 'C'])
        self.assertEqual(model['sections'][1]['blocks'][0]['kind'], 'list')

    def test_a_single_steps_block_and_a_plan_with_none_are_untouched(self):
        model = plan(('Implementation sequence', [steps('Edit', 'Test')]))
        self.assertEqual(model['sections'][0]['blocks'][0]['kind'], 'steps')
        self.assertEqual(plan(('Summary', [prose('x')]))['sections'][0]['blocks'][0]['kind'], 'prose')

    def test_real_numbering_errors_in_the_sequence_are_still_rejected(self):
        bad = {'kind': 'steps', 'steps': [{'number': 1, 'title': 'A', 'text': '', 'owns': 'a.js', 'depends_on': ''},
                                          {'number': 1, 'title': 'B', 'text': '', 'owns': 'b.js', 'depends_on': ''}]}
        with self.assertRaises(pm.PlanError):
            plan(('Implementation sequence', [bad]))


if __name__ == '__main__':
    unittest.main()
