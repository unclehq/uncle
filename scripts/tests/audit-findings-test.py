#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from process_tree import bash_executable

HELPER = ROOT / 'scripts/lib/audit-findings.py'
TABLE = '''## Findings

| ID | Severity | Evidence | Required correction | Blocks |
|---|---|---|---|---|
| FA-1 | blocking | Missing browser evidence | Run browser checks | YES |
| FA-2 | blocking | Missing comparison | Compare HTML to PDF | YES |
| FA-3 | low | Stale prose | Refresh docs | NO |

NOT READY
'''

class FindingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        (self.work / '.uncle/docs').mkdir(parents=True)
        self.report = self.work / '.uncle/docs/FINAL_AUDIT.md'
        self.report.write_bytes((TABLE).encode("utf-8"))
        self.state = self.work / 'workflow'

    def run_review(self, answers, env=None):
        return subprocess.run([sys.executable, '-B', str(HELPER), str(self.report), str(self.state)], input=answers, text=True, capture_output=True, timeout=10, env=env)

    def record(self):
        sha = hashlib.sha256(self.report.read_bytes()).hexdigest()
        return json.loads((self.state / 'audit-dispositions' / (sha + '.json')).read_text())

    def test_all_ignored_ready_preserves_audit(self):
        result = self.run_review('y\ny\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count('Choose [s] Skip'), 2)
        self.assertEqual(self.record()['effective_verdict'], 'READY')
        self.assertEqual(self.report.read_text(), TABLE)
        self.assertNotIn('FA-3', self.record()['decisions'])
        self.assertEqual(self.run_review('').returncode, 0)

    def test_keep_then_resume_only_outstanding(self):
        self.assertEqual(self.run_review('y\nn\n').returncode, 1)
        self.assertEqual(self.record()['effective_verdict'], 'NOT_READY')
        result = self.run_review('y\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count('Choose [s] Skip'), 1)

    def test_eof_preserves_partial_decisions(self):
        self.assertEqual(self.run_review('y\n').returncode, 1)
        self.assertEqual(self.record()['decisions']['FA-1']['decision'], 'ignore')
        self.assertNotIn('FA-2', self.record()['decisions'])

    def test_blank_and_invalid_answers_require_explicit_choice(self):
        result = self.run_review('perhaps\n\ns\nr\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.record()['decisions']['FA-1']['decision'], 'skip')
        self.assertEqual(result.stdout.count('Choose S to skip'), 2)

    def test_blank_then_eof_does_not_record_keep(self):
        result = self.run_review('\n')
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.state / 'audit-dispositions').exists())

    def test_unattended_eof_keeps_final_review_pending(self):
        import os
        env = dict(os.environ, UNCLE_UNATTENDED='1')
        result = self.run_review('', env=env)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('No decision received; audit remains pending.', result.stdout)
        self.assertFalse((self.state / 'audit-dispositions').exists())

    def test_unattended_user_can_explicitly_skip_final_findings(self):
        import os
        env = dict(os.environ, UNCLE_UNATTENDED='1', UNCLE_APPROVAL_NAME='owner')
        result = self.run_review('s\nr\n', env=env)
        self.assertEqual(result.returncode, 0, result.stdout)
        record = self.record()
        self.assertEqual(record['decisions']['FA-1']['decision'], 'skip')
        self.assertEqual(record['decisions']['FA-2']['decision'], 'human-reviewed')
        self.assertEqual(record['decisions']['FA-1']['approved_by'], 'owner')

    def test_changed_audit_invalidates_ignores(self):
        self.run_review('y\ny\n')
        self.report.write_bytes((TABLE.replace('Missing comparison', 'New missing comparison')).encode("utf-8"))
        self.assertEqual(self.run_review('').returncode, 1)

    def test_skip_and_human_review_distinct_and_both_ready(self):
        result = self.run_review('s\nr\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        record = self.record()
        self.assertEqual(record['decisions']['FA-1']['decision'], 'skip')
        self.assertEqual(record['decisions']['FA-2']['decision'], 'human-reviewed')
        self.assertEqual(record['effective_verdict'], 'READY')
        self.assertEqual(self.run_review('').returncode, 0)
        result = subprocess.run([sys.executable, '-B', str(HELPER), str(self.report), str(self.state), '--check'])
        self.assertEqual(result.returncode, 0)

    def test_table_wrappers_conclusion_and_escaped_pipes(self):
        for text in (
            TABLE.replace('NOT READY', '## Conclusion\n\n**NOT READY**'),
            TABLE.replace('| ID', '```markdown\n| ID').replace('\nNOT READY', '\n```\nNOT READY'),
            TABLE.replace('Missing comparison', r'Missing A\|B comparison'),
        ):
            self.report.write_bytes((text).encode("utf-8"))
            result = self.run_review('r\ns\n')
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_trailing_commentary_preserved_and_requires_decisions(self):
        for summary in ('Checked: regression checks passed.',
                        'Category 1 sweep: every PASS tied to evidence.\n'
                        'Re-run: `python3 -m py_compile uncle_tui.py` rc=0.\n\nNo waivers.'):
            with self.subTest(summary=summary):
                shutil.rmtree(self.state, ignore_errors=True)
                report = TABLE.replace('NOT READY', summary + '\n\nNOT READY')
                self.report.write_text(report, encoding='utf-8')
                self.assertEqual(self.run_review('').returncode, 1)
                result = self.run_review('s\nr\n')
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(set(self.record()['decisions']), {'FA-1', 'FA-2'})
                for line in summary.splitlines():
                    if line:
                        self.assertIn(line, result.stdout)
                        for decision in self.record()['decisions'].values():
                            self.assertIn(line, decision['finding']['evidence'])
                self.assertEqual(self.report.read_text(), report)

    def test_commentary_cannot_hide_rows(self):
        for row in ('| FA-4 | high | Missing | Fix | YES |', '| malformed row'):
            self.report.write_text(TABLE.replace('NOT READY',
                'Category 1 sweep: checks run.\n' + row + '\nNOT READY'))
            self.assertEqual(self.run_review('s\nr\n').returncode, 2)
            self.assertFalse((self.state / 'audit-dispositions').exists())

    def test_row_after_verdict_cannot_be_hidden(self):
        self.report.write_bytes((TABLE + '| FA-4 | blocking | Missing check | Run check | YES |\n').encode("utf-8"))
        self.assertEqual(self.run_review('s\ns\n').returncode, 2)

    def test_dialog_detection_and_choice_keys(self):
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            import curses
        except ImportError:
            self.skipTest('curses is unavailable')
        from uncle_tui import UncleTUI
        ui = UncleTUI.__new__(UncleTUI)
        ui.state = 'running'
        raw_answers = []
        ui._send_raw = raw_answers.append
        ui._read_banner('AUDIT REVIEW REQUIRED: FINAL_AUDIT.md')
        self.assertEqual(raw_answers, [])
        self.assertEqual(ui.gate_file, 'FINAL_AUDIT.md')
        ui._read_banner('HUMAN REVIEW REQUIRED: REQUIREMENTS.md')
        self.assertEqual(raw_answers, [])
        ui.prompt_kind = ''
        ui.partial = 'Audit finding FA-1. Choose [s] Skip, [r] Human reviewed — OK, [n] Keep blocking: '
        ui.prompt_seen = 2
        ui._detect_prompt()
        self.assertEqual(ui.prompt_kind, 'audit')
        answers = []
        ui.answer_prompt = answers.append
        for key in ('s', 'r', 'n'):
            ui.handle_key(ord(key))
        ui.handle_key(27)
        self.assertEqual(answers, ['s', 'r', 'n', 'n'])

    def test_malformed_findings_never_ready(self):
        for bad in (TABLE.replace('FA-2', 'FA-1'), TABLE.replace('| YES |', '| MAYBE |'), TABLE.replace('| YES |', '| NO |'), TABLE.replace('## Findings', '## Other'), TABLE.replace('Missing comparison', 'Missing | comparison')):
            with self.subTest(bad=bad):
                self.report.write_bytes((bad).encode("utf-8"))
                self.assertEqual(self.run_review('y\ny\n').returncode, 2)

    def test_annotated_id_and_bold_headers_still_parse(self):
        # A model echoing the review's own "AR-002 (High)" heading shape into
        # the ID cell, or bolding the header row, is still naming the same
        # findings and columns -- not a different, unparseable table.
        annotated = (TABLE.replace('| FA-1 |', '| FA-1 (High) |')
                     .replace('| ID | Severity | Evidence | Required correction | Blocks |',
                              '| **ID** | **Severity** | **Evidence** | **Required correction** | **Blocks** |'))
        self.report.write_bytes(annotated.encode('utf-8'))
        result = self.run_review('y\ny\n')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('FA-1', self.record()['decisions'])

    def test_driver_gates_both_formats_and_resume(self):
        for driver, prefix, column in [('stagegate.sh', '', 1), ('change-workflow.sh', 'run-123\t', 1)]:
            with self.subTest(driver=driver):
                shutil.rmtree(self.state / 'audit-dispositions', ignore_errors=True)
                # Execute the production WAIT arm, avoiding external agents,
                # approval dialogs and issue-close calls from the other states.
                source = (ROOT / 'scripts' / driver).read_text(encoding='utf-8')
                arm = source.split('        WAIT_AUDIT_OVERRIDE)\n', 1)[1].split('\n        COMPLETE)', 1)[0]
                harness = f'''set -euo pipefail
ROOT={ROOT.as_posix()!r}
STATE_DIR=workflow
STATE_FILE=workflow/state
VERDICT_FILE=workflow/audit-verdict
AUDIT_OVERRIDE_FILE=workflow/audit-override
STAGEGATE_RUN_ID=run-123
. "$ROOT/scripts/lib/sha256.sh"
. "$ROOT/scripts/lib/audit-verdict.sh"
require_file() {{ [[ -s "$1" ]]; }}
set_state() {{ printf '%s\\n' "$1" > "$STATE_FILE"; }}
for turn in 1 2; do
 case "$(cat "$STATE_FILE")" in
 WAIT_AUDIT_OVERRIDE)
{arm}
 COMPLETE) exit 0 ;;
 *) exit 8 ;;
 esac
done
'''
                self.state.mkdir(exist_ok=True)
                canonical = self.state / 'documents' / 'FINAL_AUDIT.json'
                canonical.parent.mkdir(exist_ok=True)
                canonical.write_text(json.dumps({
                    'schema': 'uncle.artifact/v1', 'kind': 'final-audit',
                    'findings': [
                        {'id': 'FA-1', 'severity': 'blocking', 'evidence': 'Missing browser evidence',
                         'required_correction': 'Run browser checks', 'blocks': 'YES'},
                        {'id': 'FA-2', 'severity': 'blocking', 'evidence': 'Missing comparison',
                         'required_correction': 'Compare HTML to PDF', 'blocks': 'YES'},
                    ], 'verdict': 'NOT READY',
                }))
                sha = hashlib.sha256(canonical.read_bytes()).hexdigest()
                (self.state / 'audit-verdict').write_bytes((prefix + 'NOT_READY\t' + sha + '\n').encode("utf-8"))
                (self.state / 'state').write_bytes(('WAIT_AUDIT_OVERRIDE\n').encode("utf-8"))
                (self.work / 'harness.sh').write_bytes((harness).encode("utf-8"))
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, input='s\nn\n', text=True, capture_output=True)
                self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
                self.assertEqual((self.state / 'state').read_text().strip(), 'WAIT_AUDIT_OVERRIDE')
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, input='r\n', text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual((self.state / 'state').read_text().strip(), 'COMPLETE')
                self.assertEqual((self.state / 'audit-verdict').read_text().split('\t')[column], 'READY')
                self.assertIn('NOT_READY', (self.state / 'audit-verdict.original').read_text())
                self.assertEqual(self.report.read_text(), TABLE)
                # Crash after verdict persistence: resume without another vote.
                (self.state / 'state').write_bytes(('WAIT_AUDIT_OVERRIDE\n').encode("utf-8"))
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, input='', text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                # A revised audit must never inherit the effective READY.
                canonical.write_text(canonical.read_text() + '\n')
                (self.state / 'state').write_bytes(('WAIT_AUDIT_OVERRIDE\n').encode("utf-8"))
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, input='', text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                canonical.write_text(canonical.read_text().rstrip() + '\n')

    def test_driver_unattended_skips_and_completes_both_drivers(self):
        for driver, prefix, column in [('stagegate.sh', '', 1), ('change-workflow.sh', 'run-123\t', 1)]:
            with self.subTest(driver=driver):
                shutil.rmtree(self.state, ignore_errors=True)
                source = (ROOT / 'scripts' / driver).read_text(encoding='utf-8')
                arm = source.split('        WAIT_AUDIT_OVERRIDE)\n', 1)[1].split('\n        COMPLETE)', 1)[0]
                harness = f'''set -euo pipefail
ROOT={ROOT.as_posix()!r}
STATE_DIR=workflow
STATE_FILE=workflow/state
VERDICT_FILE=workflow/audit-verdict
AUDIT_OVERRIDE_FILE=workflow/audit-override
UNATTENDED_FILE=workflow/unattended-gates
UNATTENDED=1
STAGEGATE_RUN_ID=run-123
. "$ROOT/scripts/lib/sha256.sh"
. "$ROOT/scripts/lib/audit-verdict.sh"
require_file() {{ [[ -s "$1" ]]; }}
set_state() {{ printf '%s\\n' "$1" > "$STATE_FILE"; }}
for turn in 1 2; do
 case "$(cat "$STATE_FILE")" in
 WAIT_AUDIT_OVERRIDE)
{arm}
 COMPLETE) exit 0 ;;
 *) exit 8 ;;
 esac
done
'''
                canonical = self.state / 'documents' / 'FINAL_AUDIT.json'
                canonical.parent.mkdir(parents=True)
                canonical.write_text(json.dumps({
                    'schema': 'uncle.artifact/v1', 'kind': 'final-audit', 'verdict': 'NOT READY',
                    'findings': [{'id': 'FA-%d' % n, 'severity': 'blocking', 'evidence': 'e', 'required_correction': 'c', 'blocks': 'YES'} for n in (1, 2, 3)],
                }))
                before = hashlib.sha256(canonical.read_bytes()).hexdigest()
                (self.state / 'audit-verdict').write_text(prefix + 'NOT_READY\t' + before + '\n')
                (self.state / 'state').write_text('WAIT_AUDIT_OVERRIDE\n')
                (self.work / 'harness.sh').write_text(harness)
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn('3 blocking audit findings skipped', result.stdout)
                self.assertEqual((self.state / 'state').read_text().strip(), 'COMPLETE')
                self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(), before)
                self.assertIn('NOT_READY', (self.state / 'audit-verdict.original').read_text())
                ledger = (self.state / 'unattended-gates').read_text().splitlines()
                self.assertEqual(len([l for l in ledger if '\taudit-finding-skipped\t' in l]), 3)
                # Resume after the skip, and a second run, add no ledger lines.
                (self.state / 'state').write_text('WAIT_AUDIT_OVERRIDE\n')
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(len((self.state / 'unattended-gates').read_text().splitlines()), 3)


    def test_modal_labels_and_long_finding_fit(self):
        import sys
        sys.path.insert(0, str(ROOT))
        try:
            import curses
        except ImportError:
            self.skipTest('curses is unavailable')
        from uncle_tui import UncleTUI
        class Screen:
            def __init__(self): self.writes = []
            def addnstr(self, y, x, text, n, *args): self.writes.append((y, text))
        ui = UncleTUI.__new__(UncleTUI)
        ui.prompt_kind = 'audit'
        ui.prompt_text = 'Audit finding FA-1. ' + 'Evidence details. ' * 200 + 'Choose [s] Skip, [r] Human reviewed — OK, [n] Keep blocking: '
        ui.gate_file = 'FINAL_AUDIT.md'
        ui.stdscr = Screen()
        ui.color = {'title': 0, 'sel': 0, 'accent': 0, 'text': 0}
        ui._draw_modal(30, 100)
        displayed = '\n'.join(text for _, text in ui.stdscr.writes)
        self.assertIn('Skip', displayed)
        self.assertIn('Human reviewed', displayed)
        self.assertIn('Keep blocking', displayed)
        self.assertLess(max(y for y, _ in ui.stdscr.writes), 30)

