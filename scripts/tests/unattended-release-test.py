#!/usr/bin/env python3
"""Findings an unattended run waived do not stop release; nothing else is lifted, and the record stays."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import envelope  # noqa: E402

ENGINE = (LIB / 'change-pr.sh').read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
HASH = '76709ca832c5' + 'a' * 52


def fresh_engine(directory):
    os.chdir(directory)
    (Path(directory) / '.uncle/workflow').mkdir(parents=True)
    namespace = {'__name__': 'engine'}
    exec(compile(ENGINE.split('\ndef main():', 1)[0], 'engine', 'exec'), namespace)
    return namespace


def envelopes(audit='fail', verification='pass', review='pass'):
    return {'review': {'result': review}, 'verification': {'result': verification}, 'audit': {'result': audit},
            'implementation': {'artifact': {'digest': {'gitTree': 'T'}}},
            'verification_inputs': None}


def ready(e):
    e['verification'] = dict(e['verification'], inputs={'artifact': {'digest': {'gitTree': 'T'}}})
    e['audit'] = dict(e['audit'], inputs={'artifact': {'digest': {'gitTree': 'T'}}})
    return e


class Release(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.addCleanup(os.chdir, self.old)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = fresh_engine(self.temp.name)
        self.state = Path(self.temp.name) / '.uncle/workflow'

    def ledger(self, *findings, audit=HASH[:12]):
        lines = ['2026-01-01T00:00:00Z\taudit-finding-skipped\t%s accepted without human review (audit %s)' % (f, audit)
                 for f in findings]
        (self.state / 'unattended-gates').write_text('\n'.join(lines) + '\n')

    def test_a_failed_audit_blocks_release_as_before(self):
        self.assertIn('audit result fail', envelope.blocking_reason(ready(envelopes()), 'T'))

    def test_waiving_the_audit_lifts_only_that_refusal(self):
        self.assertEqual(envelope.blocking_reason(ready(envelopes()), 'T', ('audit',)), '')
        self.assertIn('verification result fail',
                      envelope.blocking_reason(ready(envelopes(verification='fail')), 'T', ('audit',)))
        self.assertIn('review result fail', envelope.blocking_reason(ready(envelopes(review='fail')), 'T', ('audit',)))

    def test_a_waiver_never_hides_an_artifact_mismatch(self):
        self.assertIn('artifact mismatch', envelope.blocking_reason(ready(envelopes()), 'OTHER', ('audit',)))

    def test_skipped_findings_for_this_audit_count(self):
        self.ledger('FA-001', 'FA-002')
        self.assertEqual(self.engine['unattended_audit_waiver']({'audit_hash': HASH}), 2)
        self.assertEqual(self.engine['waived_stages']({'audit_hash': HASH}), ('audit',))

    def test_skipped_findings_for_a_different_audit_do_not(self):
        self.ledger('FA-001', audit='deadbeef0000')
        self.assertEqual(self.engine['unattended_audit_waiver']({'audit_hash': HASH}), 0)
        self.assertEqual(self.engine['waived_stages']({'audit_hash': HASH}), ())

    def test_no_ledger_no_waiver(self):
        self.assertEqual(self.engine['waived_stages']({'audit_hash': HASH}), ())

    def test_only_skipped_finding_lines_count(self):
        (self.state / 'unattended-gates').write_text(
            '2026-01-01T00:00:00Z\tCHANGE_PLAN\tapprove (audit %s)\n' % HASH[:12])
        self.assertEqual(self.engine['unattended_audit_waiver']({'audit_hash': HASH}), 0)

    def test_the_approver_of_a_waiver_is_recorded_as_no_human(self):
        self.ledger('FA-001')
        (self.state / 'audit-verdict.original').write_text('run\tNOT_READY\t%s\n' % HASH)
        entry = self.engine['override_entry']({'audit_hash': HASH, 'verdict_run': 'run'})
        self.assertEqual(entry['approved_by'], 'unattended (no human)')


if __name__ == '__main__':
    unittest.main()
