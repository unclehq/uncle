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
        self.deliver({'replace_text': [{'heading': '## 9. Nowhere', 'old': 'Text nobody has.', 'new': 'x'}]}, {})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'missing')
        self.assertIn('## 3. Tests', caught.exception.groups[0]['context'])

    def test_an_edit_labelled_with_a_subsection_heading_goes_to_the_section_holding_its_text(self):
        # calculator-local: writers said `## 10.2 Test file inventory`; the plan has `### 10.2 ...` inside `## 10.`
        self.deliver({'replace_text': [{'heading': '## 2.1 Sometimes', 'old': 'I-2 holds sometimes.', 'new': 'I-2 holds.'}]}, {})
        patch = self.merge()['patch']['replace_text']
        self.assertEqual([op['heading'] for op in patch], ['## 2. Invariants'])

    def test_an_insert_that_is_not_a_section_goes_to_a_resolver_not_a_failed_merge(self):
        # calculator-local: a writer "inserted" a numbered step (`0. Regression baseline ...`) after a section
        self.deliver({'insert_sections': [{'after': '## 3. Tests', 'content': '0. Copy the baseline first.'}]}, {})
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        group = caught.exception.groups[0]
        self.assertEqual((group['kind'], group['heading']), ('missing', '## 3. Tests'))
        self.assertIn('T-1 checks it.', group['context'])
        resolution = {'resolutions': [{'group': group['id'], 'patch': {'replace_text': [
            {'heading': '## 3. Tests', 'old': 'T-1 checks it.', 'new': '0. Copy the baseline first.\nT-1 checks it.'}]}}]}
        out = self.dir / 'out.json'
        (self.dir / 'res.json').write_text(json.dumps(resolution))
        edits.merge(self.dir / 'plan.json', self.dir / 'slices.tsv', self.dir, out, self.dir / 'res.json')
        patch = json.loads(out.read_text())['patch']
        self.assertEqual(patch['insert_sections'], [])
        self.assertIn('0. Copy the baseline first.', edits.apply_patch(NARRATIVE, patch))

    def test_a_wrong_heading_is_not_retargeted_when_the_text_is_in_two_sections(self):
        self.deliver({'replace_text': [{'heading': '## 9. Nowhere', 'old': 'holds', 'new': 'x'}]}, {})
        with self.assertRaises(edits.NeedsResolution):
            self.merge()

    def test_a_resolver_answer_with_a_subsection_label_is_retargeted(self):
        answer = {'resolutions': [{'group': 'G1', 'patch': {'replace_text': [
            {'heading': '### 1.1 Lines', 'old': 'Beta line.', 'new': 'B'}]}}]}
        (self.dir / 'resolutions-G1.json').write_text(json.dumps(answer))
        rows = edits.read_resolutions(self.dir, NARRATIVE)['resolutions']
        self.assertEqual(rows[0]['patch']['replace_text'][0]['heading'], '## 1. Overview')

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

    def test_a_command_edit_naming_text_that_is_not_there_is_left_out_and_recorded(self):
        self.deliver({}, {}, {'1': {'commands_replace': [{'old': 'nothing', 'new': 'x'}]}})
        result = self.merge()
        self.assertEqual(result['verification_commands'], plan()['verification_commands'].strip())
        self.assertIn('could not be placed', result['dispositions'][0]['reason'])

    def test_a_command_edit_with_a_near_miss_quote_goes_to_the_line_it_meant(self):
        commands = 'npm ci\nnpx vitest run --reporter=dot\nnpx playwright test'
        placed, aside = edits.place_commands([('1', 'npx vitest run --reporter dot', 'npx vitest run')], commands)
        self.assertEqual((placed, aside), ([('1', 'npx vitest run --reporter=dot', 'npx vitest run')], {}))

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

    def test_a_near_miss_copy_is_corrected_to_the_passage_it_meant(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always', 'new': 'x'}]})
        self.assertEqual(edits.check_resolutions(self.dir / 'plan.json', self.dir), {})
        plan_ = plan()
        text = 'The calculator shows `Error` when dividing by zero, and clears it on the next key.'
        narrative = '## 1. A\n\nFirst.\n\n%s\n\nLast.\n' % text
        near = 'The calculator shows Error when dividing by zero, and clears it on the next key.'
        fixed = edits.repair({'replace_text': [{'heading': 'Made up', 'old': near, 'new': 'n'}]}, narrative)
        self.assertEqual(fixed['replace_text'][0]['old'], text)
        self.assertEqual(fixed['replace_text'][0]['heading'], '## 1. A')

    def test_a_loose_paraphrase_is_not_guessed_at(self):
        narrative = '## 1. A\n\nThe calculator shows Error when dividing by zero.\n'
        patch = {'replace_text': [{'heading': '## 1. A', 'old': 'Division by zero is shown as an error message.', 'new': 'n'}]}
        self.assertEqual(edits.repair(patch, narrative), patch)

    def test_the_retry_shows_the_closest_real_lines(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'replace_text': [{'heading': '## 2. Invariants', 'old': 'I-1 holds always, honestly.', 'new': 'x'}]})
        edits.check_resolutions(self.dir / 'plan.json', self.dir)
        self.assertIn('closest to what you quoted', (self.dir / 'prompts' / 'resolve-G1.retry.md').read_text())

    def test_a_stray_insert_and_a_label_that_is_not_a_section_are_caught(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'insert_sections': [{'content': '#### 10.2.4 Tests\n\nrows'}]})
        self.assertIn('must start with a "## "', edits.check_resolutions(self.dir / 'plan.json', self.dir)['G1'])

    def test_after_the_retry_an_unplaceable_edit_is_left_out_and_recorded_not_the_whole_merge(self):
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'replace_text': [
            {'heading': '## 2. Invariants', 'old': 'I-1 holds always.', 'new': 'resolved'},
            {'heading': 'Made up label', 'old': 'text nowhere in the plan', 'new': 'b'}]})
        target = self.dir
        edits.merge(self.dir / 'plan.json', self.dir / 'slices.tsv', self.dir, self.dir / 'out.json', target)
        result = json.loads((self.dir / 'out.json').read_text())
        applied = edits.apply_patch(NARRATIVE, result['patch'])
        self.assertIn('resolved', applied)
        self.assertNotIn('text nowhere', applied)
        notes = [d for d in result['dispositions'] if 'could not be placed' in d['reason']]
        self.assertTrue(notes)
        self.assertEqual({d['disposition'] for d in notes}, {'Partially accepted'})

    def test_item_edits_by_id_merge_without_any_quoted_text(self):
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [row('AR-1')], 'patch': {'replace_item': [
            {'heading': '## 2. Invariants', 'item': 'I-2', 'new': 'I-2 holds mostly.'}]}}))
        (self.dir / '2.json').write_text(json.dumps({'dispositions': [row('AR-2')], 'patch': {'replace_item': [
            {'heading': '## 3. Tests', 'item': 'T-1', 'new': 'T-1 checks it well.'}]}}))
        result = self.merge()
        applied = edits.apply_patch(NARRATIVE, result['patch'])
        self.assertIn('I-2 holds mostly.', applied)
        self.assertIn('T-1 checks it well.', applied)

    def test_two_writers_changing_the_same_item_need_a_resolution(self):
        for name, finding, text in (('1', 'AR-1', 'I-1 first.'), ('2', 'AR-2', 'I-1 second.')):
            (self.dir / ('%s.json' % name)).write_text(json.dumps({'dispositions': [row(finding)], 'patch': {'replace_item': [
                {'heading': '## 2. Invariants', 'item': 'I-1', 'new': text}]}}))
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'text')

    def test_an_item_that_does_not_exist_goes_to_a_resolver_not_a_failed_merge(self):
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [row('AR-1')], 'patch': {'replace_item': [
            {'heading': '## 2. Invariants', 'item': 'I-9', 'new': 'I-9 new.'}]}}))
        (self.dir / '2.json').write_text(json.dumps({'dispositions': [row('AR-2')], 'patch': {}}))
        with self.assertRaises(edits.NeedsResolution) as caught:
            self.merge()
        self.assertEqual(caught.exception.groups[0]['kind'], 'missing')
        self.assertIn('I-1 holds always.', caught.exception.groups[0]['nearest'])

    def test_a_resolver_answers_with_an_item_edit(self):
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [row('AR-1')], 'patch': {'replace_item': [
            {'heading': '## 2. Invariants', 'item': 'I-9', 'new': 'I-9 new.'}]}}))
        (self.dir / '2.json').write_text(json.dumps({'dispositions': [row('AR-2')], 'patch': {}}))
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        result = self.merge(self.answer({'replace_item': [{'heading': '## 2. Invariants', 'item': 'I-2', 'new': 'I-2 resolved.'}]}))
        self.assertIn('I-2 resolved.', edits.apply_patch(NARRATIVE, result['patch']))

    def test_a_resolver_item_that_does_not_exist_is_caught_with_a_clear_reason(self):
        (self.dir / '1.json').write_text(json.dumps({'dispositions': [row('AR-1')], 'patch': {'replace_item': [
            {'heading': '## 2. Invariants', 'item': 'I-9', 'new': 'x'}]}}))
        (self.dir / '2.json').write_text(json.dumps({'dispositions': [row('AR-2')], 'patch': {}}))
        with self.assertRaises(edits.NeedsResolution):
            self.merge()
        self.answer_file('G1', {'replace_item': [{'heading': '## 2. Invariants', 'item': 'I-8', 'new': 'x'}]})
        self.assertIn('I-8 begins no single line', edits.check_resolutions(self.dir / 'plan.json', self.dir)['G1'])

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


