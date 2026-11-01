"""A small application's project plan is written by fewer workers: the same headings, validated the same way, fewer calls."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'lib'))
sys.path.insert(0, str(HERE))
fixtures = importlib.import_module('project-plan-sections-test')


def load(merge=None, cls=None):
    """project_plan_sections as a run would import it: in a project directory, with the class the classifier recorded."""
    directory = tempfile.mkdtemp()
    os.chdir(directory)
    Path('.uncle/workflow').mkdir(parents=True)
    os.environ.pop('WORKFLOW_PLAN_MERGE', None)
    if merge is not None:
        os.environ['WORKFLOW_PLAN_MERGE'] = merge
    if cls:
        Path('.uncle/workflow/change-class.json').write_text(json.dumps({'class': cls, 'family': 'app'}))
    for name in ('project_plan_sections', 'change_class'):
        sys.modules.pop(name, None)
    return importlib.import_module('project_plan_sections'), directory


class Merged(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.addCleanup(os.chdir, self.old)
        self.addCleanup(os.environ.pop, 'WORKFLOW_PLAN_MERGE', None)

    def test_the_class_switches_it_on_and_standard_and_the_opt_out_keep_the_full_layout(self):
        full, _ = load()
        merged, _ = load(cls='small')
        self.assertEqual(len(load(cls='standard')[0].WORKERS), len(full.WORKERS))
        self.assertEqual(len(load('0', cls='small')[0].WORKERS), len(full.WORKERS))
        self.assertEqual(len(load('1')[0].WORKERS), len(merged.WORKERS))
        self.assertLess(len(merged.WORKERS), len(full.WORKERS))
        self.assertEqual(sum(len(p) for p in merged.PHASES), 13)
        self.assertEqual(sum(len(p) for p in full.PHASES), 22)

    def test_every_section_still_has_exactly_one_owner_and_nothing_is_shared(self):
        m, _ = load('1')
        owners = {}
        for name, spec in m.WORKERS.items():
            if name == 'trace':
                continue
            for item in list(spec['sections']) + list(spec['extra']):
                owners.setdefault(item, []).append(name)
        for number in list(range(1, 3)) + [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15]:
            self.assertEqual(len(owners.get(number, [])), 1, number)
        self.assertEqual(len(owners['Decision Record']), 1)
        self.assertEqual(len(owners['Restriction Inventory']), 1)
        self.assertEqual(m.SHARED, set())

    def test_the_phases_keep_the_outline_first_and_the_decisions_gate(self):
        m, _ = load('1')
        self.assertEqual(m.PHASES[0][0], 'outline')
        self.assertTrue(set(m.GATE) <= set(m.PHASES[0]))
        self.assertEqual(set(m.EARLY), set(m.PHASES[0]) - {'outline'})
        self.assertIn('commands', m.PHASES[1])
        self.assertIn('closing', m.PHASES[1])
        for gone in ('design', 'state', 'domain', 'flow', 'sequence', 'guards', 'defects', 'obligations', 'limits', 'bounds'):
            self.assertNotIn(gone, m.WORKERS)

    def test_the_trace_kinds_follow_the_merge(self):
        m, _ = load('1')
        self.assertEqual(m.TRACE_KINDS, {'behaviors': 'B', 'checks': 'M', 'invariants': 'I', 'tests': 'T'})

    def test_the_merged_test_worker_writes_every_row_kind_of_section_10(self):
        m, _ = load('1')
        self.assertEqual(m.row_kinds_of('tests'), ['automated_test', 'mutation', 'obligation'])
        self.assertTrue(m.allows_steps('steps'))

    def test_each_merged_contract_names_exactly_its_own_headings(self):
        m, directory = load('1')
        for name in [w for phase in m.PHASES for w in phase if w != 'outline']:
            text = m.block_contract(name, directory)
            listed = []
            capture = False
            for line in text.splitlines():
                if line.startswith('Write exactly these headings'):
                    capture = True
                    continue
                if capture:
                    if line.startswith('- `'):
                        listed.append(line[3:-1])
                    elif listed and not line.startswith('- `'):
                        break
            self.assertEqual(listed, m.titles(name), name)

    def test_a_merged_prompt_does_not_say_its_own_sections_are_written_by_someone_else(self):
        m, directory = load('1')
        core = m.contract('core', directory)
        self.assertIn('architecture (section 1)', core)
        self.assertNotIn('is written beside you by another worker: do not write or restate the state', core)
        self.assertIn('Whole automated-test strategy'.lower(), m.contract('tests', directory).lower())
        self.assertNotIn('another worker writes them', m.contract('tests', directory))
        self.assertNotIn('Another worker writes the second half', m.contract('steps', directory))

    def test_the_merged_word_caps_are_the_sum_of_what_they_replace(self):
        full, _ = load('0')
        m, _ = load('1')
        for name, members in m.MERGES.items():
            self.assertEqual(m.WORD_CAP[name], sum(full.WORD_CAP[x] for x in members), name)

    def test_a_plan_assembled_from_merged_workers_has_every_heading_in_order(self):
        m, directory = load('1')
        scratch = tempfile.mkdtemp()
        files = fixtures.good_files(scratch)
        out = Path(directory) / 'parts'
        out.mkdir()
        joined = lambda *names: ''.join(files[n] for n in names)
        # what the merged workers would write: one file per merged worker, its sections whole
        parts = {'outline': files['outline'], 'components': files['components'], 'decisions': files['decisions'],
                 'restrictions': files['restrictions'], 'behaviors': files['behaviors'], 'handling': files['handling'],
                 'checks': files['checks'], 'commands': files['commands'], 'closing': files['closing'],
                 'core': joined('design', 'state', 'domain', 'flow'), 'steps': files['steps'],
                 'invariants': files['invariants'], 'tests': files['tests']}
        self.assertEqual(set(parts), {w for phase in m.PHASES for w in phase})
        for name, text in parts.items():
            (out / (name + '.md')).write_text(text)
        plan = m.assemble(str(out))
        positions = [plan.index(m.heading(n)) for n in range(1, 16)]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(plan.count('## Verification commands'), 1)
        self.assertEqual(plan.count(m.heading(7)), 1)
        self.assertEqual(plan.count(m.heading(10)), 1)

    def test_a_merged_worker_may_not_write_another_workers_section(self):
        m, directory = load('1')
        scratch = tempfile.mkdtemp()
        files = fixtures.good_files(scratch)
        out = Path(directory) / 'parts'
        out.mkdir()
        for name in [w for phase in m.PHASES for w in phase]:
            text = {'core': ''.join(files[n] for n in ('design', 'state', 'domain', 'flow'))}.get(name, files.get(name, ''))
            (out / (name + '.md')).write_text(text)
        (out / 'core.md').write_text((out / 'core.md').read_text() + fixtures.section(4))     # the components section is not core's
        with self.assertRaises(ValueError):
            m.assemble(str(out))


class MergedTypedBlocks(unittest.TestCase):
    """The default delivery mode: typed blocks per worker, assembled into the plan model and validated by plan_model."""

    def setUp(self):
        self.old = os.getcwd()
        self.addCleanup(os.chdir, self.old)
        self.addCleanup(os.environ.pop, 'WORKFLOW_PLAN_MERGE', None)
        self.saved = (fixtures.S, fixtures.sections)
        self.addCleanup(lambda: setattr(fixtures, 'S', self.saved[0]))
        self.addCleanup(lambda: setattr(fixtures, 'sections', self.saved[1]))

    def run_blocks_case(self, name):
        merged, _ = load('1')
        fixtures.S = fixtures.sections = merged
        result = unittest.TestResult()
        fixtures.Blocks(name).run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

    def test_the_model_assembles_and_validates_from_merged_typed_sections(self):
        self.run_blocks_case('test_the_model_is_assembled_from_the_typed_sections_and_section_13_is_built_from_trace_data')

    def test_a_merged_worker_that_lacks_typed_sections_means_the_markdown_assembly(self):
        self.run_blocks_case('test_a_worker_without_typed_sections_means_the_markdown_assembly')


if __name__ == '__main__':
    unittest.main()