class UnattendedTests(FindingsTests):
    def unattended(self, *extra, stdin=subprocess.DEVNULL):
        return subprocess.run([sys.executable, '-B', str(HELPER), str(self.report), str(self.state), '--unattended',
                               '--ledger', str(self.ledger), *extra], stdin=stdin, text=True, capture_output=True, timeout=10)

    def setUp(self):
        super().setUp()
        self.ledger = self.work / 'unattended-gates'

    def test_skips_all_blockers_stdin_closed_audit_unchanged(self):
        before = hashlib.sha256(self.report.read_bytes()).hexdigest()
        result = self.unattended()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('2 blocking audit findings skipped', result.stdout)
        self.assertNotIn('Choose [s] Skip', result.stdout)
        self.assertEqual(hashlib.sha256(self.report.read_bytes()).hexdigest(), before)
        self.assertEqual(self.report.read_text(), TABLE)
        decisions = self.record()['decisions']
        self.assertEqual(sorted(decisions), ['FA-1', 'FA-2'])
        for entry in decisions.values():
            self.assertEqual((entry['decision'], entry['mode'], entry['approved_by']), ('skip', 'unattended', 'unattended'))
        lines = self.ledger.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all('\taudit-finding-skipped\t' in line and 'accepted without human review' in line for line in lines))

    def test_single_blocker_wording(self):
        self.report.write_text(TABLE.replace('| FA-2 | blocking | Missing comparison | Compare HTML to PDF | YES |', '| FA-2 | blocking | Missing comparison | Compare HTML to PDF | NO |'))
        self.assertIn('1 blocking audit findings skipped', self.unattended().stdout)

    def test_rerun_does_not_duplicate_ledger(self):
        self.unattended()
        again = self.unattended()
        self.assertEqual(again.returncode, 0)
        self.assertIn('2 blocking audit findings skipped', again.stdout)
        self.assertEqual(len(self.ledger.read_text().splitlines()), 2)

    def test_preseeded_disposition_is_ledgered(self):
        self.unattended()
        self.ledger.unlink()
        self.assertEqual(self.unattended().returncode, 0)
        self.assertEqual(len(self.ledger.read_text().splitlines()), 2)

    def test_human_decision_kept_not_ledgered(self):
        self.assertEqual(self.run_review('y\nn\n').returncode, 1)
        self.assertEqual(self.unattended().returncode, 0)
        decisions = self.record()['decisions']
        self.assertEqual(decisions['FA-1']['decision'], 'ignore')
        self.assertNotIn('mode', decisions['FA-1'])
        self.assertEqual(len(self.ledger.read_text().splitlines()), 1)

    def test_attended_reprompts_unattended_waivers_and_check_reports_them(self):
        self.unattended()
        check = subprocess.run([sys.executable, '-B', str(HELPER), str(self.report), str(self.state), '--check'], text=True, capture_output=True, timeout=10)
        self.assertEqual(check.returncode, 1)
        self.assertIn('Unattended waivers', check.stdout)
        check = subprocess.run([sys.executable, '-B', str(HELPER), str(self.report), str(self.state), '--check', '--unattended'], text=True, capture_output=True, timeout=10)
        self.assertEqual(check.returncode, 0)
        result = self.run_review('')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count('Choose [s] Skip'), 1)
        self.assertEqual(self.run_review('r\nr\n').returncode, 0)

    def test_hand_edited_record_not_trusted_by_attended(self):
        self.unattended()
        sha = hashlib.sha256(self.report.read_bytes()).hexdigest()
        path = self.state / 'audit-dispositions' / (sha + '.json')
        record = json.loads(path.read_text())
        for entry in record['decisions'].values():
            entry['approved_by'] = 'a human'
        path.write_text(json.dumps(record))
        self.assertEqual(self.run_review('').returncode, 1)

    def test_malformed_and_tampered_never_skipped(self):
        self.report.write_text('## Findings\n\nnot a table\n')
        result = self.unattended()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.ledger.exists())
        self.report.write_text(TABLE)
        self.unattended()
        sha_record = next((self.state / 'audit-dispositions').iterdir())
        record = json.loads(sha_record.read_text())
        record['audit_sha256'] = 'x'
        sha_record.write_text(json.dumps(record))
        self.assertEqual(self.unattended().returncode, 2)

    def test_attended_eof_still_pending(self):
        result = self.run_review('')
        self.assertEqual(result.returncode, 1)
        self.assertIn('audit remains pending', result.stdout)

if __name__ == '__main__':
    unittest.main()
