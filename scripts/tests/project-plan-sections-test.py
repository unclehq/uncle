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
import plan_model as pm
S = sections

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
        'design': section(1),
        'state': section(2),
        'domain': section(3),
        'components': section(4),
        'flow': section(5),
        'steps': section(12),
        'sequence': '## 12. Implementation order\nNONE\n',
        'decisions': '## Decision Record\n| D-1 | x |\n',
        'restrictions': '## Restriction Inventory\n| R-1 | y |\n',
        'limits': '## Restriction Inventory\nNONE\n',
        'bounds': '## Restriction Inventory\nNONE\n',
        'behaviors': section(6) + t('B', 'R-1=B-1,B-2; R-2=B-3'),
        'handling': ''.join(section(n) for n in (8, 9)),
        'checks': section(11) + t('M', 'R-2=M-1'),
        'invariants': section(7) + t('I', 'R-1=I-1'),
        'guards': section(7, 'Edge invariants.'),
        'tests': section(10) + t('T', 'R-1=T-1; R-2=T-2,T-3'),
        'defects': section(10, 'Defect injections.'),
        'obligations': section(10, 'Obligations.'),
        'commands': '## Verification commands\n```sh\nnpm test\n```\n',
        'closing': section(14) + section(15),
    }
    for name, text in files.items():
        (Path(directory) / (name + '.md')).write_text(text)
    return files


class Assemble(unittest.TestCase):
    def test_implementation_receives_the_outline_contract_in_the_final_plan(self):
        good_files(self.dir)
        (Path(self.dir) / 'outline.md').write_text(OUTLINE + '\nExact export: calculateTotal; display selector: result-panel\n')
        text = sections.assemble(self.dir)
        self.assertIn('Exact export: calculateTotal; display selector: result-panel', text)
        self.assertIn('### Binding planning outline', text)
        self.assertEqual(text.count('## Verification commands'), 1)

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


class Halves(unittest.TestCase):
    def test_two_halves_of_the_implementation_order_become_one_list_so_a_dependency_can_cross_them(self):
        joined = sections.join_steps([{'kind': 'steps', 'items': [{'number': 1}]}, {'kind': 'steps', 'items': [{'number': 2}]},
                                      {'kind': 'prose', 'text': 'x'}])
        self.assertEqual([b['kind'] for b in joined], ['steps', 'prose'])
        self.assertEqual([i['number'] for i in joined[0]['items']], [1, 2])


class Guards(unittest.TestCase):
    def test_the_two_invariant_workers_have_separate_id_ranges_and_both_report_i(self):
        low, high = sections.SPECIFIC['invariants'], sections.SPECIFIC['guards']
        self.assertIn('below `I-40`', low)
        self.assertIn('from `I-41`', high)
        self.assertEqual(sections.trace_letters('guards'), 'I')
        self.assertEqual(sections.WORKERS['invariants']['sections'], sections.WORKERS['guards']['sections'])
        order = list(sections.WORKERS)
        self.assertLess(order.index('invariants'), order.index('guards'))

    def test_the_blocks_prompt_carries_the_outline_so_no_worker_reads_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'outline.json').write_text(json.dumps({'stack': 'vite', 'components': [{'id': 'C-1'}]}, indent=2))
            text = sections.block_contract('tests', tmp)
            self.assertIn('{"stack":"vite","components":[{"id":"C-1"}]}', text)
            self.assertIn('do not read any file for it', text)
            self.assertNotIn('outline.json`', text)

    def test_without_an_outline_file_the_worker_is_still_told_to_read_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn('outline.json`', sections.block_contract('tests', tmp))


