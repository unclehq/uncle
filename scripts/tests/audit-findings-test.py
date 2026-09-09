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
        self.report = self.work / 'FINAL_AUDIT.md'
        self.report.write_bytes((TABLE).encode("utf-8"))
        self.state = self.work / 'workflow'

    def run_review(self, answers):
        return subprocess.run([sys.executable, '-B', str(HELPER), str(self.report), str(self.state)], input=answers, text=True, capture_output=True, timeout=10)

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

    def test_empty_is_keep_invalid_reprompts(self):
        result = self.run_review('perhaps\n\ny\n')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.record()['decisions']['FA-1']['decision'], 'keep')

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

    def test_driver_gates_both_formats_and_resume(self):
        for driver, prefix, column in [('stagegate.sh', '', 0), ('change-workflow.sh', 'run-123\t', 1)]:
            with self.subTest(driver=driver):
                shutil.rmtree(self.state / 'audit-dispositions', ignore_errors=True)
                # Execute the production WAIT arm, avoiding external agents,
                # approval dialogs and issue-close calls from the other states.
                source = (ROOT / 'scripts' / driver).read_text()
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
                sha = hashlib.sha256(self.report.read_bytes()).hexdigest()
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
                self.report.write_bytes((TABLE + '\n').encode("utf-8"))
                (self.state / 'state').write_bytes(('WAIT_AUDIT_OVERRIDE\n').encode("utf-8"))
                result = subprocess.run([bash_executable(), 'harness.sh'], cwd=self.work, input='', text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.report.write_bytes((TABLE).encode("utf-8"))

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

if __name__ == '__main__':
    unittest.main()
