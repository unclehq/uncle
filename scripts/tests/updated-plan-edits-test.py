#!/usr/bin/env python3
"""Parallel updated-plan writers: slicing, and a merge that is exact or refuses."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import updated_plan_edits as edits

NARRATIVE = '''# Project plan

## 1. Overview
Alpha line.
Beta line.

## 2. Invariants
I-1 holds always.
I-2 holds sometimes.

## 3. Tests
T-1 checks it.
'''
COMMANDS = 'npm test\n# Frozen verification paths: tests/a.test.js'


def plan():
    return {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': NARRATIVE,
            'verification_commands': COMMANDS}


def row(finding):
    return {'finding': finding, 'disposition': 'Accepted', 'reason': 'r', 'plan_change': 'c'}


class Merge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / 'plan.json').write_text(json.dumps(plan()))
        (self.dir / 'slices.tsv').write_text('1\tAR-1,AR-2\n2\tAR-3,AR-4\n')

    def tearDown(self):
        self.tmp.cleanup()

    def deliver(self, one, two, extra=None):
        for name, ids, patch in (('1', ('AR-1', 'AR-2'), one), ('2', ('AR-3', 'AR-4'), two)):
            body = {'dispositions': [row(i) for i in ids], 'patch': patch}
            body.update((extra or {}).get(name, {}))
            (self.dir / ('%s.json' % name)).write_text(json.dumps(body))

    def merge(self):
        out = self.dir / 'out.json'
        edits.merge(self.dir / 'plan.json', self.dir / 'slices.tsv', self.dir, out)
        return json.loads(out.read_text())

    def test_disjoint_edits_merge_into_one_patch(self):
        self.deliver({'replace_text': [{'heading': '## 1. Overview', 'old': 'Alpha line.', 'new': 'A.'}]},
                     {'replace_text': [{'heading': '## 1. Overview', 'old': 'Beta line.', 'new': 'B.'},
                                       {'heading': '## 3. Tests', 'old': 'T-1', 'new': 'T-9'}]})
        result = self.merge()
        self.assertEqual(len(result['patch']['replace_text']), 3)
        self.assertEqual([d['finding'] for d in result['dispositions']], ['AR-1', 'AR-2', 'AR-3', 'AR-4'])
        self.assertEqual(result['protected_verification_paths'], 'tests/a.test.js')
        self.assertEqual(result['verification_commands'], COMMANDS)
        applied = edits.apply_patch(NARRATIVE, result['patch'])
        self.assertIn('A.\nB.', applied)
        self.assertIn('T-9', applied)

    def test_same_text_changed_twice_needs_a_resolution(self):
        self.deliver({'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'x'}]},
                     {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds', 'new': 'y'}]})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'text')

    def test_whole_section_rewritten_twice_is_refused(self):
        patch = {'edit_sections': [{'heading': '## 3. Tests', 'content': 'x'}]}
        self.deliver(patch, patch)
        with self.assertRaisesRegex(edits.Conflict, 'rewritten'):
            self.merge()

    def test_section_rewrite_plus_line_edit_needs_a_resolution(self):
        self.deliver({'edit_sections': [{'heading': '## 3. Tests', 'content': 'x'}]},
                     {'replace_text': [{'heading': '## 3. Tests', 'old': 'T-1', 'new': 'T-2'}]})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'section')

    def test_same_insert_twice_is_refused(self):
        patch = {'insert_sections': [{'content': '## 4. New\nbody', 'after': '## 3. Tests'}]}
        self.deliver(patch, patch)
        with self.assertRaisesRegex(edits.Conflict, 'both insert'):
            self.merge()

    def test_text_not_in_base_needs_a_resolution(self):
        self.deliver({'replace_text': [{'heading': '## 1. Overview', 'old': 'Gamma', 'new': 'x'}]}, {})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'missing')

    def test_an_ambiguous_old_text_needs_a_resolution_not_a_crash(self):
        self.deliver({'replace_text': [{'heading': '## 1. Overview', 'old': 'line', 'new': 'x'}]}, {})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'missing')

    def test_an_ambiguous_old_text_is_fine_when_it_says_all(self):
        self.deliver({'replace_text': [{'heading': '## 1. Overview', 'old': 'line', 'new': 'x', 'all': True}]}, {})
        self.assertEqual(len(self.merge()['patch']['replace_text']), 1)

    def test_an_edit_for_a_section_that_does_not_exist_needs_a_resolution(self):
        self.deliver({'replace_text': [{'heading': '## 9. Nowhere', 'old': 'Alpha line.', 'new': 'x'}]}, {})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'missing')
        self.assertIn('## 3. Tests', caught.exception.groups[0]['context'])

    def test_missing_disposition_is_refused(self):
        self.deliver({}, {})
        data = json.loads((self.dir / '2.json').read_text())
        data['dispositions'] = data['dispositions'][:1]
        (self.dir / '2.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(edits.Conflict, 'AR-4'):
            self.merge()

    def test_disposition_for_a_finding_the_writer_does_not_own_is_ignored(self):
        self.deliver({}, {})
        data = json.loads((self.dir / '1.json').read_text())
        data['dispositions'].append(row('AR-3'))
        (self.dir / '1.json').write_text(json.dumps(data))
        found = [d['finding'] for d in self.merge()['dispositions']]
        self.assertEqual(found, ['AR-1', 'AR-2', 'AR-3', 'AR-4'])

    def test_command_edits_from_several_writers_merge_line_by_line(self):
        (self.dir / 'plan.json').write_text(json.dumps(dict(plan(), verification_commands='a one\nb two\nc three\n# Frozen verification paths: tests/a.test.js')))
        self.deliver({}, {}, {'1': {'commands_replace': [{'old': 'a one', 'new': 'A'}]},
                              '2': {'commands_replace': [{'old': 'c three', 'new': 'C'}]}})
        self.assertEqual(self.merge()['verification_commands'], 'A\nb two\nC\n# Frozen verification paths: tests/a.test.js')

    def test_the_same_edit_from_two_writers_is_one_edit(self):
        row_ = {'old': 'npm test', 'new': 'npm ci && npm test'}
        self.deliver({'replace_text': [{'heading': '## 3. Tests', 'old': 'T-1', 'new': 'T-2'}]},
                     {'replace_text': [{'heading': '## 3. Tests', 'old': 'T-1', 'new': 'T-2'}]},
                     {'1': {'commands_replace': [row_]}, '2': {'commands_replace': [row_]}})
        result = self.merge()
        self.assertEqual(len(result['patch']['replace_text']), 1)
        self.assertTrue(result['verification_commands'].startswith('npm ci && npm test'))

    def test_two_writers_changing_the_same_command_differently_needs_a_resolution(self):
        self.deliver({}, {}, {'1': {'commands_replace': [{'old': 'npm test', 'new': 'a'}]},
                              '2': {'commands_replace': [{'old': 'npm test', 'new': 'b'}]}})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'command')

    def test_commands_written_whole_and_changed_are_refused(self):
        self.deliver({}, {}, {'2': {'verification_commands': 'npm run check'}})
        with self.assertRaisesRegex(edits.Conflict, 'commands_replace'):
            self.merge()

    def test_commands_written_whole_but_unchanged_are_accepted(self):
        self.deliver({}, {}, {'2': {'verification_commands': COMMANDS}})
        self.assertEqual(self.merge()['verification_commands'], COMMANDS)

    def test_a_command_edit_naming_text_that_is_not_there_is_refused(self):
        self.deliver({}, {}, {'1': {'commands_replace': [{'old': 'nothing', 'new': 'x'}]}})
        with self.assertRaisesRegex(edits.Conflict, '0 times'):
            self.merge()

    def test_a_plan_without_protected_paths_needs_a_writer_to_supply_them(self):
        bare = plan()
        bare['verification_commands'] = 'npm test'
        (self.dir / 'plan.json').write_text(json.dumps(bare))
        self.deliver({}, {})
        with self.assertRaisesRegex(edits.Conflict, 'protected_verification_paths'):
            self.merge()
        self.deliver({}, {}, {'1': {'protected_verification_paths': 'tests/a.test.js'}})
        self.assertEqual(self.merge()['protected_verification_paths'], 'tests/a.test.js')

    def test_only_the_first_writer_is_told_to_own_the_fields(self):
        base = self.dir / 'b.md'
        base.write_text('BASE')
        edits.write_prompt(base, ['AR-1'], self.dir / 'one.md', owns_fields=True)
        edits.write_prompt(base, ['AR-2'], self.dir / 'two.md')
        self.assertIn('include it, complete', (self.dir / 'one.md').read_text())
        self.assertIn('first writer owns it', (self.dir / 'two.md').read_text())
        self.assertIn('commands_replace', (self.dir / 'two.md').read_text())

    def test_unreadable_delivery_is_refused(self):
        self.deliver({}, {})
        (self.dir / '2.json').write_text('not json')
        with self.assertRaises(edits.Conflict):
            self.merge()


class Resolve(unittest.TestCase):
    """Overlapping edits go to one resolver; everything else stays mechanical."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / 'plan.json').write_text(json.dumps(plan()))
        (self.dir / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n')
        one = [{'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'I-1 holds always, checked.'},
               {'heading': '## 1. Overview', 'old': 'Alpha line.', 'new': 'A.'}]
        two = [{'heading': '## 2. Invariants', 'old': 'I-1 holds', 'new': 'I-1 never fails'},
               {'heading': '## 3. Tests', 'old': 'T-1', 'new': 'T-9'}]
        for name, finding, ops in (('1', 'AR-1', one), ('2', 'AR-2', two)):
            (self.dir / ('%s.json' % name)).write_text(json.dumps(
                {'dispositions': [row(finding)], 'patch': {'replace_text': ops}}))

    def tearDown(self):
        self.tmp.cleanup()

    def merge(self, resolution=None):
        target = None
        if resolution is not None:
            target = self.dir / 'res.json'
            target.write_text(json.dumps(resolution))
        args = [self.dir / 'plan.json', self.dir / 'slices.tsv', self.dir, self.dir / 'out.json']
        edits.merge(*args, *([target] if target else []))
        return json.loads((self.dir / 'out.json').read_text())

    def answer(self, patch):
        return {'resolutions': [{'group': 'G1', 'patch': patch}]}

    def test_only_the_overlapping_edits_reach_the_resolver(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        prompt = (self.dir / 'prompts' / 'resolve-G1.md').read_text()
        self.assertIn('I-1 holds always.', prompt)
        self.assertNotIn('Alpha line', prompt)      # the edits that do not collide are not sent
        self.assertNotIn('T-9', prompt)
        self.assertEqual(len(json.loads((self.dir / 'conflicts.json').read_text())), 1)

    def test_a_resolution_replaces_the_group_and_the_rest_merges_unchanged(self):
        result = self.merge(self.answer({'replace_text': [
            {'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'I-1 never fails, checked.'}]}))
        applied = edits.apply_patch(NARRATIVE, result['patch'])
        self.assertIn('I-1 never fails, checked.', applied)
        self.assertNotIn('I-1 holds always, checked.', applied)
        self.assertIn('A.\n', applied)
        self.assertIn('T-9', applied)

    def test_a_miscopied_edit_is_replaced_by_the_resolver_and_the_rest_merges(self):
        (self.dir / '2.json').write_text(json.dumps({'dispositions': [row('AR-2')], 'patch': {'replace_text': [
            {'heading': '## 3. Tests', 'old': 'T-1 checks it, honestly.', 'new': 'T-9'}]}}))
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [row('AR-1')], 'patch': {'replace_text': [
            {'heading': '## 1. Overview', 'old': 'Alpha line.', 'new': 'A.'}]}}))
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        prompt = (self.dir / 'prompts' / 'resolve-G1.md').read_text()
        self.assertIn('T-1 checks it.', prompt)
        self.assertNotIn('Alpha line', prompt)
        result = self.merge(self.answer({'replace_text': [{'heading': '## 3. Tests', 'old': 'T-1 checks it.', 'new': 'T-9'}]}))
        applied = edits.apply_patch(NARRATIVE, result['patch'])
        self.assertIn('T-9', applied)
        self.assertIn('A.\n', applied)

    def test_each_group_gets_its_own_prompt_and_its_own_answer_file(self):
        (self.dir / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n3\tAR-3\n')
        (self.dir / '3.json').write_text(json.dumps({'dispositions': [row('AR-3')], 'patch': {'replace_text': [
            {'heading': '## 3. Tests', 'old': 'T-1 checks', 'new': 'T-1 verifies'}]}}))
        two = json.loads((self.dir / '2.json').read_text())
        two['patch']['replace_text'][1] = {'heading': '## 3. Tests', 'old': 'T-1 checks it.', 'new': 'T-9'}
        (self.dir / '2.json').write_text(json.dumps(two))
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        ids = sorted(g['id'] for g in caught.exception.groups)
        self.assertEqual(ids, ['G1', 'G2'])
        for gid in ids:
            self.assertTrue((self.dir / 'prompts' / ('resolve-%s.md' % gid)).exists())
        self.assertNotIn('Group G2', (self.dir / 'prompts' / 'resolve-G1.md').read_text())
        answers = {'G1': {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'r1'}]},
                   'G2': {'replace_text': [{'heading': '## 3. Tests', 'old': 'T-1 checks it.', 'new': 'r2'}]}}
        for gid, patch in answers.items():
            (self.dir / ('resolutions-%s.json' % gid)).write_text(json.dumps({'resolutions': [{'group': gid, 'patch': patch}]}))
        out = self.dir / 'out.json'
        edits.merge(self.dir / 'plan.json', self.dir / 'slices.tsv', self.dir, out, self.dir)
        applied = edits.apply_patch(NARRATIVE, json.loads(out.read_text())['patch'])
        self.assertIn('r1', applied)
        self.assertIn('r2', applied)

    def test_the_resolver_is_told_which_text_other_edits_already_changed(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        prompt = (self.dir / 'prompts' / 'resolve-G1.md').read_text()
        self.assertIn('must not touch', prompt)
        avoid = json.loads((self.dir / 'conflicts.json').read_text())[0]['avoid']
        self.assertEqual(avoid, [])             # every edit in that section is in the group
        # a kept edit in the same section as a group is named as off limits
        one = json.loads((self.dir / '1.json').read_text())
        one['patch']['replace_text'].append({'heading': '## 2. Invariants', 'old': 'I-2 holds sometimes.', 'new': 'I-2'})
        (self.dir / '1.json').write_text(json.dumps(one))
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.assertEqual(json.loads((self.dir / 'conflicts.json').read_text())[0]['avoid'], ['I-2 holds sometimes.'])
        self.assertIn('- `I-2 holds sometimes.`', (self.dir / 'prompts' / 'resolve-G1.md').read_text())

    def answer_file(self, gid, patch, **extra):
        row = {'group': gid, 'patch': patch}
        row.update(extra)
        (self.dir / ('resolutions-%s.json' % gid)).write_text(json.dumps({'resolutions': [row]}))

    def test_a_resolver_answer_quoting_text_that_is_not_there_is_caught_per_group(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always, honestly.', 'new': 'x'}]})
        bad = edits.check_resolutions(self.dir / 'plan.json', self.dir)
        self.assertEqual(list(bad), ['G1'])
        self.assertIn('not in section', bad['G1'])
        retry = (self.dir / 'prompts' / 'resolve-G1.retry.md').read_text()
        self.assertIn('previous answer was rejected', retry)
        self.assertIn('I-1 holds always, honestly.', retry)
        self.assertTrue(retry.startswith((self.dir / 'prompts' / 'resolve-G1.md').read_text()))

    def test_a_good_resolver_answer_passes_the_check(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'x'}]})
        self.assertEqual(edits.check_resolutions(self.dir / 'plan.json', self.dir), {})

    def test_a_missing_ambiguous_or_unknown_target_is_caught(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        for patch, word in (({'replace_text': [{'heading': '## 9. Nowhere', 'old': 'a', 'new': 'b'}]}, 'does not exist'),
                            ({'replace_text': [{'heading': '## 2. Invariants', 'old': 'holds', 'new': 'b'}]}, 'occurs 2 times'),
                            ({'edit_sections': [{'heading': '## 9. Nowhere', 'content': 'x'}]}, 'does not exist')):
            self.answer_file('G1', patch)
            self.assertIn(word, edits.check_resolutions(self.dir / 'plan.json', self.dir)['G1'])
        (self.dir / 'resolutions-G1.json').unlink()
        self.assertIn('no valid answer', edits.check_resolutions(self.dir / 'plan.json', self.dir)['G1'])

    def test_the_cli_check_exits_5_and_names_the_groups(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        cli = [sys.executable, str(LIB / 'updated_plan_edits.py'), 'check', str(self.dir / 'plan.json'), str(self.dir)]
        self.answer_file('G1', {'replace_text': [{'heading': '## 2. Invariants', 'old': 'nope', 'new': 'x'}]})
        done = subprocess.run(cli, capture_output=True, text=True)
        self.assertEqual((done.returncode, done.stdout.split()), (5, ['G1']))
        self.answer_file('G1', {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'x'}]})
        self.assertEqual(subprocess.run(cli, capture_output=True, text=True).returncode, 0)

    def test_a_missing_group_shows_the_resolver_the_closest_real_lines(self):
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [row('AR-1')], 'patch': {'replace_text': [
            {'heading': '## 3. Tests', 'old': 'T-1 checks it, truly.', 'new': 'x'}]}}))
        (self.dir / '2.json').write_text(json.dumps({'dispositions': [row('AR-2')], 'patch': {}}))
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        group = caught.exception.groups[0]
        self.assertEqual(group['kind'], 'missing')
        self.assertIn('T-1 checks it.', group['nearest'])
        self.assertIn('closest to what the writer quoted', (self.dir / 'prompts' / 'resolve-G1.md').read_text())

    def test_a_missing_answer_is_refused(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        with self.assertRaisesRegex(edits.Conflict, 'did not answer G1'):
            self.merge({'resolutions': []})

    def test_a_resolution_that_overlaps_a_kept_edit_is_refused(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        with self.assertRaisesRegex(edits.Conflict, 'same text'):
            self.merge(self.answer({'replace_text': [
                {'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'a'},
                {'heading': '## 2. Invariants', 'old': 'holds always', 'new': 'b'}]}))

    def test_a_resolution_citing_text_not_in_the_plan_is_refused(self):  # still strict after the resolver
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        with self.assertRaises(edits.Conflict):
            self.merge(self.answer({'replace_text': [{'heading': '## 2. Invariants', 'old': 'nothing', 'new': 'b'}]}))

    def test_an_identical_duplicate_of_a_replaced_edit_is_dropped_too(self):
        (self.dir / 'slices.tsv').write_text('1\tAR-1\n2\tAR-2\n3\tAR-3\n')
        (self.dir / '3.json').write_text(json.dumps({'dispositions': [row('AR-3')], 'patch': {'replace_text': [
            {'heading': '## 2. Invariants', 'old': 'I-1 holds', 'new': 'I-1 never fails'}]}}))
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        result = self.merge(self.answer({'replace_text': [
            {'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'resolved'}]}))
        self.assertEqual(edits.apply_patch(NARRATIVE, result['patch']).count('resolved'), 1)

    def test_the_cli_exits_3_for_overlap_and_0_with_a_resolution(self):
        cli = [sys.executable, str(LIB / 'updated_plan_edits.py'), 'merge', str(self.dir / 'plan.json'),
               str(self.dir / 'slices.tsv'), str(self.dir), str(self.dir / 'o.json')]
        self.assertEqual(subprocess.run(cli, capture_output=True).returncode, 3)
        (self.dir / 'res.json').write_text(json.dumps(self.answer({'replace_text': [
            {'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'r'}]})))
        self.assertEqual(subprocess.run(cli + [str(self.dir / 'res.json')], capture_output=True).returncode, 0)


class Slicing(unittest.TestCase):
    def test_few_findings_stay_one_call(self):
        self.assertEqual(edits.slices(['A', 'B', 'C']), [])

    def test_findings_are_split_evenly_and_in_order(self):
        ids = ['AR-%d' % n for n in range(1, 10)]
        self.assertEqual(edits.slices(ids), [('1', ids[:3]), ('2', ids[3:6]), ('3', ids[6:])])

    def test_writer_count_is_capped(self):
        rows = edits.slices(['AR-%d' % n for n in range(1, 61)])
        self.assertEqual(len(rows), edits.MAX_WRITERS)
        self.assertEqual(sum(len(ids) for _, ids in rows), 60)

    def test_cli_prints_tab_separated_rows_and_the_prompt_names_the_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / 'r.json'
            review.write_text(json.dumps({'findings': [{'id': 'AR-%d' % n} for n in range(1, 7)]}))
            out = subprocess.run([sys.executable, str(LIB / 'updated_plan_edits.py'), 'slices', str(review)],
                                 capture_output=True, text=True, check=True).stdout
            self.assertEqual(out.splitlines(), ['1\tAR-1,AR-2,AR-3', '2\tAR-4,AR-5,AR-6'])
            base = Path(tmp) / 'base.md'
            base.write_text('BASE')
            target = Path(tmp) / 'p.md'
            subprocess.run([sys.executable, str(LIB / 'updated_plan_edits.py'), 'prompt', str(base), 'AR-1,AR-2', str(target)],
                           check=True)
            text = target.read_text()
            self.assertTrue(text.startswith('BASE'))
            self.assertIn('AR-1, AR-2', text)


if __name__ == '__main__':
    unittest.main()
