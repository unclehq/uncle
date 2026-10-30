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

    def test_a_test_count_ratio_is_not_mistaken_for_a_file(self):
        # A real stuck run (calculator, 2026-10-29): COVERAGE's evidence said
        # "controls 4/4 passed", and "4/4" matched the same word/word shape as
        # a real repository path. Tracked as one ("4/4."), it never exists and
        # its hash is always None before and after, so a repair that genuinely
        # added new files (and left no existing named file touched) was judged
        # unrepaired even though the coverage gap it described was closed.
        review = REVIEW.replace(
            '| COVERAGE | YES | FAIL | TR-1 untested |',
            '| COVERAGE | YES | FAIL | mutation runner caught 10 of 10 (DI-1..DI-10) with controls 4/4. '
            'Playwright ran only 11 tests, no spec for T-12..T-16 |')
        (self.root / 'TEST_REVIEW.md').write_text(review)
        self.snapshot()
        import json
        data = json.loads(self.snap.read_text())
        self.assertEqual(data['findings']['COVERAGE']['paths'], [])
        # The real fix is a brand-new file the finding's own text never
        # names -- only the pathless tree-wide fallback can see it. TR-1 and
        # TR-2 are fixed too, the ordinary way, so the whole pass judges clean.
        (self.root / 'tests/browser/robust.test.js').parent.mkdir(parents=True, exist_ok=True)
        (self.root / 'tests/browser/robust.test.js').write_text('new coverage spec\n')
        (self.root / 'src/calc.js').write_text('fixed\n')
        (self.root / 'tests/defects/inject.js').write_text('fixed\n')
        code, ids = self.judge()
        self.assertEqual((code, ids), (0, []))

    def test_a_project_dotfile_is_tracked_with_its_leading_dot_intact(self):
        # A real stuck run (calculator, 2026-10-29): `.uncle/launch.json` is a
        # real, trackable project file (not driver state under
        # .uncle/workflow/), but a naive `.lstrip('./')` ate its leading dot
        # down to `uncle/launch.json` -- a path that can never exist. The
        # driver's own repair brief then cited that corrupted name, and a
        # repair that genuinely fixed `.uncle/launch.json` was judged as
        # having changed nothing because the wrong path's hash never moves.
        review = REVIEW.replace(
            '| COVERAGE | YES | FAIL | TR-1 untested |',
            '| COVERAGE | YES | FAIL | fix `.uncle/launch.json`, it has the wrong shape |')
        (self.root / 'TEST_REVIEW.md').write_text(review)
        (self.root / '.uncle/launch.json').write_text('{"kind":"webpage"}\n')
        self.snapshot()
        import json
        data = json.loads(self.snap.read_text())
        self.assertEqual(data['findings']['COVERAGE']['paths'], ['.uncle/launch.json'])
        (self.root / '.uncle/launch.json').write_text('{"kind":"webpage","command":["npm","start"]}\n')
        (self.root / 'src/calc.js').write_text('fixed\n')
        (self.root / 'tests/defects/inject.js').write_text('fixed\n')
        code, ids = self.judge()
        self.assertEqual((code, ids), (0, []))

    def test_driver_workflow_state_is_still_excluded(self):
        review = REVIEW.replace(
            '| COVERAGE | YES | FAIL | TR-1 untested |',
            '| COVERAGE | YES | FAIL | see `.uncle/workflow/green-check.md` |')
        (self.root / 'TEST_REVIEW.md').write_text(review)
        self.snapshot()
        import json
        data = json.loads(self.snap.read_text())
        self.assertEqual(data['findings']['COVERAGE']['paths'], [])

    def test_a_shell_variable_expansion_is_not_mistaken_for_a_file(self):
        # Same bug class as `4/4.` and the lstrip corruption: `$HOME/x.json`
        # has no `$` exclusion in the lookbehind, so it matched starting right
        # after the `$` as `HOME/x.json` -- a path that is never repo-relative
        # and can never exist, silently defeating change detection again.
        review = REVIEW.replace(
            '| COVERAGE | YES | FAIL | TR-1 untested |',
            '| COVERAGE | YES | FAIL | uses $HOME/.config/app/settings.json for config |')
        (self.root / 'TEST_REVIEW.md').write_text(review)
        self.snapshot()
        import json
        data = json.loads(self.snap.read_text())
        self.assertEqual(data['findings']['COVERAGE']['paths'], [])

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

    def test_paths_in_audit_sweep(self):
        # A systematic sweep of prose shapes that look path-like but are not,
        # run directly after a session that found three independent false
        # positives in this function reactively, one live incident at a
        # time. Each case documents a real way evidence text phrases a
        # non-path, so the next one is caught here instead of live.
        import importlib.util
        sys.path.insert(0, str(TOOL.parent))
        spec = importlib.util.spec_from_file_location('repair_check', TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        root = self.root
        non_paths = [
            'controls 4/4 passed and 10/10 mutants caught',
            'violates DEC-9/I-5 in an untested branch',
            'version bumped to 1.2.3/stable for release',
            'server listens on localhost:5173/api/users and returns 200',
            '95/100 coverage achieved this run',
            'the file ../../etc/passwd should never be read',
            'uses $HOME/.config/app/settings.json for config',
            'fetches https://cdn.example.com/lib/react.production.min.js successfully',
        ]
        for text in non_paths:
            self.assertEqual(module.paths_in(text, root), [], 'false positive on: %r' % text)
        real_paths = [
            ('see [the fix](src/App.jsx) for details', ['src/App.jsx']),
            ('src/App.jsx:42-51 has the bug', ['src/App.jsx']),
            ('edited .uncle/launch.json and .uncle/workflow/state', ['.uncle/launch.json']),
        ]
        for text, expected in real_paths:
            self.assertEqual(module.paths_in(text, root), expected, 'false negative on: %r' % text)


if __name__ == '__main__':
    unittest.main()
