"""Core candidate_race.py behavior: AC-1..AC-5, AC-8 (regression baseline)."""
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
spec = importlib.util.spec_from_file_location('candidate_race', ROOT / 'scripts/lib/candidate_race.py')
candidate_race = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate_race)

import subprocess
from process_tree import start_check


def sleepy_launch(directories, delays, writes):
    """Build a `launch(n)` that starts a real, killable subprocess per
    candidate: it sleeps `delays[n]` seconds, then writes `writes[n]`
    (a string, or None to write nothing) to `<directory>/output.txt`."""
    def launch(n):
        directory = directories[n]
        directory.mkdir(parents=True, exist_ok=True)
        write = writes[n]
        script = (
            'import time, sys\n'
            'time.sleep(%r)\n' % delays[n] +
            (('with open(%r, "w") as f: f.write(%r)\n' % (str(directory / 'output.txt'), write))
             if write is not None else '')
        )
        process = start_check([sys.executable, '-c', script])
        return process, directory
    return launch


def validate_output(directory):
    path = Path(directory) / 'output.txt'
    if not path.is_file():
        return False, None, 'no output.txt written'
    text = path.read_text(encoding='utf-8')
    if text != 'valid':
        return False, None, 'malformed: %r' % text
    return True, str(path), 'validated'


class CandidateRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def dirs(self, count):
        return [self.root / ('c%d' % n) for n in range(count)]

    def test_first_valid_candidate_wins_even_when_an_earlier_one_is_malformed(self):
        # AC-2: a chat-response/malformed candidate that finishes first must
        # not block a later, valid candidate from winning.
        directories = self.dirs(2)
        launch = sleepy_launch(directories, delays=[0.05, 0.3], writes=['garbage', 'valid'])
        winner, directory, result = candidate_race.run(
            'test-stage', launch, validate_output, count=2, timeout=5)
        self.assertEqual(winner, 1)
        self.assertEqual(Path(result).read_text(), 'valid')

    def test_all_four_fail_raises_with_per_candidate_diagnostics(self):
        # AC-5: no candidate passes -> stage fails with useful diagnostics.
        directories = self.dirs(4)
        launch = sleepy_launch(directories, delays=[0.05] * 4, writes=[None, 'x', 'y', None])
        with self.assertRaises(candidate_race.AllCandidatesFailed) as ctx:
            candidate_race.run('test-stage', launch, validate_output, count=4, timeout=5)
        self.assertEqual(len(ctx.exception.candidates), 4)
        for candidate in ctx.exception.candidates:
            self.assertIn(candidate['status'], ('rejected-invalid',))
            self.assertTrue(candidate['detail'])

    def test_late_candidate_cannot_overwrite_after_selection(self):
        # AC-3/BH-3, the plan's own required regression test: a deliberately
        # slow candidate must not be able to affect anything after a faster
        # candidate has already won -- this must fail before a promotion
        # lock exists and pass after. Our design has no shared canonical
        # path for candidates to race over at all (promotion is the caller
        # copying the *returned* winner directory, never a write candidates
        # perform themselves), so prove the guarantee operationally: the
        # slow candidate is killed, not merely out-raced, and its write
        # never happens.
        directories = self.dirs(2)
        launch = sleepy_launch(directories, delays=[0.05, 2.0], writes=['valid', 'valid'])
        winner, directory, result = candidate_race.run(
            'test-stage', launch, validate_output, count=2, timeout=5)
        self.assertEqual(winner, 0)
        # Give the killed "slow" candidate time to have finished naturally
        # if it had NOT been killed (it slept only 2s and we wait 3s here).
        time.sleep(3)
        self.assertFalse((directories[1] / 'output.txt').exists(),
                          'a losing candidate wrote its output after the race was decided')

    def test_all_losing_candidates_are_killed_no_orphans(self):
        # AC-4: every losing candidate (and its process tree) is stopped.
        directories = self.dirs(4)
        launch = sleepy_launch(directories, delays=[0.05, 10, 10, 10], writes=['valid'] * 4)
        winner, directory, result = candidate_race.run(
            'test-stage', launch, validate_output, count=4, timeout=30)
        self.assertEqual(winner, 0)
        # None of the intentionally-10s-sleeping losers should still be
        # running: they were killed within the call above, which already
        # joined every worker thread before returning.
        time.sleep(0.3)
        for n in (1, 2, 3):
            self.assertFalse((directories[n] / 'output.txt').exists(),
                              'candidate %d was not stopped before it could write' % n)

    def test_timeout_stops_a_hanging_candidate_and_lets_others_race(self):
        directories = self.dirs(2)
        launch = sleepy_launch(directories, delays=[100, 0.1], writes=['valid', 'valid'])
        winner, directory, result = candidate_race.run(
            'test-stage', launch, validate_output, count=2, timeout=2)
        self.assertEqual(winner, 1)

    def test_evidence_file_records_every_candidate_and_the_selection(self):
        # Candidate 1 is well behind candidate 0, so candidate 0's win and
        # the resulting cancellation are guaranteed to land before candidate
        # 1 finishes -- it is stopped, not validated-then-rejected. Losing
        # either way is the guarantee; which losing status depends on timing.
        directories = self.dirs(2)
        launch = sleepy_launch(directories, delays=[0.05, 1.5], writes=['valid', 'garbage'])
        evidence = self.root / 'evidence.json'
        candidate_race.run('test-stage', launch, validate_output, count=2, timeout=5,
                            evidence_path=evidence)
        payload = json.loads(evidence.read_text())
        self.assertEqual(payload['stage'], 'test-stage')
        self.assertEqual(len(payload['candidates']), 2)
        self.assertEqual(payload['selected'], 0)
        statuses = {c['id']: c['status'] for c in payload['candidates']}
        self.assertEqual(statuses[0], 'validated-winner')
        self.assertIn(statuses[1], ('rejected-invalid', 'stopped-nonselected'))

    def test_count_one_behaves_like_a_single_candidate(self):
        # D-3: WORKFLOW_SELF_HOSTED_CANDIDATES=1 must restore single-candidate
        # behavior through the same code path -- a race of one.
        directories = self.dirs(1)
        launch = sleepy_launch(directories, delays=[0.05], writes=['valid'])
        winner, directory, result = candidate_race.run(
            'test-stage', launch, validate_output, count=1, timeout=5)
        self.assertEqual(winner, 0)

    def test_launch_failure_is_a_crashed_candidate_not_a_hang(self):
        def launch(n):
            raise OSError('could not start candidate %d' % n)
        with self.assertRaises(candidate_race.AllCandidatesFailed) as ctx:
            candidate_race.run('test-stage', launch, validate_output, count=2, timeout=5)
        for candidate in ctx.exception.candidates:
            self.assertEqual(candidate['status'], 'crashed')

    def test_only_one_candidate_is_ever_labeled_winner_even_if_both_validate_true_at_once(self):
        # Both candidates' own worker() threads can reach validate() before
        # either has observed the other's result -- neither is cancelled yet,
        # so both genuinely pass. Only the one this module's own selection
        # loop dequeues first may be promoted; a second one that also
        # validated true must be relabeled in the evidence, or the TUI
        # glyphs built from it would show two winners for one race. Force
        # the simultaneity deterministically with a barrier instead of
        # relying on real timing.
        barrier = threading.Barrier(2)
        directories = self.dirs(2)
        launch = sleepy_launch(directories, delays=[0.05, 0.05], writes=['valid', 'valid'])

        def validate(directory):
            barrier.wait(timeout=5)
            return True, str(directory), 'validated'

        evidence = self.root / 'evidence.json'
        winner, _, _ = candidate_race.run('test-stage', launch, validate, count=2, timeout=5,
                                           evidence_path=evidence)
        payload = json.loads(evidence.read_text())
        winners = [c for c in payload['candidates'] if c['status'] == 'validated-winner']
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]['id'], winner)
        self.assertEqual(payload['selected'], winner)


if __name__ == '__main__':
    unittest.main()
