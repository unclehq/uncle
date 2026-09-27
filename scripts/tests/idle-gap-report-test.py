#!/usr/bin/env python3
"""The idle-gap section of the build-timing report.

runner_timing.py has always recorded the largest gaps between received stream
events, and the per-kind tables have always totalled them. A total alone cannot
separate "the model was working" from "something was stuck": both are elapsed
seconds. Two things tell them apart and neither survives being summed -- the
longest single gap, and whether one length keeps recurring. Natural latency
scatters; a timeout lands on the same value every time.

On a real run this section read `change-plan | 36 | 692.5 | 52.0 | 30 | 16`:
sixteen gaps at exactly 30 seconds, which is a retry cadence rather than
anything the model was doing.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from build_timing import _idle_gap_section


def span(name, seconds, kind='runner_event_gap'):
    return dict(kind=kind, name=name, elapsed_seconds=seconds)


def row_for(lines, stage):
    for line in lines:
        if line.startswith(f'| {stage} |'):
            return [cell.strip() for cell in line.strip('|').split('|')]
    raise AssertionError(f'no row for {stage} in {lines}')


class IdleGapSection(unittest.TestCase):
    def test_nothing_recorded_emits_nothing(self):
        self.assertEqual(_idle_gap_section([span('x', 1, kind='agent')]), [])

    def test_repeated_timeout_is_surfaced(self):
        # A stage stuck on a 30s timer, beside one that simply ran long.
        spans = [span('stuck', 30.0), span('stuck', 30.1), span('stuck', 29.9),
                 span('stuck', 7.3), span('slow', 52.0), span('slow', 11.0)]
        stuck = row_for(_idle_gap_section(spans), 'stuck')
        self.assertEqual(stuck[1], '4')            # gaps
        self.assertEqual(stuck[2], '97.3')         # total seconds
        self.assertEqual(stuck[3], '30.1')         # longest
        self.assertEqual(stuck[4], '30')           # repeated length, jitter bucketed
        self.assertEqual(stuck[5], '3')            # times seen
        slow = row_for(_idle_gap_section(spans), 'slow')
        self.assertEqual(slow[4], '-')             # no repeat: nothing to chase
        self.assertEqual(slow[5], '0')

    def test_subsecond_rhythm_is_not_mistaken_for_a_timeout(self):
        # The ordinary cadence of a stream is sub-second and swamps any count.
        # Reporting "0 repeated 15 times" is noise wearing the shape of a
        # finding, so gaps under a second cannot win the repeat column.
        spans = [span('chatty', 0.1) for _ in range(15)] + [span('chatty', 9.0), span('chatty', 9.0)]
        row = row_for(_idle_gap_section(spans), 'chatty')
        self.assertEqual(row[4], '9')
        self.assertEqual(row[5], '2')

    def test_all_subsecond_reports_no_repeat_rather_than_zero(self):
        row = row_for(_idle_gap_section([span('quiet', 0.2), span('quiet', 0.2)]), 'quiet')
        self.assertEqual(row[4], '-')
        self.assertEqual(row[5], '0')

    def test_tail_gap_counts_and_worst_stage_leads(self):
        spans = [span('small', 2.0), span('big', 40.0, kind='runner_tail_gap'), span('big', 5.0)]
        lines = _idle_gap_section(spans)
        body = [line for line in lines if line.startswith('| ') and not line.startswith('| Stage')]
        self.assertTrue(body[0].startswith('| big |'), body)
        self.assertEqual(row_for(lines, 'big')[1], '2')

    def test_pipe_in_a_stage_name_cannot_break_the_table(self):
        row = row_for(_idle_gap_section([span('a|b', 3.0)]), 'a&#124;b')
        self.assertEqual(row[1], '1')


if __name__ == '__main__':
    unittest.main()