class Resplit(unittest.TestCase):
    def test_a_failed_writer_becomes_one_writer_per_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.tsv'
            path.write_text('1\tAR-1,AR-2\n2\tAR-3,AR-4,AR-5\n3\tAR-6\n')
            fresh = edits.resplit(path, {'2'})
            self.assertEqual(fresh, [('2-1', ['AR-3']), ('2-2', ['AR-4']), ('2-3', ['AR-5'])])
            self.assertEqual(path.read_text(),
                             '1\tAR-1,AR-2\n2-1\tAR-3\n2-2\tAR-4\n2-3\tAR-5\n3\tAR-6\n')

    def test_a_single_finding_writer_is_simply_asked_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.tsv'
            path.write_text('1\tAR-1\n2\tAR-2,AR-3\n')
            self.assertEqual(edits.resplit(path, {'1'}), [('1', ['AR-1'])])
            self.assertEqual(path.read_text(), '1\tAR-1\n2\tAR-2,AR-3\n')

    def test_the_cli_prints_the_rows_to_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.tsv'
            path.write_text('1\tAR-1,AR-2\n2\tAR-3,AR-4\n')
            out = subprocess.run([sys.executable, str(LIB / 'updated_plan_edits.py'), 'resplit', str(path), '1', '2'],
                                 capture_output=True, text=True, check=True).stdout
            self.assertEqual(out.splitlines(), ['1-1\tAR-1', '1-2\tAR-2', '2-1\tAR-3', '2-2\tAR-4'])


