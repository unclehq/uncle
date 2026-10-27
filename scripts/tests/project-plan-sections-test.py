#!/usr/bin/env python3
"""A plan written in sections assembles into the one document the single pass would have written."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import project_plan_sections as sections

PLAN_CONTEXT = ROOT / 'scripts' / 'lib' / 'plan_context.py'

OUTLINE = '''## Stack
React, Vite, Vitest, Playwright

## Components
- C-1 Engine -- arithmetic; files: `src/calc.js`
- C-2 View -- screen; files: `src/App.jsx`

## Steps
1. Scaffold -- Owns: `package.json`
2. Engine -- Owns: `src/calc.js`

## Decisions
- D-1: plain reducer

## Restrictions
- R-1: no network -- DESIGN

## Tests
Vitest in `tests/unit/calc.test.js`

## Requirement map
R-1: C-1
R-2: C-1, C-2
'''


def section(number, body='Content.'):
    return '%s\n%s\n' % (sections.heading(number), body)


def good_files(directory, trace=True):
    t = (lambda kind, text: '\n<!-- trace %s: %s -->\n' % (kind, text)) if trace else (lambda kind, text: '')
    files = {
        'outline': OUTLINE,
        'design': ''.join(section(n) for n in (1, 2, 3, 4, 5)),
        'steps': section(12),
        'decisions': '## Decision Record\n| D-1 | x |\n',
        'restrictions': '## Restriction Inventory\n| R-1 | y |\n',
        'behaviors': ''.join(section(n) for n in (6, 8, 9, 11)) + t('B', 'R-1=B-1,B-2; R-2=B-3') + t('M', 'R-2=M-1'),
        'invariants': section(7) + t('I', 'R-1=I-1'),
        'tests': section(10) + t('T', 'R-1=T-1; R-2=T-2,T-3'),
        'commands': '## Verification commands\n```sh\nnpm test\n```\n',
        'closing': section(14) + section(15),
    }
    for name, text in files.items():
        (Path(directory) / (name + '.md')).write_text(text)
    return files


class Assemble(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_sections_are_ordered_by_number_with_commands_last(self):
        good_files(self.dir)
        text = sections.assemble(self.dir)
        self.assertTrue(text.startswith('# Project plan\n'))
        positions = [text.index(sections.heading(n)) for n in range(1, 16)]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], text.index('## Decision Record'))
        self.assertLess(text.index('## Restriction Inventory'), text.index('## Verification commands'))
        self.assertEqual(text.count('## Verification commands'), 1)

    def test_a_missing_file_or_section_is_refused(self):
        good_files(self.dir)
        (Path(self.dir) / 'closing.md').unlink()
        with self.assertRaisesRegex(ValueError, 'closing.md'):
            sections.assemble(self.dir)
        (Path(self.dir) / 'closing.md').write_text('')
        with self.assertRaisesRegex(ValueError, 'missing'):
            sections.assemble(self.dir)

    def test_a_worker_may_not_write_anothers_section(self):
        good_files(self.dir)
        with open(Path(self.dir) / 'closing.md', 'a') as handle:
            handle.write(section(7))
        with self.assertRaisesRegex(ValueError, 'unexpected heading'):
            sections.assemble(self.dir)

    def log(self, *events):
        path = Path(self.dir) / 'worker.jsonl'
        path.write_text('\n'.join(json.dumps(e) for e in events) + '\n')
        return path

    def test_a_worker_that_answered_in_chat_is_recovered(self):
        out = Path(self.dir) / 'commands.md'
        text = '## Verification commands\n\n```sh\nnpm test\n```'
        sections.recover(self.log({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}},
                                  {'type': 'result', 'result': text}), out)
        self.assertEqual(out.read_text(), text + '\n')

    def test_a_fenced_answer_is_unwrapped_and_the_last_assistant_text_is_the_fallback(self):
        out = Path(self.dir) / 'x.md'
        sections.recover(self.log({'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': '```markdown\n## 14. Explicit non-goals\nNone.\n```'}]}}), out)
        self.assertTrue(out.read_text().startswith('## 14.'))
        self.assertNotIn('```markdown', out.read_text())

    def test_commentary_is_not_recovered_as_a_section(self):
        out = Path(self.dir) / 'x.md'
        for text in ('I wrote the file.', 'Here you go:\n## 7. Domain invariants\nx'):
            with self.assertRaisesRegex(ValueError, 'nothing to recover'):
                sections.recover(self.log({'type': 'result', 'result': text}), out)
        self.assertFalse(out.exists())
        with self.assertRaises(ValueError):
            sections.recover(Path(self.dir) / 'missing.jsonl', out)

    def test_a_recovered_section_is_still_held_to_its_lane(self):
        good_files(self.dir)
        text = '## 7. Domain invariants\nstolen'
        sections.recover(self.log({'type': 'result', 'result': text}), Path(self.dir) / 'closing.md')
        with self.assertRaisesRegex(ValueError, 'unexpected heading'):
            sections.assemble(self.dir)

    def test_a_heading_no_section_owns_stays_inside_the_section_above_it(self):
        good_files(self.dir)
        with open(Path(self.dir) / 'tests.md', 'a') as handle:
            handle.write('\n## Defect injections (`tests/mutations.mjs`)\nbreak the keymap\n\n## Protected verification paths\n`tests/a.js`\n')
        plan = sections.assemble(self.dir)
        self.assertNotIn('\n## Defect injections', plan)
        self.assertNotIn('\n## Protected verification paths', plan)
        tests_section = plan.split('## 10.')[1].split('\n## ')[0]
        self.assertIn('### Defect injections (`tests/mutations.mjs`)\nbreak the keymap', tests_section)
        self.assertIn('### Protected verification paths', tests_section)

    def test_a_section_written_twice_or_empty_is_refused(self):
        good_files(self.dir)
        with open(Path(self.dir) / 'behaviors.md', 'a') as handle:
            handle.write(section(6))
        with self.assertRaisesRegex(ValueError, 'unexpected heading|twice'):
            sections.assemble(self.dir)
        good_files(self.dir)
        (Path(self.dir) / 'closing.md').write_text(sections.heading(14) + '\n\n' + section(15))
        with self.assertRaisesRegex(ValueError, 'empty'):
            sections.assemble(self.dir)

    def test_a_worker_may_not_write_the_verification_commands_unless_assigned(self):
        good_files(self.dir)
        with open(Path(self.dir) / 'design.md', 'a') as handle:
            handle.write('## Verification commands\n```sh\nx\n```\n')
        with self.assertRaisesRegex(ValueError, 'unexpected heading'):
            sections.assemble(self.dir)

    def test_headings_inside_code_fences_are_not_sections(self):
        good_files(self.dir)
        (Path(self.dir) / 'commands.md').write_text('## Verification commands\n```sh\n## Verification commands\nnpm test\n```\n')
        found = [line for line, _ in sections.blocks(sections.assemble(self.dir)) if line == '## Verification commands']
        self.assertEqual(len(found), 1)

    def test_the_assembled_plan_exports_like_a_single_pass_plan(self):
        good_files(self.dir)
        plan = Path(self.dir) / 'plan.md'
        plan.write_text(sections.assemble(self.dir))
        result = subprocess.run([sys.executable, '-B', str(PLAN_CONTEXT), 'export-project-plan', str(plan), self.dir],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_optional_parallel_groups_section_is_kept_before_the_commands(self):
        good_files(self.dir)
        (Path(self.dir) / 'commands.md').write_text(
            '## Parallel verification groups\n```text\n2 3\n```\n\n## Verification commands\n```sh\na\nb\nc\n```\n')
        plan = sections.assemble(self.dir)
        self.assertLess(plan.index('## Parallel verification groups'), plan.index('## Verification commands'))
        self.assertIn('## Parallel verification groups', plan.split('## Verification commands')[0])

    def test_the_groups_section_may_be_left_out(self):
        good_files(self.dir)
        self.assertNotIn('Parallel verification groups', sections.assemble(self.dir))

    def test_no_other_worker_may_write_the_groups_or_the_commands(self):
        good_files(self.dir)
        with open(Path(self.dir) / 'tests.md', 'a') as handle:
            handle.write('## Parallel verification groups\n```text\n2 3\n```\n')
        with self.assertRaisesRegex(ValueError, 'unexpected heading'):
            sections.assemble(self.dir)


class Layout(unittest.TestCase):
    def test_one_short_outline_then_everything_else_at_once(self):
        self.assertEqual(sections.PHASES[0], ('outline',))
        self.assertEqual(set(sections.PHASES[1]),
                         {'design', 'steps', 'decisions', 'restrictions', 'behaviors', 'invariants', 'tests', 'commands', 'closing'})
        self.assertEqual(len(sections.PHASES), 2)
        self.assertEqual(sections.FALLBACK, ('trace',))

    def test_every_section_has_exactly_one_owner(self):
        owned = [n for name, spec in sections.WORKERS.items() for n in spec['sections']]
        self.assertEqual(sorted(owned), sorted(sections.TITLES))
        extras = [e for spec in sections.WORKERS.values() for e in spec['extra']]
        self.assertEqual(sorted(extras), sorted(sections.EXTRA))

    def test_phase_two_workers_read_only_the_outline_not_each_other(self):
        for name in sections.PHASES[1]:
            self.assertEqual(sections.readable(name, 'd'), ['d/outline.md'], name)
        self.assertEqual(sections.readable('outline', 'd'), [])

    def test_the_fallback_worker_reads_everything(self):
        self.assertEqual(sections.readable('trace', 'd'),
                         ['d/%s.md' % name for phase in sections.PHASES for name in phase])

    def test_every_worker_shares_the_base_prompt_as_an_identical_prefix(self):
        base = 'BASE PROMPT\nwith lines\n'
        self.assertTrue(all(sections.build_prompt(name, 'dir', base).startswith(base) for name in sections.WORKERS))

    def test_each_contract_names_exactly_its_own_headings(self):
        for name in sections.WORKERS:
            text = sections.contract(name, 'd')
            for row in sections.expected_headings(name):
                self.assertIn('`%s`' % row, text)
            others = [row for other in sections.WORKERS if other != name for row in sections.expected_headings(other)]
            for row in others:
                self.assertNotIn('- `%s`' % row, text)

    def test_only_the_commands_worker_owns_the_commands(self):
        for name in sections.WORKERS:
            text = sections.contract(name, 'd')
            self.assertEqual('Do not write a `## Verification commands` heading' in text, name != 'commands')

    def test_the_outline_is_short_exact_and_decides_everything_once(self):
        text = sections.contract('outline', 'd')
        for heading in sections.OUTLINE_HEADINGS:
            self.assertIn('`## %s`' % heading, text)
        self.assertIn('about 45 lines', text)
        self.assertIn('Decide everything here once', text)
        self.assertIn('Requirement map', text)

    def test_the_workers_that_trace_are_told_the_line_format(self):
        for name, examples in sections.TRACE_EXAMPLES.items():
            text = sections.contract(name, 'd')
            for example in examples:
                self.assertIn(example, text, name)
        self.assertNotIn('<!-- trace', sections.contract('design', 'd'))

    def test_each_worker_is_shown_its_own_kind_not_a_shared_example(self):
        # noinit: one `trace B` example was copied by the invariants and tests workers alike
        self.assertIn('<!-- trace T:', sections.contract('tests', 'd'))
        self.assertNotIn('<!-- trace B:', sections.contract('tests', 'd'))
        self.assertIn('<!-- trace I:', sections.contract('invariants', 'd'))
        self.assertNotIn('<!-- trace B:', sections.contract('invariants', 'd'))
        self.assertIn('<!-- trace B:', sections.contract('behaviors', 'd'))
        self.assertIn('<!-- trace M:', sections.contract('behaviors', 'd'))

    def test_decisions_and_restrictions_are_separate_workers(self):
        self.assertEqual(sections.WORKERS['decisions']['extra'], ('Decision Record',))
        self.assertEqual(sections.WORKERS['restrictions']['extra'], ('Restriction Inventory',))

    def test_the_steps_worker_may_not_change_the_outlines_ownership(self):
        text = sections.contract('steps', 'd')
        self.assertIn('do not add, drop or move a file or a dependency', text)
        self.assertIn('.gitignore', text)

    def test_the_invariant_worker_does_not_need_the_test_ids_it_cannot_see(self):
        text = sections.contract('invariants', 'd')
        self.assertIn('see 10', text)
        self.assertNotIn('d/tests.md', text)


class Trace(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        good_files(self.dir)

    def test_section_13_is_built_from_the_workers_own_lines_and_the_outlines_component_map(self):
        text = sections.assemble(self.dir)
        table = text[text.index(sections.heading(13)):text.index(sections.heading(14))]
        self.assertIn('| Requirement | Behavior | Invariant | Component | Automated test | Manual check |', table)
        self.assertIn('| R-1 | B-1, B-2 | I-1 | C-1 | T-1 | none |', table)
        self.assertIn('| R-2 | B-3 | none | C-1, C-2 | T-2, T-3 | M-1 |', table)

    def test_the_trace_lines_do_not_appear_in_the_plan(self):
        self.assertNotIn('<!-- trace', sections.assemble(self.dir))

    def test_requirements_are_sorted_naturally(self):
        files = (Path(self.dir) / 'tests.md')
        files.write_text(section(10) + '\n<!-- trace T: R-10=T-9; R-2=T-8; R-1=T-1 -->\n')
        (Path(self.dir) / 'outline.md').write_text(OUTLINE + 'R-10: C-2\n')
        table = sections.trace_section(self.dir)
        order = [line.split('|')[1].strip() for line in table.splitlines()[2:]]
        self.assertEqual(order, ['R-1', 'R-2', 'R-10'])

    def test_it_is_ready_only_when_behaviors_tests_and_components_mapped_something(self):
        self.assertTrue(sections.trace_ready(self.dir))
        for name, kind in (('behaviors', 'B'), ('tests', 'T')):
            good_files(self.dir)
            path = Path(self.dir) / (name + '.md')
            path.write_text(sections.trace_lines(path.read_text())[1].replace('<!-- trace %s' % kind, ''))
            data, _ = sections.trace_lines(path.read_text())
            self.assertNotIn(kind, data)
            self.assertFalse(sections.trace_ready(self.dir), name)
        good_files(self.dir)
        (Path(self.dir) / 'outline.md').write_text(OUTLINE.replace('R-1: C-1', '').replace('R-2: C-1, C-2', ''))
        self.assertFalse(sections.trace_ready(self.dir))

    def test_an_unmapped_plan_needs_the_fallback_worker_and_accepts_its_section(self):
        good_files(self.dir, trace=False)
        self.assertFalse(sections.trace_ready(self.dir))
        with self.assertRaisesRegex(ValueError, 'section 13 cannot be built'):
            sections.assemble(self.dir)
        (Path(self.dir) / 'trace.md').write_text(section(13, '| R-1 | B-1 |'))
        text = sections.assemble(self.dir)
        self.assertIn('| R-1 | B-1 |', text)

    def test_malformed_trace_lines_are_ignored(self):
        data, rest = sections.trace_lines('x\n<!-- trace B: nonsense -->\n<!-- trace B: R-1= -->\n<!-- trace B: R-1=B-1 -->\n')
        self.assertEqual(data, {'B': {'R-1': ['B-1']}})
        self.assertNotIn('trace', rest)

    def test_the_outline_map_accepts_the_usual_spellings(self):
        (Path(self.dir) / 'outline.md').write_text(
            '## Requirement map\n- R-1: C-1\n* `R-2` -> C-2, C-3\nR-3 = C-4\nR-4 → C-5\nprose without an id\n')
        self.assertEqual(sections.outline_requirements(self.dir),
                         {'R-1': ['C-1'], 'R-2': ['C-2', 'C-3'], 'R-3': ['C-4'], 'R-4': ['C-5']})

    def test_the_assembled_plan_still_exports_and_validates(self):
        plan = Path(self.dir) / 'plan.md'
        plan.write_text(sections.assemble(self.dir))
        for command in ('export-project-plan', 'plan-unprotected'):
            result = subprocess.run([sys.executable, '-B', str(PLAN_CONTEXT), command, str(plan), self.dir],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, command + ': ' + result.stderr)

    def test_the_command_line_reports_readiness(self):
        script = str(ROOT / 'scripts' / 'lib' / 'project_plan_sections.py')
        ready = subprocess.run([sys.executable, '-B', script, 'trace-ready', self.dir])
        self.assertEqual(ready.returncode, 0)
        good_files(self.dir, trace=False)
        not_ready = subprocess.run([sys.executable, '-B', script, 'trace-ready', self.dir])
        self.assertEqual(not_ready.returncode, 1)

    def test_the_column_comes_from_the_ids_not_from_the_letter_the_worker_wrote(self):
        """The invariants and tests workers copied `trace B`; their IDs still say I and T."""
        (Path(self.dir) / 'invariants.md').write_text(section(7) + '\n<!-- trace B: R-1=I-1,I-2 -->\n')
        (Path(self.dir) / 'tests.md').write_text(section(10) + '\n<!-- trace B: R-1=T-1; R-2=T-2 -->\n')
        data = sections.merged_trace(self.dir)
        self.assertEqual(data['I']['R-1'], ['I-1', 'I-2'])
        self.assertEqual(data['T'], {'R-1': ['T-1'], 'R-2': ['T-2']})
        self.assertTrue(sections.trace_ready(self.dir))
        table = sections.trace_section(self.dir)
        self.assertIn('| R-1 | B-1, B-2 | I-1, I-2 | C-1 | T-1 | none |', table)

    def test_lines_that_do_not_map_a_requirement_are_not_rows(self):
        """`B-1=I-1` and `D-1=T-3` (seen live) map something else; only the outline's requirements are rows."""
        (Path(self.dir) / 'tests.md').write_text(
            section(10) + '\n<!-- trace T: R-1=T-1; B-1=T-1,T-3; D-2=T-2 -->\n')
        data = sections.merged_trace(self.dir)
        self.assertEqual(data['T'], {'R-1': ['T-1']})
        rows = [line.split('|')[1].strip() for line in sections.trace_section(self.dir).splitlines()[2:]]
        self.assertEqual(rows, ['R-1', 'R-2'])

    def test_ids_that_are_not_a_column_are_ignored(self):
        (Path(self.dir) / 'tests.md').write_text(section(10) + '\n<!-- trace T: R-1=T-1,AO-3,D-1,S-2 -->\n')
        self.assertEqual(sections.merged_trace(self.dir)['T'], {'R-1': ['T-1']})

    def test_without_an_outline_map_nothing_is_ready_so_the_fallback_runs(self):
        (Path(self.dir) / 'outline.md').write_text('## Stack\nx\n')
        self.assertFalse(sections.trace_ready(self.dir))

    def test_the_real_noinit_run_that_needed_the_fallback_now_builds_locally(self):
        real = Path.home() / 'src/noinit/.uncle/workflow/project-plan-sections'
        if not (real / 'tests.md').exists() or 'trace B:' not in (real / 'tests.md').read_text():
            self.skipTest('the noinit run with the mislabelled trace lines is not present')
        self.assertTrue(sections.trace_ready(real))
        self.assertIn('| R-4 | B-9 | I-7, I-8 | C-2, C-3 | T-2, T-4 | M-2 |', sections.trace_section(real))


if __name__ == '__main__':
    unittest.main()
