"""Risk keywords are hints about meaning: context rules drop obvious non-risks, the model may waive a benign hit with a reason, and
nothing security-critical can be waived."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import change_class as c

PROMPT = Path(__file__).resolve().parents[2] / 'prompts/classify-change.md'


class Context(unittest.TestCase):
    def test_the_calculator_sentence_is_not_a_risk(self):
        text = 'Arithmetic: digits, decimal point, + - * /, equals, clear (AC), backspace/delete, sign toggle and percent are not required.'
        self.assertEqual(c.risk_hits_in(text), set())

    def test_a_delete_key_is_not_data_deletion(self):
        for text in ('The delete key removes the last digit.', 'A delete button clears the entry.', 'Pressing delete removes a character.'):
            self.assertEqual(c.risk_hits_in(text), set(), text)

    def test_deleting_data_still_counts(self):
        for text in ('Users can delete their account.', 'Deletes all user records after 30 days.', 'Destroy the old backups.'):
            self.assertTrue(c.risk_hits_in(text), text)

    def test_an_out_of_scope_sentence_is_dropped_but_its_neighbour_is_not(self):
        self.assertEqual(c.risk_hits_in('Payment processing is required. Authentication is out of scope.'), {'payment'})
        self.assertEqual(c.risk_hits_in('N-1 No payment processing, which is a non-goal.'), set())

    def test_an_optional_feature_still_counts(self):
        self.assertTrue(c.risk_hits_in('Users may optionally sign in with a password.'))


def features(**overrides):
    base = {'family': 'app', 'request_chars': 10, 'plan_chars': 10, 'steps': 0, 'owned_files': 0, 'directories': 0,
            'file_kinds': {'test': 0, 'docs': 0, 'scaffold': 0, 'app': 0}, 'criteria': 5, 'requirements': 5,
            'risk_hits': ['delete'], 'owned_sample': [], 'plan_sha': 'x'}
    base.update(overrides)
    return base


class Waivers(unittest.TestCase):
    def waive(self, hit, reason='a delete key on a calculator, not data deletion', hits=('delete',)):
        return c.apply_waivers(features(risk_hits=list(hits)), {'waived_risk_hits': [{'hit': hit, 'reason': reason}]})

    def test_a_benign_hit_with_a_reason_is_waived(self):
        f, waived = self.waive('delete')
        self.assertEqual(f['risk_hits'], [])
        self.assertEqual([w['hit'] for w in waived], ['delete'])
        self.assertEqual(c.deterministic_class(f), 'small')

    def test_security_critical_words_cannot_be_waived(self):
        for word in ('password', 'secret', 'credentials', 'access token', 'authentication', 'encryption', 'signing', 'payment',
                     'attestation', 'force-push', 'security', 'privilege', 'billing', 'sql injection'):
            f, waived = self.waive(word, hits=(word,))
            self.assertEqual(f['risk_hits'], [word], word)
            self.assertEqual(waived, [], word)

    def test_a_waiver_needs_a_real_reason_and_a_hit_that_was_found(self):
        self.assertEqual(self.waive('delete', reason='')[1], [])
        self.assertEqual(self.waive('delete', reason='fine')[1], [])
        self.assertEqual(self.waive('migrate', hits=('delete',))[1], [])        # not among the hits
        self.assertEqual(c.apply_waivers(features(), {'waived_risk_hits': 'delete'})[1], [])
        self.assertEqual(c.apply_waivers(features(), None)[1], [])

    def test_a_waiver_for_one_hit_leaves_the_others(self):
        f, waived = c.apply_waivers(features(risk_hits=['delete', 'password']), {'waived_risk_hits': [
            {'hit': 'delete', 'reason': 'a delete key, not data deletion'}, {'hit': 'password', 'reason': 'it is only a label here'}]})
        self.assertEqual(f['risk_hits'], ['password'])
        self.assertEqual(c.deterministic_class(f), 'risky')


class EndToEnd(unittest.TestCase):
    def project(self, required):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / '.uncle/workflow/documents').mkdir(parents=True)
        (root / '.uncle/docs').mkdir()
        (root / '.uncle/docs/REQUIREMENTS.md').write_text('# brief\n')
        (root / c.INTERPRETATION).write_text(json.dumps({'sections': {
            'required_functionality': required,
            'definition_of_done': '| D-1 | a |\n| D-2 | b |',
        }}))
        (root / 'interp.md').write_text('x')
        (root / 'plan.md').write_text('# Plan\n\n## 20. Implementation sequence\n\n1. One — Owns: `a.js`\n')
        return root

    def test_the_calculator_text_classifies_as_small_with_no_help_from_the_model(self):
        root = self.project('R-1 React calculator. R-2 Groovy theme. Optional: backspace/delete, sign toggle and percent are not required.')
        f = c.features('app', root, root / 'interp.md')
        self.assertEqual(f['risk_hits'], [])
        self.assertEqual(c.deterministic_class(f), 'small')

    def test_a_model_waiver_changes_the_class_and_is_recorded(self):
        root = self.project('R-1 Users can delete a saved calculation. R-2 Groovy theme.')
        self.assertEqual(c.deterministic_class(c.features('app', root, root / 'interp.md')), 'risky')
        proposal = {'class': 'small', 'waived_risk_hits': [{'hit': 'delete', 'reason': 'removes one history row on screen, no data store'}]}
        result = c.build('app', root, root / 'interp.md', proposal, 'model')
        self.assertEqual(result['class'], 'small')
        self.assertEqual(result['waived_risk_hits'][0]['hit'], 'delete')
        self.assertIn('delete', result['features']['risk_hits'])            # what was matched is still on the record
        self.assertEqual(result['checklist_lenses'], ['coverage', 'invariants', 'regressions'])

    def test_without_a_waiver_the_keyword_still_wins_over_the_models_class(self):
        root = self.project('R-1 Users can delete a saved calculation.')
        result = c.build('app', root, root / 'interp.md', {'class': 'small'}, 'model')
        self.assertEqual(result['class'], 'risky')

    def test_the_waiver_survives_the_recheck_after_planning(self):
        root = self.project('R-1 Users can delete a saved calculation. R-2 Groovy theme.')
        proposal = {'class': 'small', 'waived_risk_hits': [{'hit': 'delete', 'reason': 'removes one history row on screen'}]}
        c.write(root, c.build('app', root, root / 'interp.md', proposal, 'model'))
        self.assertEqual(c.recheck('app', root, root / 'plan.md'), '')
        self.assertEqual(c.get(root, 'class'), 'small')

    def test_the_model_is_told_how_to_waive(self):
        root = self.project('R-1 something.')
        out = root / 'p.md'
        c.prompt('app', root, root / 'interp.md', out, PROMPT)
        text = out.read_text()
        self.assertIn('waived_risk_hits', text)
        self.assertIn('cannot be waived', text)


if __name__ == '__main__':
    unittest.main()
