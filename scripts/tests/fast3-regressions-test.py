#!/usr/bin/env python3
"""Run-22 regressions: isolated probes, bounded writers, and valid row fields."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent as agent
import self_hosted
import self_hosted_http as transport
import worker_schemas

spec = importlib.util.spec_from_file_location('schema_order_fixture', ROOT / 'scripts/tests/updated-plan-schema-order-test.py')
order = importlib.util.module_from_spec(spec)
spec.loader.exec_module(order)


class PreflightIsolation(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / 'tests').mkdir()
        (self.root / 'tests/app.spec.js').write_text('protected test\n')
        (self.root / 'package.json').write_text('{}\n')
        (self.root / 'package-lock.json').write_text('lock\n')
        (self.root / 'untracked.txt').write_text('uncommitted input\n')
        env = patch.dict(os.environ, {'UNCLE_CONFIG': str(self.root / 'missing-config'),
                         'UNCLE_PROJECT_ROOT': str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def policy(self, lens='browser'):
        with patch.dict(os.environ, UNCLE_STATUS_STAGE='preflight-worker-' + lens):
            _, policy, _, _, _, _ = self_hosted._http_setup(
                'agent', {}, 'Probe prerequisites.', self.root, True, 'preflight-worker-packet')
        self.addCleanup(policy.cleanup)
        return policy

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_all_worker_lenses_deny_edit_and_write_tools(self):
        for lens in ('browser', 'tooling', 'data', 'reviewers'):
            with self.subTest(lens=lens):
                policy = self.policy(lens)
                before = self.snapshot()
                offered = [t['function']['name'] for t in policy.tools()]
                self.assertNotIn('write_file', offered)
                self.assertNotIn('edit_file', offered)
                for name, args in [('write_file', {'path': 'tests/app.spec.js', 'content': 'bad'}),
                                   ('edit_file', {'path': 'tests/app.spec.js', 'old_string': 'protected', 'new_string': 'bad'})]:
                    result = agent.run_tool(policy, name, args)
                    self.assertIn('error', result.lower(), result)
                    self.assertEqual(before, self.snapshot())

    def test_probe_has_scratch_cwd_and_includes_untracked_files(self):
        policy = self.policy()
        before = self.snapshot()
        result = agent.run_tool(policy, 'bash', {'command':
            'pwd; cat untracked.txt; printf changed > tests/app.spec.js; '
            'printf changed > package.json; printf changed > package-lock.json; '
            'mkdir -p node_modules; printf installed > node_modules/probe'})
        self.assertIn('uncommitted input', result)
        self.assertNotIn(str(self.root), result.splitlines()[0])
        self.assertEqual(before, self.snapshot())

    def test_absolute_project_write_is_refused_and_names_worker(self):
        policy = self.policy('browser')
        before = self.snapshot()
        target = shlex.quote(str(self.root / 'tests/app.spec.js'))
        try:
            result = agent.run_tool(policy, 'bash', {'command': 'printf changed > ' + target})
        except ValueError as error:
            result = str(error)
        self.assertEqual(before, self.snapshot())
        self.assertIn('preflight-worker-browser', result)


class GenericFields(unittest.TestCase):
    def test_run22_wrong_fields_are_not_accepted_by_generic_packet_schemas(self):
        for factory in (worker_schemas.edit_ops_packet, worker_schemas.resolution_ops_packet):
            schema = factory(ids=['INV-4', 'B-1'])
            for row, field in [('INV-4', 'tests'), ('INV-4', 'type'), ('B-1', 'title')]:
                op = {'op': 'set_fields', 'id': row, 'fields': {field: 'wrong'}}
                packet = {'schema': 'uncle.artifact/v1', 'kind': schema['properties']['kind']['const']}
                if factory == worker_schemas.edit_ops_packet:
                    packet.update(dispositions=[], ops=[op])
                else:
                    packet['resolutions'] = [{'group': 'G4', 'ops': [op]}]
                with self.subTest(factory=factory.__name__, row=row, field=field):
                    with self.assertRaises(ValueError):
                        transport.conforms(packet, schema)

    def test_valid_fields_remain_accepted(self):
        schema = worker_schemas.edit_ops_packet(ids=['INV-4', 'B-1'])
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet', 'dispositions': [],
                  'ops': [{'op': 'set_fields', 'id': 'INV-4', 'fields': {'test': 'assert invariant'}},
                          {'op': 'set_fields', 'id': 'B-1', 'fields': {'result': 'display value'}}]}
        transport.conforms(packet, schema)


class WriterFallback(unittest.TestCase):
    run_driver = order.AttemptOrder.run_driver

    def run_attempts(self, change=False):
        stub = order.STUB.replace("'strict': strict,", "'strict': strict, 'cheap': os.environ.get('UNCLE_UPDATED_PLAN_CHEAP_RETRY'), 'schema_first': os.environ.get('WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST'),")
        stub = stub.replace("if mode == 'writer-transport' and n == '1' and not prior:",
                            "if mode == 'writer-transport' and n.startswith('1') and not prior:")
        with patch.object(order, 'STUB', stub):
            return self.run_driver(mode='writer-transport', change=change,
                                   config='self-hosted.writer-schema-first off\n')

    def test_failed_writer_uses_strict_cheap_single_finding_before_tool_fallback(self):
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_attempts(change)
                first = [r for r in rows if r['stage'].endswith('-edits-1')]
                self.assertEqual(len(first), 1)
                for suffix in ('1-1', '1-2', '1-3'):
                    attempts = [r for r in rows if r['stage'].endswith('-edits-' + suffix)]
                    self.assertEqual(len(attempts), 2, rows)
                    self.assertEqual([r['cheap'] for r in attempts], ['1', None], attempts)
                    self.assertTrue(attempts[0]['strict'], attempts)
                    self.assertEqual(attempts[-1]['schema_first'], 'off', attempts)
                sibling = [r for r in rows if r['stage'].endswith('-edits-2')]
                self.assertEqual(len(sibling), 1)

    def test_writer_budget_defaults_and_config_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'config'
            with patch.dict(os.environ, {'UNCLE_CONFIG': str(config),
                    'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-3'}, clear=True):
                def seconds():
                    setup = self_hosted._http_setup('agent', {}, 'Deliver.', root, True,
                                                     'updated-plan-edit-ops-packet')
                    self.addCleanup(setup[1].cleanup)
                    return setup[-1]
                self.assertEqual(seconds(), 150)
                config.write_text('self-hosted.writer-seconds 7\n')
                self.assertEqual(seconds(), 7)
                with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_WRITER_SECONDS='2'):
                    self.assertEqual(seconds(), 2)


if __name__ == '__main__':
    unittest.main()
