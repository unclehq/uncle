#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('plan_patch', ROOT/'scripts/lib/plan_patch.py')
plan_patch = importlib.util.module_from_spec(spec); spec.loader.exec_module(plan_patch)

NARRATIVE = '''# Change Plan — Issue 97

Seeded from an issue.

## 1. Selected technical approach
Restore the module.

## 2. Alternative approaches considered
None worth it.

## 14. Rollback plan
Revert the diff.

## Restrictions
| ID | Rule |
|---|---|
| R-1 | keep tests green |
'''


class PlanPatch(unittest.TestCase):
    def test_empty_patch_round_trips_byte_identical(self):
        self.assertEqual(plan_patch.apply_patch(NARRATIVE, {}), NARRATIVE)
        self.assertEqual(plan_patch.apply_patch(NARRATIVE, {'edit_sections': [], 'insert_sections': []}), NARRATIVE)

    def test_edit_section_replaces_only_that_body(self):
        out = plan_patch.apply_patch(NARRATIVE, {'edit_sections': [
            {'heading': '## 2. Alternative approaches considered', 'content': 'Reconsidered: still none worth it.'}]})
        # A heading is never glued straight onto its new body, even when the
        # model's own content omits the blank line.
        self.assertIn('## 2. Alternative approaches considered\n\nReconsidered: still none worth it.', out)
        self.assertNotIn('None worth it.', out)
        # Untouched sections survive verbatim.
        self.assertIn('Restore the module.', out)
        self.assertIn('| R-1 | keep tests green |', out)

    def test_edit_section_normalizes_a_leading_blank_line_the_model_included(self):
        # Whether the model's content already has its own leading blank line
        # or not, the result is the same -- exactly one.
        for content in ('Body.', '\nBody.', '\n\nBody.'):
            with self.subTest(content=repr(content)):
                out = plan_patch.apply_patch(NARRATIVE, {'edit_sections': [
                    {'heading': '## 14. Rollback plan', 'content': content}]})
                self.assertIn('## 14. Rollback plan\n\nBody.', out)

    def test_edit_unknown_heading_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no existing section'):
            plan_patch.apply_patch(NARRATIVE, {'edit_sections': [{'heading': '## 99. Nope', 'content': 'x'}]})

    def test_duplicate_edit_of_same_heading_is_rejected(self):
        edit = {'heading': '## 1. Selected technical approach', 'content': 'x'}
        with self.assertRaisesRegex(ValueError, 'duplicate entry'):
            plan_patch.apply_patch(NARRATIVE, {'edit_sections': [edit, dict(edit, content='y')]})

    def test_insert_after_existing_heading(self):
        out = plan_patch.apply_patch(NARRATIVE, {'insert_sections': [
            {'content': '## 15. New risk\n\nA newly identified risk.', 'after': '## 14. Rollback plan'}]})
        lines = [l for l in out.splitlines() if l.startswith('## ')]
        self.assertEqual(lines, ['## 1. Selected technical approach', '## 2. Alternative approaches considered',
                                  '## 14. Rollback plan', '## 15. New risk', '## Restrictions'])
        self.assertIn('A newly identified risk.', out)

    def test_insert_before_existing_heading(self):
        out = plan_patch.apply_patch(NARRATIVE, {'insert_sections': [
            {'content': '## 0. Preface\n\nContext first.', 'before': '## 1. Selected technical approach'}]})
        lines = [l for l in out.splitlines() if l.startswith('## ')]
        self.assertEqual(lines[0], '## 0. Preface')

    def test_insert_with_position_start(self):
        out = plan_patch.apply_patch(NARRATIVE, {'insert_sections': [
            {'content': '## 0. Preface\n\nx', 'position': 'start'}]})
        lines = [l for l in out.splitlines() if l.startswith('## ')]
        self.assertEqual(lines[0], '## 0. Preface')

    def test_insert_with_no_anchor_appends_at_end(self):
        out = plan_patch.apply_patch(NARRATIVE, {'insert_sections': [{'content': '## 23. New\n\nx'}]})
        lines = [l for l in out.splitlines() if l.startswith('## ')]
        self.assertEqual(lines[-1], '## 23. New')

    def test_insert_unknown_anchor_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no section with heading'):
            plan_patch.apply_patch(NARRATIVE, {'insert_sections': [{'content': '## X\n\nx', 'after': '## 99. Nope'}]})

    def test_insert_colliding_with_existing_heading_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'already exists'):
            plan_patch.apply_patch(NARRATIVE, {'insert_sections': [
                {'content': '## 1. Selected technical approach\n\nx'}]})

    def test_insert_without_heading_line_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must start with a "## " heading line'):
            plan_patch.apply_patch(NARRATIVE, {'insert_sections': [{'content': 'no heading here'}]})

    def test_second_insert_can_anchor_onto_the_first(self):
        out = plan_patch.apply_patch(NARRATIVE, {'insert_sections': [
            {'content': '## 15. First new\n\na', 'after': '## 14. Rollback plan'},
            {'content': '## 16. Second new\n\nb', 'after': '## 15. First new'}]})
        lines = [l for l in out.splitlines() if l.startswith('## ')]
        self.assertEqual(lines[3:5], ['## 15. First new', '## 16. Second new'])

    def test_patch_must_be_an_object(self):
        with self.assertRaisesRegex(ValueError, 'patch must be an object'):
            plan_patch.apply_patch(NARRATIVE, ['not', 'a', 'dict'])

    def test_narrative_with_no_sections_keeps_preamble_only(self):
        preamble, sections = plan_patch.split_sections('# Just a title\n\nNo sections here.\n')
        self.assertEqual(sections, [])
        self.assertEqual(preamble, '# Just a title\n\nNo sections here.')

    def test_level_three_headings_stay_inside_their_section(self):
        text = '## 1. Title\n\nIntro.\n\n### Sub-heading\n\nDetail.\n'
        preamble, sections = plan_patch.split_sections(text)
        self.assertEqual(len(sections), 1)
        self.assertIn('### Sub-heading', sections[0]['body'])


