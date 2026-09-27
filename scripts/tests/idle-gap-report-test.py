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


def span(name, seconds, kind='runner_event_gap', started_at=0.0):
    return dict(kind=kind, name=name, elapsed_seconds=seconds, started_at=started_at)


def beats(name, length, count, start=1000.0):
    """Back-to-back gaps: each opens exactly where the last closed."""
    return [span(name, length, started_at=start + i * length) for i in range(count)]


def scattered(name, length, count, start=1000.0, work=45.0):
    """Same length, but with real work between each -- a retry, not a beat."""
    return [span(name, length, started_at=start + i * (length + work)) for i in range(count)]


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
        self.assertEqual(stuck[4], 'repeated 30s x3')   # scattered: worth chasing
        slow = row_for(_idle_gap_section(spans), 'slow')
        self.assertEqual(slow[4], '-')                  # no repeat: nothing to chase

    def test_subsecond_rhythm_is_not_mistaken_for_a_timeout(self):
        # The ordinary cadence of a stream is sub-second and swamps any count.
        # Reporting "0 repeated 15 times" is noise wearing the shape of a
        # finding, so gaps under a second cannot win the repeat column.
        spans = [span('chatty', 0.1) for _ in range(15)] + [span('chatty', 9.0), span('chatty', 9.0)]
        row = row_for(_idle_gap_section(spans), 'chatty')
        # Two 9s gaps is too few to call a pattern either way.
        self.assertEqual(row[4], '-')

    def test_all_subsecond_reports_no_repeat_rather_than_zero(self):
        row = row_for(_idle_gap_section([span('quiet', 0.2), span('quiet', 0.2)]), 'quiet')
        self.assertEqual(row[4], '-')

    def test_tail_gap_counts_and_worst_stage_leads(self):
        spans = [span('small', 2.0), span('big', 40.0, kind='runner_tail_gap'), span('big', 5.0)]
        lines = _idle_gap_section(spans)
        body = [line for line in lines if line.startswith('| ') and not line.startswith('| Stage')]
        self.assertTrue(body[0].startswith('| big |'), body)
        self.assertEqual(row_for(lines, 'big')[1], '2')

    def test_pipe_in_a_stage_name_cannot_break_the_table(self):
        row = row_for(_idle_gap_section([span('a|b', 3.0)]), 'a&#124;b')
        self.assertEqual(row[1], '1')




class GapPattern(unittest.TestCase):
    """Telling a heartbeat from a retry is the whole point of the column.

    Nineteen gaps of exactly 30.0s were read as a retry loop worth ~9.5
    minutes. They were back to back -- a heartbeat over a stage that was busy
    running commands, with nothing to reclaim. Lengths alone cannot separate
    the two; only their arrangement can.
    """

    def test_back_to_back_is_a_heartbeat(self):
        row = row_for(_idle_gap_section(beats('beat', 30.0, 19)), 'beat')
        self.assertEqual(row[4], 'heartbeat 30s x19')

    def test_same_length_with_work_between_is_a_retry(self):
        row = row_for(_idle_gap_section(scattered('retry', 30.0, 8)), 'retry')
        self.assertEqual(row[4], 'repeated 30s x8')

    def test_a_few_skipped_beats_still_read_as_a_heartbeat(self):
        # A beat is skipped whenever real work lands between two of them. The
        # real run broke twice in eighteen pairs and is still a heartbeat.
        rows = beats('beat', 30.0, 19)
        rows[13]['started_at'] += 30.0
        rows[18]['started_at'] += 66.7
        self.assertEqual(row_for(_idle_gap_section(rows), 'beat')[4], 'heartbeat 30s x19')

    def test_threshold_counts_pairs_not_gaps(self):
        # Nineteen beats have eighteen adjacencies. Requiring one per gap asks
        # for one more than can exist and reports every heartbeat as a retry.
        self.assertTrue(row_for(_idle_gap_section(beats('b', 30.0, 19)), 'b')[4].startswith('heartbeat'))

    def test_too_few_to_judge_claims_nothing(self):
        self.assertEqual(row_for(_idle_gap_section(beats('few', 30.0, 2)), 'few')[4], '-')


class BusiestProcess(unittest.TestCase):
    """A gap proves nothing was emitted, not that nothing was happening."""

    def test_names_what_ran_during_the_gaps(self):
        rows = beats('stage', 10.0, 3)          # 1000-1030
        rows.append(span('bash', 25.0, kind='sampled_process', started_at=1000.0))
        rows.append(span('jq', 4.0, kind='sampled_process', started_at=1000.0))
        self.assertIn('bash', row_for(_idle_gap_section(rows), 'stage')[5])

    def test_a_process_outside_the_window_is_not_credited(self):
        rows = beats('stage', 10.0, 3)          # 1000-1030
        rows.append(span('elsewhere', 900.0, kind='sampled_process', started_at=5000.0))
        self.assertEqual(row_for(_idle_gap_section(rows), 'stage')[5], '-')

    def test_only_the_overlap_counts(self):
        rows = beats('stage', 10.0, 3)          # 1000-1030
        rows.append(span('straddler', 600.0, kind='sampled_process', started_at=900.0))
        self.assertIn('(30s)', row_for(_idle_gap_section(rows), 'stage')[5])


if __name__ == '__main__':
    unittest.main()
