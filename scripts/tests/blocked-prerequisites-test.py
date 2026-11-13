#!/usr/bin/env python3
"""A verification command that could not run because a BLOCKED-SETUP prerequisite is outstanding is not a failure to repair.

The run that found this: another project's Vite server held port 5173, the preflight reported it BLOCKED-SETUP ("the user stops that
process"), the unattended run went on, and the e2e command then failed with 'http://127.0.0.1:5173 is already used'. It was counted as
a regression and sent to repair, which cannot free a port; the mutation checks failed behind it for the same reason."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import blocked_prerequisites as bp  # noqa: E402

BLOCKED = {'id': 'G-7', 'required': True, 'status': 'BLOCKED-SETUP',
           'evidence': 'Bind of 127.0.0.1:5173 failed: Address already in use (node PID 66094). Action: the user stops that process.'}
PASSING = {'id': 'G-1', 'required': True, 'status': 'PASS', 'evidence': 'cargo 1.99'}
E2E = 'npm --prefix frontend run test:e2e'
LOG = ('\n$ cargo test --manifest-path backend/Cargo.toml\ntest t3 ... FAILED\nleft: Some("http://127.0.0.1:5173")\n'
       '\n$ %s\n> npx playwright test\nError: http://127.0.0.1:5173 is already used, make sure that nothing is running on the port\n'
       '\n$ node tests/mutations/run.mjs\ncontrols 0/2 passed\n') % E2E


def reclassify(rows, log, classified):
    with tempfile.TemporaryDirectory() as directory:
        report, logfile, side = (Path(directory) / n for n in ('r.json', 'g.log', 's.tsv'))
        report.write_text(json.dumps({'rows': rows}))
        logfile.write_text(log)
        out = io.StringIO()
        bp.reclassify(str(report), str(logfile), str(side), io.StringIO(classified), out)
        return out.getvalue(), side.read_text() if side.exists() else ''


class Attribution(unittest.TestCase):
    def test_the_port_blocked_command_is_relabelled_and_a_real_failure_is_not(self):
        out, side = reclassify([BLOCKED, PASSING], LOG, 'REGRESSION\tcargo test --manifest-path backend/Cargo.toml\nREGRESSION\t%s\nPASS\tx\n' % E2E)
        self.assertEqual(out.splitlines(), ['REGRESSION\tcargo test --manifest-path backend/Cargo.toml', 'BLOCKED-SETUP\t' + E2E, 'PASS\tx'])
        self.assertEqual(side.strip(), '%s\tG-7\tthe user stops that process.' % E2E)

    def test_the_port_must_be_the_one_the_row_names(self):
        other = LOG.replace('5173', '3000')
        out, _ = reclassify([BLOCKED], other, 'REGRESSION\t%s\n' % E2E)
        self.assertEqual(out, 'REGRESSION\t%s\n' % E2E)

    def test_a_failure_that_merely_mentions_the_port_is_not_enough(self):
        log = '\n$ %s\nexpected origin http://127.0.0.1:5173 but got none\nAssertionError\n' % E2E
        out, _ = reclassify([BLOCKED], log, 'REGRESSION\t%s\n' % E2E)
        self.assertTrue(out.startswith('REGRESSION'))

    def test_the_in_use_line_may_sit_beside_the_line_naming_the_port(self):
        log = '\n$ %s\nOSError: [Errno 48] Address already in use\nwhile binding 127.0.0.1:5173\n' % E2E
        out, _ = reclassify([BLOCKED], log, 'REGRESSION\t%s\n' % E2E)
        self.assertTrue(out.startswith('BLOCKED-SETUP'))

    def test_only_blocked_setup_rows_count(self):
        out, _ = reclassify([dict(BLOCKED, status='BLOCKED-HUMAN'), PASSING], LOG, 'REGRESSION\t%s\n' % E2E)
        self.assertTrue(out.startswith('REGRESSION'))
        out, _ = reclassify([], LOG, 'REGRESSION\t%s\n' % E2E)
        self.assertTrue(out.startswith('REGRESSION'))

    def test_a_mutation_row_is_explained_too_and_a_passing_row_is_never_touched(self):
        log = LOG + '\n$ node tests/mutations/run2.mjs\nError: listen EADDRINUSE: address already in use 127.0.0.1:5173\n'
        out, _ = reclassify([BLOCKED], log, 'MUTATION\tnode tests/mutations/run2.mjs\nPASS\t%s\nFIXED\tz\n' % E2E)
        self.assertEqual(out.splitlines(), ['BLOCKED-SETUP\tnode tests/mutations/run2.mjs', 'PASS\t' + E2E, 'FIXED\tz'])

    def test_an_unreadable_report_or_log_passes_every_row_through(self):
        out = io.StringIO()
        bp.reclassify('/no/such/report.json', '/no/such/log', None, io.StringIO('REGRESSION\ta\nPASS\tb\n'), out)
        self.assertEqual(out.getvalue(), 'REGRESSION\ta\nPASS\tb\n')

    def test_ansi_colour_in_the_log_does_not_hide_the_message(self):
        log = '\n$ %s\n\x1b[31mError: http://127.0.0.1:5173 is already used\x1b[0m\n' % E2E
        out, _ = reclassify([BLOCKED], log, 'REGRESSION\t%s\n' % E2E)
        self.assertTrue(out.startswith('BLOCKED-SETUP'))


class Driver(unittest.TestCase):
    """The real green-check functions, in bash, over a fake report and log."""

    def run_green(self, rows, tail):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'documents').mkdir()
            (base / 'logs').mkdir()
            (base / 'documents' / 'PREFLIGHT_REPORT.json').write_text(json.dumps({'rows': rows}))
            (base / 'logs' / 'green-check.log').write_text(LOG)
            (base / 'current.tsv').write_text('0\tnpm install\n1\tcargo test --manifest-path backend/Cargo.toml\n1\t%s\n' % E2E)
            script = ('ROOT="%s"; STATE_DIR="%s"; LOG_DIR="%s/logs"; . "$ROOT/scripts/lib/green-check.sh"\n'
                      'record_nonblocking_failure() { printf "%%s\\t%%s\\n" "$1" "$2" >> "$STATE_DIR/nonblocking-test-failures.tsv"; }\n'
                      'green_classify "" "$STATE_DIR/current.tsv" > "$STATE_DIR/classified.tsv"\n'
                      'green_report "$STATE_DIR/classified.tsv" "$STATE_DIR/report.md" plan.md "$LOG_DIR/green-check.log" 0\n%s') % (ROOT, base, base, tail)
            done = subprocess.run(['bash', '-c', script], cwd=base, capture_output=True, text=True, timeout=60)
            read = lambda name: (base / name).read_text() if (base / name).exists() else ''
            return done, read('classified.tsv'), read('report.md'), read('nonblocking-test-failures.tsv')

    def test_the_blocked_command_never_reaches_repair_and_is_reported_as_not_performed(self):
        done, classified, report, ledger = self.run_green([BLOCKED], 'echo "regressions=$(green_regressions "$STATE_DIR/classified.tsv")"')
        self.assertIn('regressions=1', done.stdout, done.stderr)                               # only the real cargo failure
        self.assertIn('BLOCKED-SETUP\t' + E2E, classified)
        self.assertIn('REGRESSION\tcargo test --manifest-path backend/Cargo.toml', classified)
        self.assertIn('**Not performed: BLOCKED-SETUP.**', report)
        self.assertIn('`%s` -- G-7: the user stops that process.' % E2E, report)
        self.assertIn('| BLOCKED-SETUP |', report)
        self.assertIn('BLOCKED-SETUP, not performed: %s (G-7: the user stops that process.)' % E2E, ledger)

    def test_when_only_blocked_commands_fail_the_report_does_not_say_all_passed(self):
        done, classified, report, _ = self.run_green([BLOCKED], 'sed -i.bak "/cargo test/d" "$STATE_DIR/current.tsv"; '
                                                      'green_classify "" "$STATE_DIR/current.tsv" > "$STATE_DIR/classified.tsv"; '
                                                      'green_report "$STATE_DIR/classified.tsv" "$STATE_DIR/report.md" plan.md "$LOG_DIR/green-check.log" 0')
        self.assertNotIn('All verification commands passed', report)
        self.assertIn('could not run (BLOCKED-SETUP)', report)

    def test_without_a_blocked_row_nothing_changes(self):
        done, classified, report, ledger = self.run_green([PASSING], 'true')
        self.assertIn('REGRESSION\t' + E2E, classified)
        self.assertNotIn('BLOCKED-SETUP', classified + report + ledger)

    def test_a_ledger_entry_is_written_once(self):
        _, _, _, ledger = self.run_green([BLOCKED], 'green_report "$STATE_DIR/classified.tsv" "$STATE_DIR/report.md" plan.md "$LOG_DIR/green-check.log" 0')
        self.assertEqual(ledger.count('BLOCKED-SETUP, not performed'), 1)


if __name__ == '__main__':
    unittest.main()
