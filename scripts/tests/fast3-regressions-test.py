#!/usr/bin/env python3
"""Run-22 regressions: isolated probes, bounded writers, and valid row fields."""
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
import shlex
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import http_agent as agent
import preflight_readonly
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


    def test_probe_subprocess_cannot_write_through_symlink_to_project(self):
        policy = self.policy('tooling')
        before = self.snapshot()
        code = "from pathlib import Path; Path('project-link/app.spec.js').write_text('changed')"
        try:
            result = agent.run_tool(policy, 'bash', {'command': 'ln -s ' + shlex.quote(str(self.root / 'tests')) + ' project-link; ' + shlex.quote(sys.executable) + ' -c ' + shlex.quote(code)})
        except ValueError as error:
            result = str(error)
        self.assertEqual(before, self.snapshot())
        self.assertIn('preflight-worker-tooling', result)


class PreflightCancellation(unittest.TestCase):
    def test_failed_worker_cleans_cancelled_sibling_snapshots(self):
        source = (ROOT / 'scripts/stagegate.sh').read_text()
        functions = '\n'.join(re.search(r'^' + name + r'\(\) \{\n.*?^}', source, re.M | re.S)[0]
                              for name in ('run_preflight_readonly_worker', 'run_preflight_investigation_panel'))
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            project, scratch = base / 'project', base / 'scratch'
            (project / 'tests').mkdir(parents=True)
            (project / 'tests/app.spec.js').write_text('protected')
            state = project / '.uncle/workflow'
            (state / 'logs').mkdir(parents=True)
            scratch.mkdir()
            script = functions + r"""
stage_tools() { echo Read,Glob,Grep,Bash; }
run_claude() {
    touch "$STATE_DIR/$2-started"
    if [[ "$2" == preflight-worker-tooling ]]; then
        while [[ ! -f "$STATE_DIR/preflight-worker-data-started" || ! -f "$STATE_DIR/preflight-worker-reviewers-started" ]]; do sleep .01; done
        printf changed > tests/app.spec.js
    else
        sleep 10
    fi
}
run_preflight_investigation_panel
"""
            env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
            env.update(ROOT=str(ROOT), STATE_DIR=str(state), LOG_DIR=str(state / 'logs'), TMPDIR=str(scratch))
            result = subprocess.run(['bash', '-c', script], cwd=project, env=env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('preflight-worker-tooling', result.stderr)
            self.assertEqual((project / 'tests/app.spec.js').read_text(), 'protected')
            self.assertFalse(list(scratch.glob('uncle-preflight-*')), 'cancelled workers leaked project snapshots')


class PreflightSnapshotMetadata(unittest.TestCase):
    def test_project_local_tmpdir_cannot_contain_snapshot_or_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            local = root / 'tmp'
            local.mkdir()
            (root / 'input').write_text('untracked')
            copy = preflight_readonly.copy_project
            def guarded_copy(source, target):
                self.assertFalse(Path(target).is_relative_to(root), 'scratch allocation is inside live project')
                return copy(source, target)
            with patch.object(tempfile, 'tempdir', str(local)), \
                    patch.dict(os.environ, {'TMPDIR': str(local), 'UNCLE_STATUS_STAGE': 'preflight-worker-tooling',
                               'UNCLE_CONFIG': str(root / 'config'), 'UNCLE_PROJECT_ROOT': str(root)}, clear=True), \
                    patch.object(preflight_readonly, 'copy_project', side_effect=guarded_copy):
                staged = preflight_readonly.prepare(root)
                try:
                    self.assertEqual((staged / 'input').read_text(), 'untracked')
                finally:
                    preflight_readonly.main(['remove', str(staged)])
                _, policy, _, _, _, _ = self_hosted._http_setup('agent', {}, '', root, True, 'preflight-worker-packet')
                try:
                    self.assertIn('untracked', agent.run_tool(policy, 'bash', {'command': 'cat input'}))
                finally:
                    policy.cleanup()
                self.assertEqual(list(local.iterdir()), [])

    def test_worker_directory_and_mode_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'input').write_text('untracked')
            for mutation in ('directory', 'mode'):
                with self.subTest(mutation=mutation):
                    staged = preflight_readonly.prepare(root)
                    try:
                        if mutation == 'directory':
                            (staged / 'new-empty-directory').mkdir()
                        else:
                            (staged / 'input').chmod(0o700)
                        with self.assertRaisesRegex(preflight_readonly.Violation, 'preflight-worker-data'):
                            preflight_readonly.check(staged, 'preflight-worker-data')
                    finally:
                        preflight_readonly.main(['remove', str(staged)])


