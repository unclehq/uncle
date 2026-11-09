#!/usr/bin/env python3
"""A failing driver check is never laundered into READY, and an audit that was given no evidence is not accepted."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib/audit-verdict.sh'

PRELUDE = r'''
set -u
source "%(lib)s"
STATE_DIR="%(state)s"; GREEN_CHECK=1; GREEN_CLASS="$STATE_DIR/g.tsv"; GREEN_CMDS="$STATE_DIR/g.cmds"; GREEN_MD=g.md
VERDICT_FILE="$STATE_DIR/verdict"; AUDIT_OVERRIDE_FILE="$STATE_DIR/override"; UNATTENDED=1; UNATTENDED_FILE="$STATE_DIR/ledger"
green_regressions() { grep -c '^REGRESSION' "$1" || true; }
green_failed_ids() { awk -F'\t' '$1=="REGRESSION"{printf "green-%%s ", NR}' "$1"; }
waived_ids() { for i in "$@"; do [[ -e "$STATE_DIR/waive-$i" ]] || return 1; done; }
set_state() { echo "STATE=$1"; }
hash_file() { echo deadbeef; }
verdict_file_field() { echo deadbeef; }
'''


class Unresolved(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'g.cmds').write_text('npx vitest run\n')
        (self.tmp / 'documents').mkdir()
        (self.tmp / 'documents/FINAL_AUDIT.json').write_text('{}')

    def run_bash(self, body, green=None):
        if green is not None:
            (self.tmp / 'g.tsv').write_text(green)
        script = PRELUDE % {'lib': LIB, 'state': self.tmp} + body
        return subprocess.run(['bash', '-c', script], cwd=self.tmp, capture_output=True, text=True)

    def test_a_failing_command_is_unresolved(self):
        self.assertEqual(self.run_bash('audit_verification_unresolved', 'REGRESSION\tnpx vitest run\n').returncode, 0)

    def test_green_is_not_unresolved(self):
        self.assertEqual(self.run_bash('audit_verification_unresolved', 'PASS\tnpx vitest run\n').returncode, 1)

    def test_a_waiver_for_every_failing_command_resolves_it(self):
        (self.tmp / 'waive-green-1').write_text('reason')
        self.assertEqual(self.run_bash('audit_verification_unresolved', 'REGRESSION\tnpx vitest run\n').returncode, 1)

    def test_unattended_release_keeps_not_ready_when_a_check_still_fails(self):
        r = self.run_bash('''
final_audit_override_recovery NOT_READY - 0
echo "VERDICT=$(cat "$VERDICT_FILE" 2>/dev/null)"
''', 'REGRESSION\tnpx vitest run\n')
        self.assertIn('STATE=COMPLETE', r.stdout)                      # the run finishes
        self.assertNotIn('READY\tdeadbeef', r.stdout)                  # ...but is never rewritten to READY
        self.assertFalse((self.tmp / 'verdict').exists())
        self.assertIn('NOT_READY', r.stdout)
        self.assertIn('unresolved driver verification', (self.tmp / 'ledger').read_text())

    def test_an_audit_with_no_artifacts_is_blind(self):
        audit = self.tmp / 'A.md'
        audit.write_text('| FA-001 | The assigned prompt named no canonical JSON prerequisite artifacts |')
        self.assertEqual(self.run_bash('audit_blind_to_evidence "%s"' % audit).returncode, 0)
        audit.write_text('| FA-001 | Everything was verified against green-check.md |')
        self.assertEqual(self.run_bash('audit_blind_to_evidence "%s"' % audit).returncode, 1)


if __name__ == '__main__':
    unittest.main()
