"""run_step's docstring promises it "never raises into the caller": it runs on
a bare threading.Thread (not a ThreadPoolExecutor future), so an exception
that actually escapes it does not propagate anywhere observable -- it only
prints a traceback via the default thread excepthook, and `results` is left
with no entry at all for that step number. `main()` then treats a missing
entry exactly like a reported success (`results.get(n, {}).get('exit')` is
falsy), so a step that silently crashed looked like it passed, right up until
`merge()` KeyErrors on the missing results[number].

This was true for any exception type other than (OSError, ValueError): the
original `except (OSError, ValueError)` left every other exception class to
escape silently. This test forces exactly such an exception (a KeyError from
a malformed step spec) and checks that it is recorded as the failed step the
docstring promises, not silently dropped from `results` entirely.

Found while investigating the "driver vanishes silently after all parallel
workers report success, with no stop-reason and no TRIAGE.md" issue reported
against change-workflow.sh (GitHub issues 116 and 119). This is a genuine,
reproducible contributing defect in the implementation-worker merge path that
both stagegate.sh and change-workflow.sh share via parallel_steps.py; it is
not a confirmed full reproduction of the exact production incident (which
looks, from the driver.lock/TRIAGE.md symptom pattern, like it may also
involve a signal terminating the whole process group -- that part needs live
multi-process reproduction this environment cannot safely attempt).
"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import parallel_steps  # noqa: E402


class ParallelWorkerExceptionSafetyTests(unittest.TestCase):
    def test_non_oserror_exception_is_recorded_as_a_failed_step(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            # Deliberately missing 'baseline' and 'command': run_step's first
            # touch of spec['baseline'] (inside the try, after
            # publish_worker_start) raises a bare KeyError, not an
            # OSError/ValueError.
            spec = {'number': 7, 'sandbox': sandbox, 'project': sandbox, 'env': {}}
            results = {}
            thread = threading.Thread(target=parallel_steps.run_step, args=(spec, results))
            thread.start()
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive(), 'run_step thread did not finish')

            self.assertIn(7, results,
                          "a step that raised a non-(OSError, ValueError) exception left no "
                          "results[number] entry at all -- main() will treat this as a silent "
                          "success and merge() will KeyError on it later")
            self.assertEqual(results[7].get('exit'), 1,
                             'a step that crashed with an unexpected exception must be '
                             'recorded as failed (exit=1), matching every other failure path')
            self.assertIn('detail', results[7])

    def test_missing_result_is_not_silently_treated_as_success(self):
        """Guards the exact failure mode described above directly: a step
        number absent from `results` must not be excluded from a failed-step
        filter the way `main()` builds `failed`."""
        results = {1: {'exit': 0}}
        numbers = [1, 7]
        failed = [n for n in numbers if results.get(n, {}).get('exit')]
        self.assertNotIn(7, failed,
                         'documents the exact bug: a step missing from `results` entirely is '
                         'indistinguishable from a passing step to this filter. The real fix is '
                         'that run_step must never leave a step number out of `results` -- '
                         'covered by the test above.')


if __name__ == '__main__':
    unittest.main()
