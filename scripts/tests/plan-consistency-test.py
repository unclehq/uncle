#!/usr/bin/env python3
"""plan_consistency.py (file-name conflicts across sections) and the stage step's prompts built from it."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import plan_consistency as pc
import project_plan_stage as stage

PLAN = '''# Project plan

## 4. Components

| ID | Name | Files |
|---|---|---|
| C-1 | Calculator | `src/Calculator.jsx`, `src/theme.css` |

## 12. Implementation steps

1. Scaffold. Owns: `package.json`, `index.html`, `.gitignore`
2. Core. Owns: `src/calc.js`, `src/Calculator.jsx`, `src/theme.css`
3. Tests. Owns: `tests/calc.test.js`

## 15. Restrictions

| ID | Restriction | Where |
|---|---|---|
| R-4 | Palette is a custom property | %s |
'''


class Findings(unittest.TestCase):
    def test_a_file_named_two_ways_is_reported_even_without_backticks(self):
        # The real case: table cells wrote `src/styles.css;` with no ticks while the steps own src/theme.css.
        found = pc.findings(PLAN % 'src/styles.css; body rule')
        self.assertEqual(len(found), 1)
        self.assertIn('`src/styles.css`', found[0])
        self.assertIn('`src/theme.css`', found[0])

    def test_a_backticked_name_is_reported_too(self):
        self.assertEqual(len(pc.findings(PLAN % '`src/styles.css`')), 1)

    def test_a_consistent_plan_has_no_findings(self):
        self.assertEqual(pc.findings(PLAN % 'src/theme.css body rule'), [])

    def test_build_output_driver_state_and_the_lockfile_are_never_reported(self):
        text = PLAN % '`dist/assets/index.js`, `test-results/a.json`, `.uncle/launch.json`, `node_modules/x/y.js`, `package-lock.json`'
        self.assertEqual(pc.findings(text), [])

    def test_commands_urls_globs_and_prose_are_not_file_names(self):
        text = PLAN % '`npm run build`, `src/*.js`, https://example.com/a/b.css, see src/ for details, `a, b`'
        self.assertEqual(pc.findings(text), [])

    def test_an_unowned_file_in_a_directory_the_plan_owns_files_in_is_reported(self):
        found = pc.findings(PLAN % 'src/helpers.js')
        self.assertEqual(len(found), 1)
        self.assertIn('no step owns it', found[0])

    def test_a_plan_with_no_owned_files_gives_nothing_to_compare_against(self):
        self.assertEqual(pc.findings('# Plan\n\nSee `src/a.js` and `src/b.js`.\n'), [])


class Prompts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.plan = self.dir / 'plan.md'
        self.plan.write_text(PLAN % 'src/styles.css; body rule')

    def test_the_stage_step_may_fix_and_is_told_what_the_driver_found(self):
        out = self.dir / 'prompt.md'
        stage.prepare(self.dir, self.plan, out)
        text = out.read_text()
        self.assertIn('Fix a contradiction yourself with Edit', text)
        self.assertIn('`src/styles.css` is mentioned but no step owns it', text)
        self.assertNotIn('report it and stop; do not claim completion. Do not rewrite the plan or its packets.', text)
        self.assertIn(stage.COMPLETE, text)

    def test_a_consistent_plan_adds_no_findings_section(self):
        self.plan.write_text(PLAN % 'src/theme.css')
        out = self.dir / 'prompt.md'
        stage.prepare(self.dir, self.plan, out)
        self.assertNotIn('The driver already found these', out.read_text())

    def test_the_repair_prompt_carries_the_first_reply_the_reason_and_what_is_still_found(self):
        (self.dir / 'stage-duties.jsonl').write_text(json.dumps(
            {'type': 'result', 'result': 'Which resolution do you want for the stylesheet name?'}) + '\n')
        out = self.dir / 'repair.md'
        stage.prepare_repair(self.dir, self.plan, out, 'stage step did not confirm consistency and file duties')
        text = out.read_text()
        self.assertIn('Which resolution do you want for the stylesheet name?', text)
        self.assertIn('did not confirm consistency', text)
        self.assertIn('The driver still finds', text)
        self.assertIn('Fix a contradiction yourself with Edit', text)
        self.assertIn(stage.COMPLETE, text)


if __name__ == '__main__':
    unittest.main()