class ReplaceText(unittest.TestCase):
    """A review usually changes a sentence or a row; the patch should cost that, not the whole section."""

    def test_a_snippet_is_replaced_and_everything_else_is_untouched(self):
        out = plan_patch.apply_patch(NARRATIVE, {'replace_text': [
            {'heading': '## 14. Rollback plan', 'old': 'Revert the diff.', 'new': 'Revert the diff and re-run the suite.'}]})
        self.assertIn('Revert the diff and re-run the suite.', out)
        self.assertIn('Restore the module.', out)
        self.assertIn('| R-1 | keep tests green |', out)
        self.assertEqual(out.count('## '), NARRATIVE.count('## '))

    def test_a_table_row_can_be_changed_in_place(self):
        out = plan_patch.apply_patch(NARRATIVE, {'replace_text': [
            {'heading': '## Restrictions', 'old': '| R-1 | keep tests green |', 'new': '| R-1 | keep tests green |\n| R-2 | no new deps |'}]})
        self.assertIn('| R-2 | no new deps |', out)

    def test_text_that_is_not_there_is_refused_loudly(self):
        with self.assertRaisesRegex(ValueError, 'does not occur'):
            plan_patch.apply_patch(NARRATIVE, {'replace_text': [
                {'heading': '## 14. Rollback plan', 'old': 'Revert the commit.', 'new': 'x'}]})

    def test_text_that_occurs_twice_needs_more_context_or_all(self):
        narrative = NARRATIVE + '\n## 15. Notes\nrepeat repeat\n'
        with self.assertRaisesRegex(ValueError, 'occurs 2 times'):
            plan_patch.apply_patch(narrative, {'replace_text': [{'heading': '## 15. Notes', 'old': 'repeat', 'new': 'once'}]})
        out = plan_patch.apply_patch(narrative, {'replace_text': [{'heading': '## 15. Notes', 'old': 'repeat', 'new': 'once', 'all': True}]})
        self.assertIn('once once', out)

    def test_an_unknown_section_or_a_malformed_entry_is_refused(self):
        for entry in ({'heading': '## 99. Nope', 'old': 'a', 'new': 'b'}, {'heading': '## 1. Selected technical approach', 'old': '', 'new': 'b'},
                      {'heading': '## 1. Selected technical approach', 'old': 'Restore'}, 'not an object'):
            with self.assertRaises(ValueError):
                plan_patch.apply_patch(NARRATIVE, {'replace_text': [entry]})

    def test_it_composes_with_edits_and_inserts_in_one_patch(self):
        out = plan_patch.apply_patch(NARRATIVE, {
            'edit_sections': [{'heading': '## 1. Selected technical approach', 'content': 'Rewrite the module.'}],
            'replace_text': [{'heading': '## 1. Selected technical approach', 'old': 'Rewrite', 'new': 'Rebuild'},
                             {'heading': '## 14. Rollback plan', 'old': 'Revert', 'new': 'Undo'}],
            'insert_sections': [{'content': '## 15. Added\nnew', 'after': '## 14. Rollback plan'}]})
        self.assertIn('Rebuild the module.', out)
        self.assertIn('Undo the diff.', out)
        self.assertIn('## 15. Added', out)

    def test_the_replacement_is_far_smaller_than_the_section_it_replaces(self):
        big = '## 10. Tests\n' + ''.join('row %d | assertion | oracle\n' % n for n in range(300))
        patch = {'replace_text': [{'heading': '## 10. Tests', 'old': 'row 7 | assertion | oracle', 'new': 'row 7 | stronger | oracle'}]}
        edit = {'edit_sections': [{'heading': '## 10. Tests', 'content': big}]}
        import json
        self.assertLess(len(json.dumps(patch)) * 20, len(json.dumps(edit)))
        self.assertIn('row 7 | stronger | oracle', plan_patch.apply_patch('# P\n\n' + big, patch))


if __name__ == '__main__':
    unittest.main()
