#!/usr/bin/env python3
"""The artifact graph: readiness, the source-approval rule, speculative adoption, and agreement with stagegate.sh."""
import importlib.util
from pathlib import Path
import re
import sys
import unittest

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))


def load(name):
    spec = importlib.util.spec_from_file_location(name, LIB / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


graph = load('driver_graph')
stages = load('driver_stages')
Node, Graph, GraphError, Ledger = graph.Node, graph.Graph, graph.GraphError, graph.Ledger


class GraphShape(unittest.TestCase):
    def test_a_cycle_is_refused(self):
        with self.assertRaises(GraphError):
            Graph([Node('a', inputs=('Y',), outputs=('X',)), Node('b', inputs=('X',), outputs=('Y',))])

    def test_an_input_nothing_produces_is_refused(self):
        with self.assertRaises(GraphError):
            Graph([Node('a', inputs=('MISSING',), outputs=('X',))])

    def test_two_producers_of_one_artifact_are_refused(self):
        with self.assertRaises(GraphError):
            Graph([Node('a', outputs=('X',)), Node('b', outputs=('X',))])

    def test_an_external_artifact_needs_no_producer(self):
        Graph([Node('a', inputs=('BRIEF',), outputs=('X',))], external=('BRIEF',))

    def test_order_puts_producers_first(self):
        g = Graph([Node('b', inputs=('X',), outputs=('Y',)), Node('a', outputs=('X',))])
        self.assertEqual(g.order(), ['a', 'b'])


class SourceApproval(unittest.TestCase):
    def test_source_writing_without_the_plan_approval_is_refused(self):
        with self.assertRaises(GraphError):
            Graph([Node('plan', outputs=('P',)), Node('build', inputs=('P',), outputs=('S',), writes_source=True)])

    def test_the_approval_may_sit_on_an_earlier_node(self):
        Graph([Node('plan', outputs=('P',), approvals=(graph.SOURCE_APPROVAL,)),
               Node('build', inputs=('P',), outputs=('S',), writes_source=True)])

    def test_a_source_writer_marked_speculative_still_waits_for_the_approval(self):
        g = Graph([Node('plan', outputs=('P',), approvals=(graph.SOURCE_APPROVAL,)),
                   Node('build', inputs=('P',), outputs=('S',), approvals=(graph.SOURCE_APPROVAL,),
                        writes_source=True, speculative_ok=True)])
        self.assertNotIn('build', g.ready({'P'}, set()))
        self.assertIn('build', g.ready({'P'}, {graph.SOURCE_APPROVAL}))

    def test_the_real_build_gates_implementation_on_the_updated_plan(self):
        g = stages.new_application()
        self.assertTrue(g.nodes['implement'].writes_source)
        self.assertIn(graph.SOURCE_APPROVAL, g.nodes['implement'].approvals)


class Readiness(unittest.TestCase):
    def setUp(self):
        self.g = stages.new_application()

    def test_only_requirements_can_start_from_the_brief(self):
        self.assertEqual(self.g.ready(set(), set()), ['requirements'])

    def test_a_speculative_node_may_run_before_its_approval_but_a_source_writer_may_not(self):
        have = {'REQUIREMENTS', 'PROJECT_PLAN', 'ADVERSARIAL_REVIEW', 'UPDATED_PROJECT_PLAN'}
        ready = self.g.ready(have, set())
        self.assertNotIn('implement', ready)
        self.assertNotIn('preflight', ready)

    def test_implementation_starts_once_the_updated_plan_is_approved(self):
        have = {'REQUIREMENTS', 'PROJECT_PLAN', 'ADVERSARIAL_REVIEW', 'UPDATED_PROJECT_PLAN'}
        self.assertIn('implement', self.g.ready(have, {'UPDATED_PROJECT_PLAN'}))

    def test_a_started_node_is_not_offered_again(self):
        self.assertEqual(self.g.ready(set(), set(), started={'requirements'}), [])

    def test_a_consumer_waits_for_every_input(self):
        have = {'REQUIREMENTS', 'PROJECT_PLAN'}
        self.assertNotIn('updated_plan', self.g.ready(have, {'ADVERSARIAL_REVIEW'}))


class CriticalPath(unittest.TestCase):
    def test_the_measured_build_is_a_single_chain_through_implementation(self):
        total, path = stages.new_application().critical_path(stages.MEASURED_SECONDS)
        self.assertEqual(path, ['requirements', 'project_plan', 'adversarial_review', 'updated_plan', 'implement',
                                'test_review', 'manual_checklist', 'execute_checklist', 'final_audit'])
        self.assertAlmostEqual(total, sum(stages.MEASURED_SECONDS[n] for n in path))

    def test_a_node_off_the_chain_does_not_lengthen_it(self):
        total, path = stages.new_application().critical_path(stages.MEASURED_SECONDS)
        self.assertNotIn('classify', path)
        self.assertLess(total, sum(stages.MEASURED_SECONDS.values()))

    def test_parallel_branches_count_once(self):
        g = Graph([Node('a', outputs=('A',)), Node('b', outputs=('B',)), Node('c', inputs=('A', 'B'), outputs=('C',))])
        self.assertEqual(g.critical_path({'a': 5, 'b': 9, 'c': 2}), (11, ['b', 'c']))


class Speculation(unittest.TestCase):
    def test_a_result_is_kept_while_its_inputs_are_unchanged(self):
        ledger = Ledger()
        ledger.record('review', {'PLAN': b'plan v1'})
        self.assertTrue(ledger.adoptable('review', {'PLAN': b'plan v1'}))

    def test_a_changed_input_discards_it(self):
        ledger = Ledger()
        ledger.record('review', {'PLAN': b'plan v1'})
        self.assertFalse(ledger.adoptable('review', {'PLAN': b'plan v2'}))

    def test_a_different_set_of_inputs_discards_it(self):
        ledger = Ledger()
        ledger.record('review', {'PLAN': b'p'})
        self.assertFalse(ledger.adoptable('review', {'PLAN': b'p', 'EXTRA': b'x'}))

    def test_an_unrecorded_node_is_never_adoptable(self):
        self.assertFalse(Ledger().adoptable('review', {}))

    def test_a_discarded_node_is_forgotten(self):
        ledger = Ledger()
        ledger.record('review', {'PLAN': b'p'})
        ledger.discard('review')
        self.assertFalse(ledger.adoptable('review', {'PLAN': b'p'}))


class AgreesWithTheBashDriver(unittest.TestCase):
    def test_the_declared_states_are_the_arms_of_stagegate(self):
        lines = (LIB.parent / 'stagegate.sh').read_text().split('\n')
        start = next(i for i, line in enumerate(lines) if line == 'while true; do')
        arms = []
        for line in lines[start:]:
            match = re.match(r'^        ([A-Z_]+)\)\s*$', line)
            if match:
                arms.append(match.group(1))
        self.assertEqual(arms, list(stages.STATES))

    def test_every_graph_node_names_a_state_of_the_driver(self):
        for name in stages.new_application().nodes:
            self.assertIn(name.upper(), stages.STATES, name)


if __name__ == '__main__':
    unittest.main()
