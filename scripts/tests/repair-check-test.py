"""repair_check.py: a repair is judged by the files it changed."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts/lib/repair_check.py'

REVIEW = """# TEST_REVIEW.md

## Findings

| ID | Req | Blocks | Evidence | Defect | Required correction |
|---|---|---|---|---|---|
| TR-1 | R-1 | YES | `src/calc.js:84-88` clears operands in `appendDigit` only | decimal path | Fix `appendDecimal`; add T-19 to `tests/unit/calc.test.js` |
| TR-2 | R-18 | YES | `tests/defects/inject.js:84-89` never links node_modules | vacuous | Set NODE_PATH in `inject.js` |
| TR-3 | B-1 | NO | `tests/browser/ui.test.js:90` | closed | None |

## Acceptance gate

| ID | Required | Status | Evidence |
|---|---|---|---|
| COVERAGE | YES | FAIL | TR-1 untested |
| TR-1 | YES | FAIL | unchanged |
| TR-2 | YES | FAIL | unchanged |
| TR-3 | NO | PASS | closed |
"""


class RepairCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for rel in ('src/calc.js', 'tests/unit/calc.test.js', 'tests/defects/inject.js', 'tests/browser/ui.test.js'):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text('original ' + rel + '\n')
        (self.root / 'node_modules/x').mkdir(parents=True)
        (self.root / 'node_modules/x/index.js').write_text('dep\n')
        (self.root / '.uncle/workflow').mkdir(parents=True)
        (self.root / 'TEST_REVIEW.md').write_text(REVIEW)
        (self.root / 'IMPLEMENTATION_NOTES.md').write_text('# Notes\n')
        self.snap = self.root / '.uncle/workflow/repair-check.json'

    def run_tool(self, *args):
        proc = subprocess.run([sys.executable, '-B', str(TOOL), *args], cwd=self.root,
                              capture_output=True, text=True)
        return proc.returncode, proc.stdout.split(), proc.stderr

    def snapshot(self, report='TEST_REVIEW.md'):
        code, _, err = self.run_tool('snapshot', report, str(self.snap))
        self.assertEqual(code, 0, err)

    def judge(self):
        code, ids, _ = self.run_tool('judge', str(self.snap), 'IMPLEMENTATION_NOTES.md')
        return code, ids

    def test_blocking_findings_and_their_files_are_snapshotted(self):
        self.snapshot()
        import json
        data = json.loads(self.snap.read_text())
        self.assertEqual(set(data['findings']), {'TR-1', 'TR-2', 'COVERAGE'}, 'TR-3 does not block')
        self.assertEqual(data['findings']['TR-1']['paths'], ['src/calc.js', 'tests/unit/calc.test.js'])
        self.assertEqual(data['findings']['TR-2']['paths'], ['tests/defects/inject.js'])
        self.assertEqual(data['findings']['COVERAGE']['paths'], [])

    def test_a_report_alone_is_not_a_repair(self):
        self.snapshot()
        (self.root / 'IMPLEMENTATION_NOTES.md').write_text('TR-1 fixed. TR-2 fixed. All green.\n')
        (self.root / 'AUTOMATED_TEST_REPORT.md').write_text('PASS\n')
        (self.root / 'node_modules/x/index.js').write_text('dep changed\n')
        code, ids = self.judge()
        self.assertEqual((code, ids), (1, ['TR-1', 'TR-2', 'COVERAGE']))

    def test_changing_a_named_file_repairs_that_finding_and_the_tree_fallback(self):
        self.snapshot()
        (self.root / 'src/calc.js').write_text('fixed\n')
        code, ids = self.judge()
        self.assertEqual((code, ids), (4, ['TR-2']), 'partial: some findings changed, exit 4')

    def test_a_file_named_in_the_disposition_row_counts(self):
        self.snapshot()
        (self.root / 'src/calc.js').write_text('fixed\n')
        (self.root / 'tests/browser/ui.test.js').write_text('honours PLAYWRIGHT_BROWSERS_PATH\n')
        (self.root / 'IMPLEMENTATION_NOTES.md').write_text(
            '| TR-2 | Fixed in `tests/browser/ui.test.js` by deriving the path from the env |\n')
        code, ids = self.judge()
        self.assertEqual((code, ids), (0, []))

    def test_new_file_the_correction_asks_for_counts(self):
        (self.root / 'TEST_REVIEW.md').write_text(REVIEW.replace('`tests/defects/inject.js:84-89` never links node_modules',
                                                                 'harness missing; add `tests/defects/env.js`'))
        self.snapshot()
        (self.root / 'src/calc.js').write_text('fixed\n')
        (self.root / 'tests/defects/env.js').write_text('module.exports = {}\n')
        self.assertEqual(self.judge(), (0, []))

    def test_a_decision_id_citation_is_not_mistaken_for_a_file(self):
        # A real stuck run: INTEGRITY's own evidence only cross-referenced
        # TR-1's decision/invariant IDs ("DEC-9/I-5"), never repeating TR-1's
        # actual file paths. "DEC-9/I-5" matches the same word/word shape as a
        # real repository path, so it must not be tracked as one -- doing so
        # left INTEGRITY waiting on a file that could never be written, and
        # the repair agent, reading it from REPAIR_BRIEF.md, spent three
        # attempts on a nonexistent target instead of the real fix.
        review = REVIEW.replace(
            '| COVERAGE | YES | FAIL | TR-1 untested |',
            '| COVERAGE | YES | FAIL | TR-1 untested |\n'
            '| INTEGRITY | YES | FAIL | TR-1: `calc()` violates DEC-9/I-5 in an untested branch |')
        (self.root / 'TEST_REVIEW.md').write_text(review)
        self.snapshot()
        import json
        data = json.loads(self.snap.read_text())
        self.assertEqual(data['findings']['INTEGRITY']['paths'], [])
        # A real fix elsewhere in the tree must still satisfy INTEGRITY, via
        # the pathless tree-wide fallback -- not by writing "DEC-9/I-5".
        (self.root / 'src/calc.js').write_text('fixed\n')
        (self.root / 'tests/defects/inject.js').write_text('fixed\n')
        code, ids = self.judge()
        self.assertEqual((code, ids), (0, []))

    def test_unstructured_report_is_judged_by_the_tree(self):
        (self.root / 'green-check.md').write_text('## Green check\n\nFAIL npm test\n')
        self.snapshot('green-check.md')
        self.assertEqual(self.judge()[0], 1)
        (self.root / 'src/calc.js').write_text('fixed\n')
        self.assertEqual(self.judge(), (0, []))

    def test_brief_lists_only_open_findings_and_disowns_the_notes(self):
        self.snapshot()
        out = self.root / '.uncle/workflow/REPAIR_BRIEF.md'
        code, _, err = self.run_tool('brief', 'TEST_REVIEW.md', str(self.snap), str(out), 'TR-2', 'COVERAGE')
        self.assertEqual(code, 0, err)
        text = out.read_text()
        self.assertIn('**TR-2**', text)
        self.assertIn('`tests/defects/inject.js`', text)
        self.assertIn('**COVERAGE**', text)
        self.assertNotIn('TR-3', text)
        self.assertNotIn('**TR-1**', text)
        self.assertIn('not as evidence', text)
        self.assertIn('| TR-2 | YES | FAIL |', text)


if __name__ == '__main__':
    unittest.main()