class Layout(unittest.TestCase):
    def test_one_short_outline_then_everything_else_at_once(self):
        self.assertEqual(sections.PHASES[0], ('outline',) + sections.EARLY)
        self.assertEqual(sections.EARLY, ('behaviors', 'handling', 'checks', 'decisions', 'restrictions', 'limits', 'bounds'))
        self.assertEqual(set(sections.PHASES[1]),
                         {'design', 'state', 'domain', 'components', 'flow', 'steps', 'sequence', 'invariants', 'guards', 'tests',
                          'defects', 'obligations', 'commands', 'closing'})
        self.assertEqual(len(sections.PHASES), 2)
        self.assertEqual(sections.FALLBACK, ('trace',))

    def test_every_section_has_an_owner_and_only_invariants_and_the_test_strategy_have_two(self):
        owned = [n for name, spec in sections.WORKERS.items() for n in spec['sections']]
        self.assertEqual(sections.WORKERS['limits']['extra'], sections.WORKERS['restrictions']['extra'])
        self.assertEqual(sorted(set(owned)), sorted(sections.TITLES))
        self.assertEqual(sorted(n for n in set(owned) if owned.count(n) > 1), [7, 10, 12])
        self.assertEqual(sections.SHARED, {7, 10, 12, 'Restriction Inventory'})
        self.assertEqual(sections.WRITERS['Restriction Inventory'], 3)
        extras = [e for spec in sections.WORKERS.values() for e in spec['extra']]
        self.assertEqual(sorted(set(extras)), sorted(sections.EXTRA))

    def test_early_workers_do_not_wait_for_the_outline_and_nobody_is_told_to_read_them(self):
        for name in sections.EARLY:
            self.assertIn(name, sections.PHASES[0])
            self.assertEqual(sections.readable(name, 'd'), [])
            self.assertIn('does not exist yet', sections.block_contract(name, '/d'))
            self.assertNotIn('outline.json', sections.block_contract(name, '/d'))
            self.assertIn('requirements interpretation', sections.contract(name, 'd') if name in sections.TRACE_KINDS else 'requirements interpretation')
        self.assertIn('requirements interpretation', sections.block_contract('behaviors', '/d'))

    def test_every_worker_is_given_a_length_and_the_restriction_thirds_have_their_own_id_ranges(self):
        for name in sections.WORKERS:
            if name != 'outline':
                self.assertIn('about %d words' % sections.WORD_CAP[name], sections.length_note(name), name)
        self.assertIn('below `R-20`', sections.SPECIFIC['restrictions'])
        self.assertIn('from `R-20`', sections.SPECIFIC['limits'])
        self.assertIn('from `R-40`', sections.SPECIFIC['bounds'])

    def test_the_outline_no_longer_carries_what_other_workers_write(self):
        for word in ('`decisions`: `id`', '`restrictions`: `id`', '`tests`: each runner'):
            self.assertNotIn(word, sections.OUTLINE_BLOCKS)
        self.assertIn('requirement_map', sections.OUTLINE_BLOCKS)

    def test_the_restriction_inventory_is_split_in_thirds_and_a_none_part_is_dropped(self):
        self.assertIn('first half', sections.SPECIFIC['steps'])
        self.assertIn('second half', sections.SPECIFIC['sequence'])
        with tempfile.TemporaryDirectory() as tmp:
            good_files(tmp)
            text = sections.assemble(tmp)
        self.assertNotIn('NONE', text)
        self.assertIn('| R-1 | y |', text)

    def test_phase_two_workers_read_the_outline_and_decisions_not_each_other(self):
        # The decisions worker fixes the choices (file names, tools, launch method) the other sections would otherwise
        # make independently, so it gates the second phase with the outline; no other early worker does.
        self.assertEqual(sections.GATE, ('outline', 'decisions'))
        for name in sections.PHASES[1]:
            self.assertEqual(sections.readable(name, 'd'), ['d/outline.md', 'd/decisions.md'], name)
        self.assertEqual(sections.readable('outline', 'd'), [])

    def test_a_block_worker_gets_the_decision_record_embedded_and_an_early_one_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'decisions.md').write_text('## Decision Record\n\n| D-1 | Stylesheet is src/theme.css |\n')
            Path(tmp, 'outline.json').write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'x', 'stack': 'Vite'}))
            self.assertIn('Stylesheet is src/theme.css', sections.block_contract('design', tmp))
            self.assertNotIn('Stylesheet is src/theme.css', sections.block_contract('behaviors', tmp))
            self.assertNotIn('decision record follows', sections.block_contract('design', tempfile.mkdtemp()))

    def test_the_fallback_worker_reads_everything(self):
        self.assertEqual(sections.readable('trace', 'd'),
                         ['d/%s.md' % name for phase in sections.PHASES for name in phase])

    def test_every_worker_shares_the_base_prompt_as_an_identical_prefix(self):
        base = 'BASE PROMPT\nwith lines\n'
        built = [sections.build_prompt(name, 'dir', base) for name in sections.WORKERS]
        self.assertTrue(all(text.split('BASE PROMPT')[0] == built[0].split('BASE PROMPT')[0] and base in text for text in built))
        self.assertEqual(len({text.split(base)[0] for text in built}), 1)

    def test_the_whole_plan_output_instruction_is_not_shown_to_a_section_worker(self):
        base = 'Intro\n\n## This is an investigation, not the final document\nWrite the plan to the file.\n\n## Compact first draft\nKeep.\n'
        for json_mode in (False, True):
            text = sections.build_prompt('outline', 'dir', base, json_mode)
            self.assertNotIn('Write the plan to the file', text)
            self.assertIn('## Compact first draft', text)

    def test_each_contract_names_exactly_its_own_headings(self):
        for name in sections.WORKERS:
            text = sections.contract(name, 'd')
            for row in sections.expected_headings(name):
                self.assertIn('`%s`' % row, text)
            own = set(sections.expected_headings(name))      # the test strategy is shared, so its heading is in two lanes
            others = [row for other in sections.WORKERS if other != name for row in sections.expected_headings(other)
                      if row not in own]
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
        self.assertNotIn('<!-- trace M:', sections.contract('behaviors', 'd'))
        self.assertIn('<!-- trace M:', sections.contract('checks', 'd'))
        self.assertNotIn('<!-- trace M:', sections.contract('handling', 'd'))

    def test_decisions_and_restrictions_are_separate_workers(self):
        self.assertEqual(sections.WORKERS['decisions']['extra'], ('Decision Record',))
        self.assertEqual(sections.WORKERS['restrictions']['extra'], ('Restriction Inventory',))

    def test_the_steps_worker_may_not_change_the_outlines_ownership(self):
        text = sections.contract('steps', 'd')
        self.assertIn('do not add, drop or move a file or a dependency', text)
        self.assertNotIn('Also write `.gitignore`', text)

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