class PreflightFallback(unittest.TestCase):
    def test_fallback_publishes_only_validated_document_and_keeps_concurrent_edits(self):
        text = ('# Preflight\n\n## Acceptance gate\n| ID | Required | Status | Evidence |\n'
                '|---|---|---|---|\n| PF-1 | YES | PASS | Checked runtime |\n')
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'), 'UNCLE_PROJECT_ROOT': temp,
                'UNCLE_STATUS_STAGE': 'preflight-investigate'}, clear=True):
            root = Path(temp).resolve()
            (root / 'input').write_text('before implementation')
            seen = []
            def investigate(side, values, prompt, staged, **kwargs):
                seen.append(staged)
                self.assertFalse(staged.is_relative_to(root))
                self.assertEqual((staged / 'input').read_text(), 'before implementation')
                (staged / 'input').write_text('incidental scratch change')
                (staged / 'unexpected').write_text('must not publish')
                (root / 'input').write_text('concurrent implementation')
                target = staged / '.uncle/workflow/preflight-investigation.md'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
                return 'diagnostic only', 1
            with patch.object(self_hosted, 'run_http_agent', side_effect=investigate):
                self.assertEqual(self_hosted.run_opencode('agent', {}, 'Probe.', root,
                                 stage='preflight-investigate'), ('diagnostic only', 1))
            self.assertEqual((root / 'input').read_text(), 'concurrent implementation')
            self.assertEqual((root / '.uncle/workflow/preflight-investigation.md').read_text(), text)
            self.assertFalse((root / 'unexpected').exists())
            self.assertFalse((root / '.uncle/workflow/documents').exists())
            self.assertTrue(all(not path.exists() for path in seen))

    def test_invalid_fallback_never_replaces_previous_investigation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'), 'UNCLE_PROJECT_ROOT': temp,
                'UNCLE_STATUS_STAGE': 'preflight-investigate'}, clear=True):
            root = Path(temp)
            target = root / '.uncle/workflow/preflight-investigation.md'
            target.parent.mkdir(parents=True)
            target.write_text('previous accepted document')
            def investigate(side, values, prompt, staged, **kwargs):
                candidate = staged / '.uncle/workflow/preflight-investigation.md'
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text('# Incomplete')
                return '', 1
            with patch.object(self_hosted, 'run_http_agent', side_effect=investigate):
                with self.assertRaises(ValueError):
                    self_hosted.run_opencode('agent', {}, 'Probe.', root, stage='preflight-investigate')
            self.assertEqual(target.read_text(), 'previous accepted document')


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


class WriterDeadline(unittest.TestCase):
    def test_trickling_stream_cannot_outlive_writer_budget(self):
        spec = importlib.util.spec_from_file_location('stream_fixture', ROOT / 'scripts/tests/self-hosted-capture-stream-test.py')
        stream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stream)
        def events(body):
            for number in range(40):
                yield stream.delta(content=str(number) + ',')
                time.sleep(.1)
            yield stream.delta(reason='stop')
            yield '[DONE]'
        server = stream.Server(events)
        self.addCleanup(server.close)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'), 'UNCLE_PROJECT_ROOT': temp,
                'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-3',
                'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096',
                'WORKFLOW_SELF_HOSTED_WRITER_SECONDS': '1',
                'WORKFLOW_SELF_HOSTED_RESULT_REUSE': 'off',
                'WORKFLOW_SELF_HOSTED_HTTP2': 'off'}, clear=True):
            start = time.monotonic()
            with self.assertRaisesRegex(Exception, 'time|budget|deadline'):
                self_hosted.run_http_agent('agent', server.values, 'Deliver the packet.', Path(temp),
                                          schema_kind='updated-plan-edit-ops-packet')
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 3, 'writer stream exceeded its one-second budget')
            self.assertEqual(len(server.requests), 1, 'timeout must return to driver before another request')


    def test_last_resort_tool_loop_shares_the_writer_deadline(self):
        spec = importlib.util.spec_from_file_location('http_fixture', ROOT / 'scripts/tests/self-hosted-http-test.py')
        http = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(http)
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                  'dispositions': [], 'ops': []}
        calls = [{'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'read-' + str(i), 'type': 'function', 'function': {
                'name': 'read_file', 'arguments': '{"path":"input.txt"}'}}]} for i in range(10)]
        server = http.Server(packet, tool_script=calls, delay=.4)
        self.addCleanup(server.close)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'), 'UNCLE_PROJECT_ROOT': temp,
                'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-3-1',
                'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096',
                'WORKFLOW_SELF_HOSTED_WRITER_SECONDS': '1',
                'WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST': 'off',
                'WORKFLOW_SELF_HOSTED_RESULT_REUSE': 'off',
                'WORKFLOW_SELF_HOSTED_HTTP2': 'off'}, clear=True):
            (Path(temp) / 'input.txt').write_text('plan context')
            start = time.monotonic()
            with self.assertRaisesRegex(Exception, 'time|budget|deadline'):
                self_hosted.run_http_agent('agent', {'base_url': server.url, 'api_key': 'stub', 'model': 'stub'},
                    'Deliver the packet.', Path(temp), schema_kind=packet['kind'], turns=20)
            self.assertLess(time.monotonic() - start, 3)
            self.assertGreaterEqual(len(server.requests), 2, 'budget must be shared by several tool turns')
            self.assertLess(len(server.requests), 10)


