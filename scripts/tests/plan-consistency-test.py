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


class ArithmeticLiterals(unittest.TestCase):
    """Runs 17, 19 and 30: a digit string worked out by hand in the plan was wrong, and every test and checklist row that copied it failed.
    A product of two whole numbers and the scientific-notation value stated for it are checked against the exact product."""

    def found(self, text):
        return pc.literal_findings(text)

    def test_run_30s_typo_is_found_and_the_correct_digits_are_given(self):
        out = self.found('| T-2 | 99999999999*99999999999 formats exactly as 9.99999999998e+21 | R-5 |')
        self.assertEqual(len(out), 1)
        self.assertIn('9999999999800000000001', out[0])
        self.assertIn('9.99999999980e+21', out[0])

    def test_run_19s_truncated_literal_is_found(self):
        out = self.found('9999999999*9999999999= displays exactly 9.99999999e+19 on the display')
        self.assertEqual(len(out), 1)
        self.assertIn('1.00000000e+20', out[0])

    def test_the_right_literal_passes_whatever_trailing_zeros_it_drops(self):
        for literal in ('9.9999999998e+21', '9.99999999980e+21', '9.999999999800e+21'):
            with self.subTest(literal=literal):
                self.assertEqual(self.found('99999999999*99999999999 shows %s' % literal), [])

    def test_a_correctly_rounded_shorter_literal_passes(self):
        self.assertEqual(self.found('99999999999*99999999999 shows 1.0e+22 at two digits'), [])

    def test_the_multiplication_sign_and_x_work_too(self):
        self.assertEqual(len(self.found('99999999999\u00d799999999999 shows 9.99999999998e+21')), 1)
        self.assertEqual(len(self.found('99999999999 x 99999999999 shows 9.99999999998e+21')), 1)

    def test_a_later_value_on_the_same_line_belongs_to_something_else(self):
        line = '999999999999*999999999999= gives 9.99999999998e+23; 1/3000000000= gives 3.33333333333e-10; a 13th digit is ignored'
        self.assertEqual(self.found(line), [])

    def test_a_table_cell_boundary_ends_the_clause(self):
        self.assertEqual(self.found('| 99999999999*99999999999 | Display | 3.33333333333e-10 |'), [])

    def test_another_long_number_between_them_ends_the_clause(self):
        self.assertEqual(self.found('99999999999*99999999999 is computed from 1234567 inputs then 7.5e+3'), [])

    def test_each_product_is_paired_with_its_own_value(self):
        out = self.found('99999999999*99999999999 shows 9.9999999998e+21 and 9999999999*9999999999 shows 9.99999999e+19')
        self.assertEqual(len(out), 1)
        self.assertIn('9999999999*9999999999', out[0])

    def test_text_with_no_product_or_no_value_is_left_alone(self):
        self.assertEqual(self.found('The display shows 9.99e+21 for large results.'), [])
        self.assertEqual(self.found('99999999999*99999999999 overflows the display'), [])
        self.assertEqual(self.found('5*3 shows 1.5e+1'), [])    # one-digit factors are not long arithmetic

    def test_a_semicolon_ends_the_clause_even_when_the_product_has_no_value_of_its_own(self):
        line = '99999999999*99999999999 overflows the display; 1/3= gives 3.33333333333e-1'
        self.assertEqual(self.found(line), [])

    def test_one_digit_factors_are_not_checked_even_when_the_value_is_wrong(self):
        self.assertEqual(self.found('5*3 shows 2.5e+1'), [])

    def test_a_truncated_literal_is_wrong_even_though_a_longer_rounding_would_look_close(self):
        self.assertEqual(len(self.found('9999999999*9999999999 shows 9.99999999e+19')), 1)

    def test_a_literal_with_more_digits_than_the_product_has_is_wrong_when_a_digit_differs(self):
        self.assertEqual(len(self.found('1234567*1234567 shows 1.524155677490e+12')), 1)
        self.assertEqual(self.found('1234567*1234567 shows 1.524155677489e+12'), [])

    def test_a_shorter_literal_is_judged_at_its_own_precision(self):
        self.assertEqual(self.found('1234567*1234567 shows 1.52415568e+12'), [])      # correctly rounded to 9 digits
        self.assertEqual(len(self.found('1234567*1234567 shows 1.52415569e+12')), 1)  # off by one in the last digit

    def test_it_reaches_the_stage_prompt_through_known_inconsistencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / 'plan.md'
            plan.write_text(PLAN + '\n| T-2 | 99999999999*99999999999 formats exactly as 9.99999999998e+21 |\n')
            known = stage.known_inconsistencies(plan)
            self.assertTrue(any('9999999999800000000001' in line for line in known), known)
            out = Path(tmp) / 'prompt.md'
            stage.prepare(tmp, plan, out)
            self.assertIn('9999999999800000000001', out.read_text())

    def test_the_command_line_prints_it(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / 'plan.md'
            plan.write_text('| T-2 | 99999999999*99999999999 formats exactly as 9.99999999998e+21 |\n')
            done = subprocess.run([sys.executable, '-B', str(Path(pc.__file__)), 'check', str(plan)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0)
            self.assertIn('9.99999999980e+21', done.stdout)


if __name__ == '__main__':
    unittest.main()