class Blocks(unittest.TestCase):
    """Section workers that answer with typed blocks, and the outline as data."""

    def packet(self, name, sections, trace=None):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'project-plan-section-model-packet', 'sections': sections}
        if trace:
            packet['trace'] = trace
        return packet

    def behaviors(self):
        rows = [{'id': 'B-1', 'trigger': 't', 'result': 'r', 'failure': 'f', 'requirements': 'R-1'}]
        return [{'heading': '6. Observable behaviors', 'blocks': [{'kind': 'rows', 'row_kind': 'behavior', 'rows': rows}]}]

    def handling(self):
        return [{'heading': '8. Failure handling', 'blocks': [{'kind': 'prose', 'text': 'x'}]},
                {'heading': '9. Concurrency model', 'blocks': [{'kind': 'prose', 'text': 'y'}]}]

    def test_a_block_packet_renders_the_markdown_the_other_stages_read(self):
        text, sections = S.render_model_packet('behaviors', self.packet('behaviors', self.behaviors(),
                                                [{'kind': 'B', 'requirement': 'R-1', 'ids': ['B-1']}]))
        self.assertIn('## 6. Observable behaviors\n\n| ID | Trigger | Observable result | Failure behavior | Requirement IDs |', text)
        self.assertIn('| B-1 | t | r | f | R-1 |', text)
        self.assertIn('<!-- trace B: R-1=B-1 -->', text)
        self.assertEqual([s['heading'] for s in sections][0], '6. Observable behaviors')

    def test_render_packet_dispatches_on_the_kind(self):
        self.assertIn('## 8. Failure handling', S.render_packet('handling', self.packet('handling', self.handling())))

    def test_a_heading_outside_the_lane_a_duplicate_and_a_missing_section_are_refused(self):
        stolen = self.behaviors() + [{'heading': '7. Domain invariants', 'blocks': [{'kind': 'prose', 'text': 'x'}]}]
        with self.assertRaisesRegex(ValueError, 'not one of'):
            S.render_model_packet('behaviors', self.packet('behaviors', stolen))
        with self.assertRaisesRegex(ValueError, 'written twice'):
            S.render_model_packet('behaviors', self.packet('behaviors', self.behaviors() + self.behaviors()[:1]))
        with self.assertRaisesRegex(ValueError, 'missing sections'):
            S.render_model_packet('handling', self.packet('handling', self.handling()[:1]))

    def test_a_bad_block_is_refused_with_the_section_and_reason(self):
        bad = [{'heading': '6. Observable behaviors', 'blocks': [{'kind': 'rows', 'row_kind': 'behavior', 'rows': [{'trigger': 't'}]}]}]
        with self.assertRaisesRegex(ValueError, "section '6. Observable behaviors'.*needs an id"):
            S.render_model_packet('behaviors', self.packet('behaviors', bad))

    def test_the_block_contract_names_the_row_fields_the_lane_uses_and_the_outline_file(self):
        text = S.block_contract('behaviors', '/d')
        self.assertIn('`behavior` rows: id, trigger, result, failure, requirements (IDs, comma-separated), verification', text)
        self.assertIn('no Markdown syntax', text)
        self.assertIn('`/d/outline.json`', S.block_contract('tests', '/d'))
        self.assertNotIn('`behavior` rows: id, statement', text)

    def outline(self, **change):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'project-plan-outline-packet', 'stack': 's',
                  'components': [{'id': 'C-1', 'name': 'App', 'responsibility': 'root', 'files': 'src/App.jsx'}],
                  'steps': [{'number': '1', 'title': 'Scaffold', 'owns': 'a.js', 'depends_on': ''},
                            {'number': '2', 'title': 'Core', 'owns': 'b.js', 'depends_on': '1'}],
                  'decisions': [], 'restrictions': [], 'tests': [], 'requirement_map': [{'requirement': 'R-1', 'components': 'C-1, C-2'}]}
        packet.update(change)
        return packet

    def test_the_outline_renders_for_people_and_gives_the_requirement_map_as_data(self):
        text = S.render_packet('outline', self.outline())
        self.assertIn('2. Core -- Owns: `b.js` -- Depends on: 1', text)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'outline.json').write_text(json.dumps(self.outline()))
            self.assertEqual(S.outline_requirements(tmp), {'R-1': ['C-1', 'C-2']})

    def test_an_outline_with_a_file_owned_twice_or_a_repeated_step_is_refused(self):
        twice = self.outline(steps=[{'number': '1', 'title': 'a', 'owns': 'x.js', 'depends_on': ''},
                                    {'number': '2', 'title': 'b', 'owns': 'x.js', 'depends_on': ''}])
        with self.assertRaisesRegex(ValueError, 'owned by steps'):
            S.render_outline(twice)
        with self.assertRaisesRegex(ValueError, 'used twice'):
            S.render_outline(self.outline(steps=[{'number': '1', 'title': 'a', 'owns': 'x', 'depends_on': ''},
                                                 {'number': '1', 'title': 'b', 'owns': 'y', 'depends_on': ''}]))

    def test_the_model_is_assembled_from_the_typed_sections_and_section_13_is_built_from_trace_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'outline.json').write_text(json.dumps(self.outline()))
            for name in S.WORKERS:
                if name in ('outline', 'trace'):
                    continue
                spec = S.WORKERS[name]
                if name == 'behaviors':
                    sections = self.behaviors()
                else:
                    sections = [{'heading': t, 'blocks': [{'kind': 'prose', 'text': 'text for ' + t}]} for t in S.titles(name)]
                    if spec['commands']:
                        sections = [{'heading': 'Verification commands', 'blocks': [{'kind': 'code', 'lang': 'sh', 'text': 'npm test'}]}]
                trace = {'behaviors': [{'kind': 'B', 'requirement': 'R-1', 'ids': ['B-1']}],
                         'invariants': [{'kind': 'I', 'requirement': 'R-1', 'ids': ['I-1']}],
                         'tests': [{'kind': 'T', 'requirement': 'R-1', 'ids': ['T-1']}]}.get(name)
                text, typed = S.render_model_packet(name, self.packet(name, sections, trace))
                Path(tmp, name + '.md').write_text(text)
                Path(tmp, name + '.model.json').write_text(json.dumps({'worker': name, 'sections': typed}))
            model = S.assemble_model(tmp)
        self.assertEqual([s['id'] for s in model['sections']][:3], ['s1', 's2', 's3'])
        headings = [s['heading'] for s in model['sections']]
        self.assertIn('13. Requirement traceability', headings)
        self.assertNotIn('Verification commands', headings)            # the commands are a separate field of the plan
        last = [b for b in model['sections'][12]['blocks'] if b['kind'] == 'rows'][0]
        self.assertEqual((last['row_kind'], last['rows'][0]['behaviors'], last['rows'][0]['components']),
                         ('traceability', ['B-1'], ['C-1', 'C-2']))
        self.assertEqual(pm.validate(model)[0], [])

    def test_a_worker_without_typed_sections_means_the_markdown_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'no typed sections'):
                S.assemble_model(tmp)


