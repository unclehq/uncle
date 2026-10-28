#!/usr/bin/env python3
"""Checks that conflict share a lane and run in order; everything else runs beside them, with no barriers."""
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import checklist_lanes as lanes


def check(cid, resources=(), depends=(), required=True):
    return {'id': cid, 'required': required, 'exclusive_resources': list(resources), 'depends_on': list(depends)}


def plan(*checks):
    return {'checks': list(checks)}


class Lanes(unittest.TestCase):
    def test_checks_sharing_a_resource_form_one_ordered_lane_and_the_rest_are_free(self):
        multi, free = lanes.lanes(plan(check('A', ['port:4173']), check('B'), check('C', ['port:4173']),
                                       check('D'), check('E', ['port:4173'])))
        self.assertEqual(multi, [['A', 'C', 'E']])
        self.assertEqual(free, ['B', 'D'])

    def test_resource_spellings_are_one_resource(self):
        multi, _ = lanes.lanes(plan(check('A', ['port:4173']), check('B', ['port-4173']), check('C', ['Port 4173'])))
        self.assertEqual(multi, [['A', 'B', 'C']])

    def test_a_dependency_keeps_both_checks_in_one_lane_in_order(self):
        multi, free = lanes.lanes(plan(check('A'), check('B', depends=['A']), check('C')))
        self.assertEqual(multi, [['A', 'B']])
        self.assertEqual(free, ['C'])

    def test_lanes_chain_through_both_kinds_of_link(self):
        multi, free = lanes.lanes(plan(check('A', ['db']), check('B', ['db']), check('C', ['file']),
                                       check('D', ['file'], ['B']), check('E')))
        self.assertEqual(multi, [['A', 'B', 'C', 'D']])
        self.assertEqual(free, ['E'])

    def test_a_check_that_declared_nothing_conflicts_with_everything(self):
        multi, free = lanes.lanes({'checks': [check('A'), {'id': 'B', 'required': True}, check('C')]})
        self.assertEqual((multi, free), ([['A', 'B', 'C']], []))

    def test_a_forward_or_self_dependency_makes_it_serial(self):
        for deps in (['C'], ['B']):
            multi, _ = lanes.lanes(plan(check('A'), check('B', depends=deps), check('C')))
            self.assertEqual(multi, [['A', 'B', 'C']], deps)

    def test_optional_checks_and_unknown_dependencies_constrain_nothing(self):
        multi, free = lanes.lanes(plan(check('A', depends=['GHOST']), check('B', ['port'], required=False), check('C', ['port'])))
        self.assertEqual(multi, [])
        self.assertEqual(free, ['A', 'C'])

    def test_every_required_check_appears_exactly_once(self):
        checks = plan(*[check('MC-%d' % n, ['r%d' % (n % 3)] if n % 2 else [], ['MC-%d' % (n - 1)] if n % 5 == 0 else []) for n in range(1, 31)])
        out = [c for batch in lanes.batches(checks, 2, 8) for c in batch]
        self.assertEqual(sorted(out), sorted(c['id'] for c in checks['checks']))
        self.assertEqual(len(out), len(set(out)))


class Batches(unittest.TestCase):
    def test_free_checks_are_pooled_and_lanes_stay_whole(self):
        out = lanes.batches(plan(check('A', ['p']), check('B', ['p']), *[check('F%d' % n) for n in range(5)]), 2, 8)
        self.assertEqual(out[0], ['A', 'B'])
        self.assertEqual(out[1:], [['F0', 'F1'], ['F2', 'F3'], ['F4']])

    def test_the_worker_limit_grows_the_pools_not_the_lanes(self):
        out = lanes.batches(plan(check('A', ['p']), check('B', ['p']), *[check('F%d' % n) for n in range(12)]), 2, 4)
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0], ['A', 'B'])
        self.assertEqual(sorted(c for b in out for c in b), sorted(['A', 'B'] + ['F%d' % n for n in range(12)]))

    def test_more_lanes_than_workers_run_two_lanes_one_after_the_other(self):
        checks = plan(*[c for n in range(6) for c in (check('A%d' % n, ['r%d' % n]), check('B%d' % n, ['r%d' % n]))])
        out = lanes.batches(checks, 2, 3)
        self.assertEqual(len(out), 3)
        for batch in out:                          # a merged lane keeps each lane's own order
            for n in range(6):
                if 'A%d' % n in batch:
                    self.assertLess(batch.index('A%d' % n), batch.index('B%d' % n))

    def test_a_realistic_fifteen_check_list_becomes_a_few_workers_without_barriers(self):
        # The shape of a real run's list (noinit's): three checks that bind the same port, a short dependency chain on a
        # shared directory, and independent reads.  It used to read the live project's checklist, so it failed whenever
        # that project was run again and its check ids changed.
        checks = [check('MC-102', ['port:4173']), check('MC-202', ['port:4173']), check('MC-300', ['port:4173']),
                  check('MC-103', ['dir:.test-out']), check('MC-104', ['dir:.test-out'], depends=['MC-103']),
                  check('MC-105'), check('MC-106'), check('MC-200'), check('MC-201'), check('MC-203'),
                  check('MC-204'), check('MC-205'), check('MC-301'), check('MC-302'), check('MC-304')]
        out = lanes.batches(plan(*checks), 2, 8)
        self.assertEqual(out[0], ['MC-102', 'MC-202', 'MC-300'])      # the three port:4173 checks, in order
        self.assertIn(['MC-103', 'MC-104'], out)                       # the chain stays together, in order
        self.assertLessEqual(len(out), 8)
        self.assertEqual(sum(len(b) for b in out), 15)
        self.assertEqual(sorted(c for b in out for c in b), sorted(c['id'] for c in checks))

    def test_the_command_line_prints_one_batch_per_line(self):
        path = Path(tempfile.mkdtemp()) / 'c.json'
        path.write_text(json.dumps(plan(check('A', ['p']), check('B', ['p']), check('C'), check('D'))))
        out = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/checklist_lanes.py'), str(path), '2', '8'],
                             capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertEqual(out, ['A B', 'C D'])

    def test_an_unreadable_checklist_is_an_error_not_a_guess(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/lib/checklist_lanes.py'), '/nonexistent', '2', '8'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


class Defaults(unittest.TestCase):
    def test_one_check_per_worker_by_default_with_room_in_the_pool(self):
        text = (ROOT / 'scripts' / 'lib' / 'checklist-lanes.sh').read_text()
        self.assertIn('WORKFLOW_EXECUTE_CHECKLIST_COMPACT_BATCH_SIZE:-1', text)
        self.assertIn('WORKFLOW_EXECUTE_CHECKLIST_MAX_WORKERS:-18', text)

    def test_fourteen_free_checks_make_fourteen_workers_at_the_defaults(self):
        checks = plan(*[check('MC-%d' % n) for n in range(100, 114)])
        self.assertEqual(len(lanes.batches(checks, 1, 18)), 14)


if __name__ == '__main__':
    unittest.main()
