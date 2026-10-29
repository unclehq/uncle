#!/usr/bin/env python3
"""Compact checklist mode keeps the reviewer's groups; it never merges them into one."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
from compact_groups import compact_groups

CHECKLIST = {'checks': [{'id': 'MC-1'}, {'id': 'MC-2'}, {'id': 'MC-3', 'required': False},
                        {'id': 'MC-4', 'required': True}, {'id': 'MC-5'}]}


class CompactGroups(unittest.TestCase):
    def test_declared_groups_stay_separate_barriers(self):
        self.assertEqual(compact_groups('MC-1 MC-2\nMC-4\nMC-5\n', CHECKLIST), ['MC-1 MC-2', 'MC-4', 'MC-5'])

    def test_optional_checks_are_dropped_and_empty_groups_vanish(self):
        self.assertEqual(compact_groups('MC-1 MC-3\nMC-3\nMC-5\n', CHECKLIST), ['MC-1', 'MC-5'])

    def test_unknown_ids_and_blank_lines_are_ignored(self):
        self.assertEqual(compact_groups('\nMC-9 MC-1\n\n', CHECKLIST), ['MC-1'])

    def test_both_drivers_no_longer_collapse_the_checklist_into_one_group(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT / source).read_text()
            start = text.index('run_parallel_checklist_workers()')
            block = text[start:text.index('\n}\n', start)]
            self.assertIn('compact_groups.py', block)
            self.assertNotIn("print(' '.join(c['id']", block)
            self.assertNotIn('compact-all', block)

    def test_batches_are_small_and_capped_in_both_drivers(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT / source).read_text()
            start = text.index('run_parallel_checklist_workers()')
            block = text[start:text.index('\n}\n', start)]
            self.assertIn('WORKFLOW_EXECUTE_CHECKLIST_COMPACT_BATCH_SIZE:-2', block)
            self.assertIn('WORKFLOW_EXECUTE_CHECKLIST_MAX_WORKERS:-8', block)
            self.assertEqual(block.count('batches="$compact_max_workers"'), 2)

    def test_the_checklist_prompts_say_declaring_nothing_lets_a_check_overlap(self):
        for name in ('manual-checklist.md', 'manual-checklist-investigate.md', 'change/manual-checklist-base.md'):
            text = (ROOT / 'prompts' / name).read_text()
            self.assertIn('Declaring nothing is a statement', text, name)
            self.assertIn('A check with no declaration at all is scheduled alone', text, name)
            self.assertNotIn('empty `exclusive_resources` array is scheduled alone', text, name)
            self.assertIn('Several checks\n  can use one running application', text, name)

    def test_spellings_of_one_resource_are_one_resource(self):
        import checklist_groups as groups
        for spelling in ('port:4173', 'port-4173', '`Port 4173`', 'PORT_4173'):
            self.assertEqual(groups.normalize_resource(spelling), 'port:4173')
        self.assertNotEqual(groups.normalize_resource('port:4173'), groups.normalize_resource('port:5173'))

    def test_checks_declaring_the_same_port_two_ways_are_not_scheduled_together(self):
        import checklist_groups as groups
        text = ('### MC-001 first\n**Exclusive resources:** port:4173\n**Depends on:** none\n\n'
                '### MC-002 second\n**Exclusive resources:** port-4173\n**Depends on:** none\n')
        checks, by_id, _ = groups.parse(text)
        self.assertEqual([[c for c in run] for run in groups.runs(checks)], [['MC-001'], ['MC-002']])

    def test_every_check_is_executed_and_over_serial_checklists_can_use_parent_fallback(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT / source).read_text()
            block = text[text.index('run_parallel_checklist_workers()'):text.index('\n}\n', text.index('run_parallel_checklist_workers()'))]
            self.assertNotIn('[[ "$n" -gt 1 ]] || continue', block)
            self.assertIn('WORKFLOW_EXECUTE_CHECKLIST_MAX_GROUPS:-4', block)
            self.assertIn('Checklist runs as one agent', block)
            self.assertIn('one shared-resource worker', block)
            self.assertIn('checklist_coverage.py', text)

    def test_coverage_lists_required_checks_no_worker_ran(self):
        import checklist_coverage as coverage
        checklist = {'checks': [{'id': 'MC-1'}, {'id': 'MC-2'}, {'id': 'MC-3', 'required': False}, {'id': 'MC-4', 'required': True}]}
        workers = {'results': [{'id': 'MC-1', 'status': 'PASS'}]}
        self.assertEqual(coverage.uncovered(checklist, workers), ['MC-2', 'MC-4'])
        self.assertEqual(coverage.uncovered(checklist, None), ['MC-1', 'MC-2', 'MC-4'])
        self.assertEqual(coverage.uncovered(checklist, {'results': [{'id': i} for i in ('MC-1', 'MC-2', 'MC-4')]}), [])

    def test_the_fast_path_runs_only_when_every_required_check_was_covered(self):
        for source in ('scripts/stagegate.sh', 'scripts/change-workflow.sh'):
            text = (ROOT / source).read_text()
            self.assertIn('Checks the workers did not cover', text)
            self.assertLess(text.index('checklist_coverage.py'), text.index('Execute-checklist fast path'))

    def test_the_panel_workers_are_told_what_a_resource_is_and_to_write_few_checks(self):
        text = (ROOT / 'prompts' / 'change' / 'manual-checklist-review-worker.md').read_text()
        self.assertIn('at most 8', text)
        self.assertIn('is not a resource (do not name its port)', text)
        self.assertIn('Spell a token one way', text)
        self.assertIn('cannot establish', text)

    def test_a_new_application_checklist_has_no_regressions_lens_by_default(self):
        text = (ROOT / 'scripts' / 'stagegate.sh').read_text()
        block = text[text.index('run_manual_checklist_panel()'):text.index('run_final_audit_panel()')]
        self.assertIn('lenses="coverage invariants resources"', block)
        self.assertIn('WORKFLOW_MANUAL_CHECKLIST_REGRESSIONS:-0', block)
        self.assertNotIn('coverage invariants resources regressions ||', block)


if __name__ == '__main__':
    unittest.main()
