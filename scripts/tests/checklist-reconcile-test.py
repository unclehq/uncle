"""Applying a reconciler's edits to the independent checklist draft: what is allowed, what is refused, and the audit it leaves."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import checklist_reconcile as r

KIND = r.PACKET_KIND


def check(ident, required=True, **extra):
    base = {'id': ident, 'section': 'Coverage', 'exact_action': 'do ' + ident, 'expected_result': 'see ' + ident,
            'evidence_to_capture': 'screenshot', 'required': required, 'depends_on': [], 'exclusive_resources': []}
    base.update(extra)
    return base


def draft(*checks):
    return {'schema': 'uncle.artifact/v1', 'kind': 'manual-checklist', 'checks': list(checks)}


def packet(**edits):
    return dict({'schema': 'uncle.artifact/v1', 'kind': KIND, 'drop': [], 'modify': [], 'add': []}, **edits)


GOOD = 'The built app no longer has this.'


class Apply(unittest.TestCase):
    def setUp(self):
        self.draft = draft(*(check('MC-%d' % n) for n in (100, 101, 102, 103)))

    def test_an_empty_packet_keeps_the_draft_exactly(self):
        final, audit = r.apply(self.draft, packet())
        self.assertEqual(final['checks'], self.draft['checks'])
        self.assertEqual((audit['draft_checks'], audit['final_checks']), (4, 4))

    def test_a_drop_with_a_reason_removes_the_check_and_is_audited(self):
        final, audit = r.apply(self.draft, packet(drop=[{'id': 'MC-101', 'reason': GOOD}]))
        self.assertEqual([c['id'] for c in final['checks']], ['MC-100', 'MC-102', 'MC-103'])
        self.assertEqual(audit['dropped'], [{'id': 'MC-101', 'reason': GOOD}])

    def test_a_modify_changes_only_the_named_fields(self):
        final, audit = r.apply(self.draft, packet(modify=[{'id': 'MC-102', 'reason': GOOD, 'fields': {
            'exact_action': 'press the key labelled 5', 'depends_on': ['MC-100']}}]))
        changed = next(c for c in final['checks'] if c['id'] == 'MC-102')
        self.assertEqual(changed['exact_action'], 'press the key labelled 5')
        self.assertEqual(changed['depends_on'], ['MC-100'])
        self.assertEqual(changed['expected_result'], 'see MC-102')
        self.assertEqual(audit['modified'][0]['fields'], ['depends_on', 'exact_action'])

    def test_an_add_is_numbered_by_the_driver_after_every_lens_range(self):
        final, audit = r.apply(self.draft, packet(add=[
            {'exact_action': 'a', 'expected_result': 'b', 'evidence_to_capture': 'c', 'required': True, 'reason': GOOD},
            {'exact_action': 'd', 'expected_result': 'e', 'evidence_to_capture': 'f', 'required': False, 'reason': GOOD,
             'section': 'Gaps', 'depends_on': ['MC-100']}]))
        added = [c for c in final['checks'] if c['id'] not in ('MC-100', 'MC-101', 'MC-102', 'MC-103')]
        self.assertEqual([c['id'] for c in added], ['MC-901', 'MC-902'])
        self.assertEqual((added[0]['section'], added[1]['section'], added[1]['depends_on']), ('Reconciliation', 'Gaps', ['MC-100']))
        self.assertEqual([a['id'] for a in audit['added']], ['MC-901', 'MC-902'])

    def test_added_ids_skip_ones_already_taken(self):
        base = draft(check('MC-100'), check('MC-901'), check('MC-902'), check('MC-903'))
        final, _ = r.apply(base, packet(add=[{'exact_action': 'a', 'expected_result': 'b', 'evidence_to_capture': 'c', 'reason': GOOD}]))
        self.assertEqual(final['checks'][-1]['id'], 'MC-904')

    def test_a_dependency_on_a_dropped_check_is_removed_and_recorded_not_fatal(self):
        base = draft(check('MC-100'), check('MC-101', depends_on=['MC-100', 'MC-102']), check('MC-102'))
        final, audit = r.apply(base, packet(drop=[{'id': 'MC-100', 'reason': GOOD}]))
        self.assertEqual(next(c for c in final['checks'] if c['id'] == 'MC-101')['depends_on'], ['MC-102'])
        self.assertEqual(audit['repaired_dependencies'], [{'id': 'MC-101', 'removed': ['MC-100']}])

    def refused(self, edits, base=None):
        with self.assertRaises(ValueError) as ctx:
            r.apply(base or self.draft, packet(**edits))
        return str(ctx.exception)

    def test_dropping_most_of_the_draft_is_refused(self):
        message = self.refused({'drop': [{'id': 'MC-%d' % n, 'reason': GOOD} for n in (100, 101, 102)]})
        self.assertIn('independent part of the review', message)
        r.apply(self.draft, packet(drop=[{'id': 'MC-100', 'reason': GOOD}, {'id': 'MC-101', 'reason': GOOD}]))   # half is allowed

    def test_a_required_check_cannot_be_loosened(self):
        self.assertIn('cannot be loosened', self.refused({'modify': [{'id': 'MC-100', 'reason': GOOD, 'fields': {'required': False}}]}))
        base = draft(check('MC-100', required=False))
        final, _ = r.apply(base, packet(modify=[{'id': 'MC-100', 'reason': GOOD, 'fields': {'required': True}}]))
        self.assertTrue(final['checks'][0]['required'])

    def test_an_expectation_cannot_be_emptied_or_a_foreign_field_changed(self):
        self.assertIn('cannot be emptied', self.refused({'modify': [{'id': 'MC-100', 'reason': GOOD, 'fields': {'expected_result': '  '}}]}))
        self.assertIn('cannot be emptied', self.refused({'modify': [{'id': 'MC-100', 'reason': GOOD, 'fields': {'exact_action': ''}}]}))
        self.assertIn('not a field', self.refused({'modify': [{'id': 'MC-100', 'reason': GOOD, 'fields': {'id': 'MC-999'}}]}))

    def test_every_edit_needs_a_real_reason(self):
        for edits in ({'drop': [{'id': 'MC-100', 'reason': 'no'}]},
                      {'modify': [{'id': 'MC-100', 'reason': '', 'fields': {'section': 'x'}}]},
                      {'add': [{'exact_action': 'a', 'expected_result': 'b', 'evidence_to_capture': 'c'}]}):
            self.assertIn('reason', self.refused(edits))

    def test_unknown_duplicate_and_conflicting_edits_are_refused(self):
        self.assertIn('no such check', self.refused({'drop': [{'id': 'MC-777', 'reason': GOOD}]}))
        self.assertIn('no such check', self.refused({'modify': [{'id': 'MC-777', 'reason': GOOD, 'fields': {'section': 'x'}}]}))
        self.assertIn('twice', self.refused({'drop': [{'id': 'MC-100', 'reason': GOOD}, {'id': 'MC-100', 'reason': GOOD}]}))
        self.assertIn('both dropped and modified', self.refused({'drop': [{'id': 'MC-100', 'reason': GOOD}],
                                                                  'modify': [{'id': 'MC-100', 'reason': GOOD, 'fields': {'section': 'x'}}]}))
        self.assertIn('at most', self.refused({'add': [{'exact_action': 'a', 'expected_result': 'b', 'evidence_to_capture': 'c',
                                                         'reason': GOOD}] * (r.MAX_ADDS + 1)}))

    def test_a_packet_or_draft_of_the_wrong_kind_is_refused(self):
        with self.assertRaises(ValueError):
            r.apply(self.draft, {'kind': 'something-else'})
        with self.assertRaises(ValueError):
            r.apply({'kind': 'manual-checklist'}, packet())

    def test_the_command_line_writes_the_final_checklist_and_the_audit_or_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'd.json').write_text(json.dumps(self.draft))
            (root / 'p.json').write_text(json.dumps(packet(drop=[{'id': 'MC-100', 'reason': GOOD}])))
            run = lambda *a: subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/checklist_reconcile.py'), 'apply', *a],
                                            capture_output=True, text=True)
            done = run(str(root / 'd.json'), str(root / 'p.json'), str(root / 'o.json'), str(root / 'a.json'))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(len(json.loads((root / 'o.json').read_text())['checks']), 3)
            self.assertEqual(json.loads((root / 'a.json').read_text())['dropped'][0]['id'], 'MC-100')
            (root / 'p.json').write_text('not json')
            bad = run(str(root / 'd.json'), str(root / 'p.json'), str(root / 'o2.json'), str(root / 'a2.json'))
            self.assertEqual(bad.returncode, 1)
            self.assertIn('refused', bad.stderr)
            self.assertFalse((root / 'o2.json').exists())


if __name__ == '__main__':
    unittest.main()