class WriterFallback(unittest.TestCase):
    run_driver = order.AttemptOrder.run_driver

    def run_attempts(self, change=False, timed=False):
        stub = order.STUB.replace("'strict': strict,", "'strict': strict, 'cheap': os.environ.get('UNCLE_UPDATED_PLAN_CHEAP_RETRY'), 'schema_first': os.environ.get('WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST'),")
        stub = stub.replace("if mode == 'writer-transport' and n == '1' and not prior:",
                            "if mode == 'writer-transport' and n.startswith('1') and not prior:")
        if timed:
            stub = stub.replace("    if mode == 'writer-transport' and n.startswith('1') and not prior:",
                "    if mode == 'writer-transport' and n == '1' and not prior:\n        time.sleep(10)\n"
                "    if mode == 'writer-transport' and n.startswith('1') and not prior:")
        with patch.object(order, 'STUB', stub):
            return self.run_driver(mode='writer-transport', change=change,
                                   config='self-hosted.writer-schema-first off\n',
                                   overrides={'WORKFLOW_SELF_HOSTED_WRITER_SECONDS': '1'} if timed else None)

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

    def test_driver_timeout_enters_cheap_retry_before_last_tool_attempt(self):
        for change in (False, True):
            with self.subTest(change=change):
                rows = self.run_attempts(change, timed=True)
                original = next(row for row in rows if row['stage'].endswith('-edits-1'))
                retry = [row for row in rows if row['stage'].endswith('-edits-1-1')]
                self.assertEqual([row['cheap'] for row in retry], ['1', None])
                self.assertTrue(retry[0]['strict'])
                self.assertEqual(retry[1]['schema_first'], 'off')
                delay = (retry[0]['started'] - original['started']) / 1e9
                self.assertGreaterEqual(delay, .8)
                self.assertLess(delay, 8, 'driver waited for the ten-second stub instead of enforcing budget')
                self.assertEqual(sum(row['stage'].endswith('-edits-2') for row in rows), 1)

    def test_cheap_retry_forces_constrained_delivery_and_thinking_off(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                  'dispositions': [], 'ops': []}
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'), 'UNCLE_PROJECT_ROOT': temp,
                'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-3-1',
                'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096', 'UNCLE_UPDATED_PLAN_CHEAP_RETRY': '1',
                'WORKFLOW_SELF_HOSTED_WRITER_SCHEMA_FIRST': 'off',
                'WORKFLOW_SELF_HOSTED_REASONING_EFFORT': 'on',
                'WORKFLOW_SELF_HOSTED_REQUEST_OPTIONS': '{"chat_template_kwargs":{"enable_thinking":true}}',
                'WORKFLOW_SELF_HOSTED_RESULT_REUSE': 'off'}, clear=True), \
                patch.object(agent, 'chat', side_effect=AssertionError('cheap retry opened tool loop')) as chat, \
                patch.object(agent, 'constrained_completion', return_value=(json.dumps(packet), 'stop', {}, 'json_schema')) as complete:
            result, count = self_hosted.run_http_agent('agent', {'base_url': 'http://unused.invalid/v1',
                'api_key': 'stub', 'model': 'stub'}, 'Deliver.', Path(temp), schema_kind=packet['kind'])
            self.assertEqual((json.loads(result), count), (packet, 1))
            chat.assert_not_called()
            args = complete.call_args.args
            self.assertIsNone(args[5], 'reasoning_effort must not switch thinking back on')
            self.assertFalse(args[0]['_request_options']['chat_template_kwargs']['enable_thinking'])
            self.assertEqual(complete.call_args.kwargs.get('skip', ()), ())

    def test_opencode_transport_uses_http_only_for_cheap_retry(self):
        packet = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet',
                             'dispositions': [], 'ops': []})
        for stage in ('updated-plan-worker-edits-3-1', 'updated-change-plan-worker-edits-3-1'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp, \
                    patch.dict(os.environ, {'UNCLE_CONFIG': str(Path(temp) / 'config'),
                        'UNCLE_PROJECT_ROOT': temp, 'UNCLE_STATUS_STAGE': stage,
                        'WORKFLOW_SELF_HOSTED_TRANSPORT': 'opencode'}, clear=True), \
                    patch.object(self_hosted, '_run_opencode', return_value=(packet, 1)) as opencode, \
                    patch.object(self_hosted, 'run_http_agent', return_value=(packet, 1)) as http:
                values = {'base_url': 'http://unused.invalid/v1', 'api_key': 'stub', 'model': 'stub'}
                for marker in ('0', '1', '0'):
                    with patch.dict(os.environ, UNCLE_UPDATED_PLAN_CHEAP_RETRY=marker):
                        self.assertEqual(self_hosted.run_opencode('agent', values, packet, Path(temp), stage=stage),
                                         (packet, 1))
                self.assertEqual(http.call_count, 1)
                self.assertEqual(opencode.call_count, 2)
                self.assertEqual(http.call_args.args[1], values)
                self.assertEqual(http.call_args.kwargs['schema_kind'], 'updated-plan-edit-ops-packet')

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