class SharedSection(unittest.TestCase):
    """The test strategy is written by two workers; their parts are joined, the first worker's first."""

    def test_the_markdown_parts_are_joined_in_worker_order_under_one_heading(self):
        directory = tempfile.mkdtemp()
        good_files(directory)
        (Path(directory) / 'tests.md').write_text(section(10, 'THE TESTS') + '\n<!-- trace T: R-1=T-1 -->\n')
        (Path(directory) / 'defects.md').write_text(section(10, 'THE DEFECTS'))
        text = sections.assemble(directory)
        self.assertEqual(text.count('## 10. Automated-test strategy'), 1)
        self.assertLess(text.index('THE TESTS'), text.index('THE DEFECTS'))

    def test_a_third_writer_of_the_shared_section_is_still_refused(self):
        directory = tempfile.mkdtemp()
        good_files(directory)
        with open(Path(directory) / 'closing.md', 'a') as handle:
            handle.write(section(10))
        with self.assertRaisesRegex(ValueError, 'unexpected heading|twice'):
            sections.assemble(directory)

    def test_a_section_only_one_worker_may_write_is_still_refused_when_written_twice(self):
        directory = tempfile.mkdtemp()
        good_files(directory)
        with open(Path(directory) / 'handling.md', 'a') as handle:
            handle.write(section(8))
        with self.assertRaisesRegex(ValueError, 'twice'):
            sections.assemble(directory)

    def test_the_two_contracts_split_the_section_and_name_different_ids(self):
        tests, defects = sections.contract('tests', 'd'), sections.contract('defects', 'd')
        self.assertIn('another worker writes them', tests)
        self.assertIn('`DI-n`', defects)
        self.assertNotIn('`DI-n`', tests)
        self.assertIn('never a `T-n` ID', defects)

    def test_the_block_contract_marks_the_shared_section_and_limits_the_row_kinds(self):
        text = sections.block_contract('defects', '/d')
        self.assertIn('Section 10 is written by several workers', text)
        self.assertIn('`mutation` rows', text)
        self.assertNotIn('`obligation` rows', text)
        self.assertIn('`obligation` rows', sections.block_contract('obligations', '/d'))
        self.assertNotIn('`automated_test` rows', text)
        self.assertIn('`automated_test` rows', sections.block_contract('tests', '/d'))

    def test_the_model_joins_the_two_parts_blocks_in_order(self):
        directory = Path(tempfile.mkdtemp())
        (directory / 'outline.json').write_text(json.dumps({
            'schema': 'uncle.artifact/v1', 'kind': 'project-plan-outline-packet', 'stack': 's',
            'components': [{'id': 'C-1', 'name': 'a', 'responsibility': 'r', 'files': 'a.js'}],
            'steps': [{'number': '1', 'title': 't', 'owns': 'a.js', 'depends_on': ''}], 'decisions': [], 'restrictions': [],
            'tests': [], 'requirement_map': [{'requirement': 'R-1', 'components': 'C-1'}]}))
        for name in sections.WORKERS:
            if name in ('outline', 'trace'):
                continue
            titles = sections.titles(name)
            blocks = [{'kind': 'prose', 'text': 'text of ' + name}]
            rows = [{'heading': t, 'blocks': blocks} for t in titles]
            if sections.WORKERS[name]['commands']:
                rows = [{'heading': 'Verification commands', 'blocks': [{'kind': 'code', 'lang': 'sh', 'text': 'npm test'}]}]
            trace = {'behaviors': [{'kind': 'B', 'requirement': 'R-1', 'ids': ['B-1']}],
                     'invariants': [{'kind': 'I', 'requirement': 'R-1', 'ids': ['I-1']}],
                     'tests': [{'kind': 'T', 'requirement': 'R-1', 'ids': ['T-1']}],
                     'checks': [{'kind': 'M', 'requirement': 'R-1', 'ids': ['M-1']}]}.get(name)
            packet = {'schema': 'uncle.artifact/v1', 'kind': 'project-plan-section-model-packet', 'sections': rows}
            if trace:
                packet['trace'] = trace
            text, typed = sections.render_model_packet(name, packet)
            (directory / (name + '.md')).write_text(text)
            (directory / (name + '.model.json')).write_text(json.dumps({'worker': name, 'sections': typed}))
        model = sections.assemble_model(directory)
        ten = [s for s in model['sections'] if s['heading'].startswith('10.')]
        self.assertEqual(len(ten), 1)
        self.assertEqual([b['text'] for b in ten[0]['blocks']], ['text of tests', 'text of defects', 'text of obligations'])
        self.assertEqual([b['id'] for b in ten[0]['blocks']], ['%s.1' % ten[0]['id'], '%s.2' % ten[0]['id'], '%s.3' % ten[0]['id']])


if __name__ == '__main__':
    unittest.main()
