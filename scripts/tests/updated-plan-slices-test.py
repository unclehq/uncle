#!/usr/bin/env python3
"""The updated-plan panel splits its dispositions lens by finding, and only past a threshold."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import updated_plan_slices as slices


def review(count, prefix='AR-'):
    directory = tempfile.mkdtemp()
    path = Path(directory) / 'review.json'
    path.write_text(json.dumps({'findings': [{'id': '%s%03d' % (prefix, n)} for n in range(1, count + 1)]}))
    return str(path)


class Slices(unittest.TestCase):
    def names(self, rows):
        return [name for name, _ in rows]

    def test_a_short_review_keeps_the_single_dispositions_worker(self):
        for count in (0, 1, 8):
            rows = slices.workers(review(count))
            self.assertEqual(self.names(rows), ['dispositions', 'ownership', 'verification', 'scope'])
            self.assertEqual([ids for _, ids in rows], [[]] * 4)

    def test_a_long_review_is_split_into_even_consecutive_slices(self):
        rows = slices.workers(review(9))
        self.assertEqual(self.names(rows), ['dispositions-1', 'dispositions-2', 'ownership', 'verification', 'scope'])
        self.assertEqual([len(ids) for _, ids in rows[:2]], [5, 4])
        merged = rows[0][1] + rows[1][1]
        self.assertEqual(merged, ['AR-%03d' % n for n in range(1, 10)])

    def test_every_finding_is_owned_by_exactly_one_slice(self):
        for count in (9, 16, 17, 24, 33):
            owned = [i for name, ids in slices.workers(review(count)) if name.startswith('dispositions') for i in ids]
            self.assertEqual(owned, ['AR-%03d' % n for n in range(1, count + 1)])

    def test_unreadable_or_odd_reviews_fall_back_to_the_single_worker(self):
        for content in (None, 'not json', '[]', '{"findings": "x"}', '{"findings": [{"id": ""}, 5]}'):
            path = Path(tempfile.mkdtemp()) / 'r.json'
            if content is not None:
                path.write_text(content)
            self.assertEqual(slices.workers(str(path))[0], ('dispositions', []))

    def test_duplicate_ids_are_assigned_once(self):
        path = Path(tempfile.mkdtemp()) / 'r.json'
        path.write_text(json.dumps({'findings': [{'id': 'AR-001'}] * 12}))
        self.assertEqual(slices.workers(str(path))[0], ('dispositions', []))

    def test_size_is_configurable_and_output_is_tab_separated(self):
        out = subprocess.run([sys.executable, str(LIB / 'updated_plan_slices.py'), review(6)],
                             capture_output=True, text=True, check=True,
                             env={'WORKFLOW_UPDATED_PLAN_SLICE': '3', 'PATH': ''}).stdout.splitlines()
        self.assertEqual(out[0], 'dispositions-1\tAR-001,AR-002,AR-003')
        self.assertEqual(out[1], 'dispositions-2\tAR-004,AR-005,AR-006')
        self.assertEqual(out[-1], 'scope\t')


if __name__ == '__main__':
    unittest.main()