class Slicing(unittest.TestCase):
    def test_few_findings_stay_one_call(self):
        self.assertEqual(edits.slices(['A', 'B', 'C']), [])

    def test_by_default_each_finding_gets_its_own_writer_in_order(self):
        ids = ['AR-%d' % n for n in range(1, 10)]
        self.assertEqual(edits.slices(ids), [(str(n + 1), [ids[n]]) for n in range(9)])

    def test_a_bigger_size_splits_evenly(self):
        ids = ['AR-%d' % n for n in range(1, 10)]
        self.assertEqual(edits.slices(ids, 4), [('1', ids[:3]), ('2', ids[3:6]), ('3', ids[6:])])

    def test_writer_count_is_capped(self):
        rows = edits.slices(['AR-%d' % n for n in range(1, 61)])
        self.assertEqual(len(rows), edits.MAX_WRITERS)
        self.assertEqual(sum(len(ids) for _, ids in rows), 60)

    def test_cli_prints_tab_separated_rows_and_the_prompt_names_the_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = Path(tmp) / 'r.json'
            review.write_text(json.dumps({'findings': [{'id': 'AR-%d' % n} for n in range(1, 7)]}))
            env = dict(__import__('os').environ, WORKFLOW_UPDATED_PLAN_EDIT_SLICE='3')
            out = subprocess.run([sys.executable, str(LIB / 'updated_plan_edits.py'), 'slices', str(review)],
                                 capture_output=True, text=True, check=True, env=env).stdout
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
