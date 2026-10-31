#!/usr/bin/env python3
"""Run-23 regressions: bounded progress, no restart, and retained evidence."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import self_hosted
import self_hosted_http as transport
import updated_plan_synthesis_prompt as prompt
import writer_deadline


def fixture(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts/tests' / (name + '-test.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


order = fixture('updated-plan-schema-order')
stream = fixture('self-hosted-capture-stream')


def functions(driver, names):
    source = (ROOT / 'scripts' / driver).read_text()
    return '\n'.join(re.search(r'^' + name + r'\(\) \{\n.*?^}', source, re.M | re.S)[0] for name in names)


def environment(root, **values):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
    env.update(ROOT=str(ROOT), UNCLE_CONFIG=str(root / 'config'), UNCLE_PROJECT_ROOT=str(root),
               STATE_DIR=str(root / '.uncle/workflow'), LOG_DIR=str(root / '.uncle/workflow/logs'))
    env.update(values)
    return env


class RestartPaths(unittest.TestCase):
    def run_speculation(self, reason='', changed=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        state = root / '.uncle/workflow'
        (state / 'logs').mkdir(parents=True)
        (state / 'speculative').mkdir()
        (state / 'speculative/UPDATED_PLAN.input').write_text('old' if changed else 'same')
        (root / 'gate.json').write_text('{}')
        script = functions('stagegate.sh', ['adopt_speculation', 'run_gated_stage']) + r'''
. "$ROOT/scripts/lib/model-jobs.sh"
canonical_artifact_path() { echo "$1"; }
hash_file() { echo same; }
run_stage() { echo restarted >> calls; }
SPEC_DIR="$STATE_DIR/speculative"
spec_stage=UPDATED_PLAN
( if [[ -n "$TEST_REASON" ]]; then printf '%s\n' "$TEST_REASON" > "$STATE_DIR/stop-reason"; fi
  if [[ "$TEST_REASON" == *'writer attempts exhausted'* ]]; then touch "$STATE_DIR/updated-plan-writers-exhausted"; fi
  exit 1 ) &
spec_pid=$!
run_gated_stage UPDATED_PLAN gate.json artifact.json
'''
        result = subprocess.run(['bash', '-c', script], cwd=root,
            env=environment(root, TEST_REASON=reason), capture_output=True, text=True, timeout=10)
        return result, root

    def test_speculative_exhaustion_stops_without_restarting_even_if_approval_changed(self):
        for changed in (False, True):
            with self.subTest(changed=changed):
                reason = 'updated-plan: writer attempts exhausted'
                result, root = self.run_speculation(reason, changed)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((root / 'calls').exists(), result.stdout + result.stderr)
                self.assertIn(reason, result.stdout + result.stderr)

    def test_speculative_readonly_violation_stops_without_restart(self):
        reason = 'preflight-worker-browser: read-only preflight violation'
        result, root = self.run_speculation(reason)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((root / 'calls').exists(), result.stdout + result.stderr)
        self.assertIn(reason, result.stdout + result.stderr)

    def test_transient_speculative_failure_can_run_normally_once(self):
        result, root = self.run_speculation(changed=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((root / 'calls').read_text(), 'restarted\n')

    def test_explicit_speculative_rerun_keeps_both_round_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / '.uncle/workflow'
            (state / 'logs').mkdir(parents=True)
            (root / 'gate.json').write_text('{}')
            script = functions('stagegate.sh', ['speculate']) + r'''
. "$ROOT/scripts/lib/model-jobs.sh"
canonical_artifact_path() { echo "$1"; }
hash_file() { echo same; }
run_stage() { echo "round-$ROUND"; return 1; }
SPEC_DIR="$STATE_DIR/speculative"
WORKFLOW_SPECULATE=1
spec_pid= spec_stage=
ROUND=1 speculate UPDATED_PLAN gate.json
wait "$spec_pid" || true
spec_pid= spec_stage=
ROUND=2 speculate UPDATED_PLAN gate.json
wait "$spec_pid" || true
'''
            result = subprocess.run(['bash', '-c', script], cwd=root, env=environment(root),
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            logs = list((state / 'logs').glob('UPDATED_PLAN.speculative*.log'))
            self.assertGreaterEqual(len(logs), 2, logs)
            for n in (1, 2):
                self.assertTrue(any('round-%d' % n in p.read_text() for p in logs), logs)

    def test_both_drivers_do_not_enter_panel_after_bounded_failure(self):
        for change in (False, True):
            for reason in ('writer attempts exhausted', 'read-only preflight violation'):
                with self.subTest(change=change, reason=reason), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    state = root / '.uncle/workflow'
                    (state / 'documents').mkdir(parents=True)
                    (state / 'documents/CHANGE_PLAN.json').write_text('{}')
                    driver = 'change-workflow.sh' if change else 'stagegate.sh'
                    source = (ROOT / 'scripts' / driver).read_text()
                    start = source.index('        UPDATED_PLAN)\n')
                    end = source.index('\n            ;;', start)
                    body = source[start + len('        UPDATED_PLAN)'):end]
                    prefix = 'updated_change_plan' if change else 'updated_plan'
                    script = '. "$ROOT/scripts/lib/model-jobs.sh"\n' + r'''
verify_approval() { :; }
stage_uses_self_hosted() { return 0; }
set_state() { :; }
''' + '\nrun_' + prefix + '_fast_path() { return 1; }\nrun_' + prefix + '_decide() {\n' + r'''
printf '%s\n' "$TEST_REASON" > "$STATE_DIR/stop-reason"
[[ "$TEST_REASON" != *'writer attempts exhausted'* ]] || touch "$STATE_DIR/updated-plan-writers-exhausted"
return 1
}
''' + 'run_' + prefix + '_panel() { touch restarted; return 1; }\nrun_test() {\n' + body + '\n}\nrun_test\n'
                    result = subprocess.run(['bash', '-c', script], cwd=root,
                        env=environment(root, WORKFLOW_UPDATED_PLAN_COMPACT='0', TEST_REASON='updated-plan: ' + reason),
                        capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse((root / 'restarted').exists(), result.stdout + result.stderr)
                    self.assertIn(reason, result.stdout + result.stderr)


class TriageRestart(unittest.TestCase):
    def test_terminal_failure_blocks_auto_resume_but_preserves_explicit_resume(self):
        triage = fixture('triage-chat')
        for reason in ('updated-plan: writer attempts exhausted',
                       'preflight-worker-browser: read-only preflight violation'):
            for mode in ('diagnosis', 'do'):
                with self.subTest(reason=reason, mode=mode), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    state = root / '.uncle/workflow'
                    state.mkdir(parents=True)
                    (state / 'stop-reason').write_text(reason + '\n')
                    (state / 'state').write_text('UPDATED_PLAN\n')
                    with patch.object(triage.tui, '_project_root', return_value=str(root)), \
                            patch.dict(os.environ, environment(root), clear=True):
                        ui = triage.TriageTests.ui(self)
                        ui._triage_init()
                        ui.workflow_unattended = True
                        ui.triage_offer_resume = True
                        ui.triage_do_offer = True
                        ui.triage_classification = 'tool bug'
                        with patch.object(ui, '_run', side_effect=lambda: setattr(ui, 'state', 'running')) as start:
                            if mode == 'diagnosis':
                                ui._maybe_auto_resume_triage()
                            else:
                                ui._auto_resume_after_do((1, 'Resume as is; no files edited.'), triage.TriageTests.CLEAN, False)
                            start.assert_not_called()
                            self.assertIn(reason, ' '.join(text for _, text in ui.triage_history))
                            ui._triage_command('/resume')
                            start.assert_called_once()



class ProgressDeadline(unittest.TestCase):
    def run_stream(self, events, **options):
        server = stream.Server(events)
        self.addCleanup(server.close)
        self.addCleanup(transport.close_connections)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        env = {'UNCLE_CONFIG': str(root / 'config'), 'UNCLE_PROJECT_ROOT': str(root),
               'UNCLE_STATUS_STAGE': 'updated-plan-worker-edits-3',
               'UNCLE_UPDATED_PLAN_ANSWER_TOKENS': '4096',
               'WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS': '1',
               'WORKFLOW_SELF_HOSTED_WRITER_SECONDS': '8',
               'WORKFLOW_SELF_HOSTED_RESULT_REUSE': 'off', 'WORKFLOW_SELF_HOSTED_HTTP2': 'off'}
        env.update(options)
        env = {key: value for key, value in env.items() if value is not None}
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()):
            result = self_hosted.run_http_agent('agent', server.values, 'Deliver the packet.', root,
                                               schema_kind='updated-plan-edit-ops-packet')
        return result, server

    def test_default_ceiling_scales_and_stage_config_overrides_family(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / 'config'
            with patch.dict(os.environ, {'UNCLE_CONFIG': str(config),
                    'UNCLE_STATUS_STAGE': 'updated-change-plan-worker-edits-3'}, clear=True):
                self.assertEqual(writer_deadline.seconds(), 720)
                config.write_text('self-hosted.writer-seconds 900\nupdated-change-plan.writer-seconds 800\n')
                self.assertEqual(writer_deadline.seconds(), 800)
                with patch.dict(os.environ, WORKFLOW_SELF_HOSTED_WRITER_SECONDS='700'):
                    self.assertEqual(writer_deadline.seconds(), 700)
                config.write_text('self-hosted.writer-jobs 20\n')
                self.assertEqual(writer_deadline.seconds(), 1200)

    def test_slow_streaming_writer_survives_several_idle_windows(self):
        packet = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-edit-ops-packet', 'dispositions': [], 'ops': []}
        text = json.dumps(packet)
        def events(body):
            for index in range(0, len(text), 10):
                yield stream.delta(text[index:index + 10])
                time.sleep(.2)
            yield stream.delta(reason='stop')
            yield '[DONE]'
        started = time.monotonic()
        seconds = writer_deadline.seconds
        # Scale production ceilings 100:1: the old 150s dies at 1.5s, while
        # the concurrency-scaled ceiling permits this continuously streaming answer.
        with patch.object(writer_deadline, 'seconds', side_effect=lambda default=3600: seconds(default) / 100):
            result, server = self.run_stream(events, WORKFLOW_SELF_HOSTED_WRITER_SECONDS=None)
        self.assertEqual(json.loads(result[0]), packet)
        self.assertGreater(time.monotonic() - started, 2)
        self.assertEqual(len(server.requests), 1)

    def test_silent_stream_is_stopped_at_no_progress_window(self):
        def events(body):
            yield stream.delta('{')
            time.sleep(4)
            yield stream.delta('}')
            yield '[DONE]'
        started = time.monotonic()
        with self.assertRaisesRegex(Exception, 'no.progress'):
            self.run_stream(events)
        self.assertLess(time.monotonic() - started, 3)

    def test_opencode_streaming_output_resets_no_progress_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child = root / 'opencode-stub.py'
            child.write_text("import json, time\nfor n in range(12):\n"
                             "    print(json.dumps({'type': 'text', 'part': {'text': 'token%d' % n}}), flush=True)\n"
                             "    time.sleep(.2)\n"
                             "print(json.dumps({'type': 'step_finish', 'part': {'reason': 'stop', 'tokens': {'output': 24}}}), flush=True)\n")
            env = environment(root, UNCLE_STATUS_STAGE='updated-plan-worker-edits-1',
                              WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS='1',
                              WORKFLOW_SELF_HOSTED_WRITER_SECONDS='8')
            def invoke(side, values, prompt, project, stage, usage):
                return self_hosted._run_opencode(side, values, prompt, project, usage=usage)
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(self_hosted, 'opencode_invocation', return_value=([sys.executable, str(child)], env)), \
                    patch.object(self_hosted, '_run_stage', side_effect=invoke):
                text, turns = self_hosted.run_opencode('agent', {'model': 'stub'}, 'Deliver.', root,
                                                      stage='updated-plan-worker-edits-1')
            self.assertIn('token11', text)
            self.assertGreaterEqual(turns, 1)

    def test_native_opencode_repeated_polls_do_not_count_as_new_progress(self):
        import native_opencode as native
        stage = Mock(stage='updated-plan-worker-edits-1', side='agent', prompt='Deliver.')
        stage.option.return_value = None
        child = Mock()
        child.poll.return_value = None
        polls, observed = [], []
        def urlopen(request, **kwargs):
            url = request.full_url
            if url.endswith('/global/health') or url.endswith('/session/status'):
                value = {}
            elif url.endswith('/session'):
                value = {'id': 's'}
            elif url.endswith('/prompt_async'):
                value = None
            else:
                self.assertTrue(url.endswith('/session/s/message'), url)
                polls.append(len(polls) + 1)
                complete = len(polls) == 3
                value = [{'info': {'id': 'u', 'role': 'user'}},
                         {'info': {'id': 'a', 'role': 'assistant', 'parentID': 'u',
                                   'time': {'completed': 1} if complete else {}, 'tokens': {'output': 2}},
                          'parts': [{'id': 'p', 'type': 'text', 'text': 'ab' if complete else 'a'}]}]
            response = Mock()
            response.read.return_value = json.dumps(value).encode()
            return contextlib.nullcontext(response)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, environment(Path(temp)), clear=True), \
                patch.object(native, 'opencode_invocation', return_value=([], {})), \
                patch.object(native, 'timed_popen', return_value=child), \
                patch.object(native, 'launch_command', side_effect=lambda command: command), \
                patch.object(native.urllib.request, 'urlopen', side_effect=urlopen), \
                patch.object(native.time, 'sleep'), \
                patch.object(writer_deadline, 'progress', side_effect=lambda: observed.append(len(polls))):
            native.run(stage, temp, values={'model': 'stub'}, root=temp)
        self.assertEqual(observed, [1, 3])
        self.assertEqual(stage.final_answer, 'ab')

    def test_shell_watchdog_uses_actual_worker_stage_override(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = r'''
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { return 0; }
run_claude() { sleep 3; }
workflow_model_writer updated-plan run_claude prompt updated-plan-worker-edits-3
'''
            result = subprocess.run(['bash', '-c', script], cwd=root, env=environment(root,
                WORKFLOW_SELF_HOSTED_WRITER_SECONDS='8',
                WORKFLOW_SELF_HOSTED_WRITER_SECONDS_UPDATED_PLAN_WORKER_EDITS_3='1'),
                capture_output=True, text=True, timeout=6)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('deadline: ceiling', result.stderr)
            self.assertIn('1s', result.stderr)

    def test_nested_runner_deadlines_cannot_extend_aggregate_allowance(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'UNCLE_CONFIG': str(Path(temp) / 'config'),
                'WORKFLOW_SELF_HOSTED_WRITER_NO_PROGRESS_SECONDS': '5'}, clear=True):
            with self.assertRaisesRegex(Exception, 'ceiling|wall-clock budget'):
                with writer_deadline.deadline(.5):
                    time.sleep(.3)
                    with writer_deadline.deadline(2):
                        time.sleep(.4)

    def test_stream_progress_does_not_reset_absolute_ceiling(self):
        def events(body):
            for index in range(80):
                yield stream.delta(str(index) + ',')
                time.sleep(.1)
            yield '[DONE]'
        started = time.monotonic()
        with self.assertRaisesRegex(Exception, 'ceiling|wall-clock budget'):
            self.run_stream(events, WORKFLOW_SELF_HOSTED_WRITER_SECONDS='1')
        self.assertLess(time.monotonic() - started, 3)


class ResolverExhaustion(unittest.TestCase):
    def run_resolvers(self, change, semantic=False, granularity='small'):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / '.uncle/workflow'
        (state / 'logs').mkdir(parents=True)
        (state / 'documents').mkdir()
        (root / '.uncle/docs').mkdir()
        plan = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan' if change else 'plan',
                'narrative': order.NARRATIVE, 'verification_commands': 'true',
                'protected_verification_paths': 'tests/a.test.js'}
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review',
                  'findings': [{'id': 'AR-%d' % n} for n in range(1, 7)]}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        (state / 'documents' / ('CHANGE_PLAN.json' if change else 'PROJECT_PLAN.json')).write_text(json.dumps(plan))
        (state / 'documents/ADVERSARIAL_REVIEW.json').write_text(json.dumps(review))
        (root / 'prompt.md').write_text(prompt.prompt(plan, review, workers, change=change))
        stub = order.STUB.replace("if mode == 'resolver-transport' and group == 'G1' and not stage.endswith('-retry'):",
                                 "if mode == 'resolver-transport' and group == 'G1':\n        print('resolver-attempt-%d' % (len(prior) + (2 if stage.endswith('-retry') else 1)), flush=True)")
        if semantic:
            stub = stub.replace("invalid = mode == 'resolver-invalid' and group == 'G1' and not stage.endswith('-retry')",
                                "invalid = mode == 'resolver-invalid' and group == 'G1'")
        (root / 'stub.py').write_text(stub)
        prefix = 'updated_change_plan' if change else 'updated_plan'
        names = [prefix + '_launch_writer', 'run_' + prefix + '_edit_writers']
        if not change:
            names.append('updated_plan_warm_prefix')
        script = functions('change-workflow.sh' if change else 'stagegate.sh', names) + r'''
UPDATED_PLAN_PROMPT="$PWD/prompt.md"
MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=
UPDATED_PLAN_ADVISOR_PIDS=()
stage_uses_self_hosted() { return 0; }
stage_supports_structured_output() { return 1; }
run_claude() { python3 -I "$PWD/stub.py" "$1" "$2"; }
''' + 'run_' + prefix + '_edit_writers\n'
        result = subprocess.run(['bash', '-c', script], cwd=root, env=environment(root,
            SCHEMA_TEST_MODE='resolver-invalid' if semantic else 'resolver-transport', WORKFLOW_UPDATED_PLAN_EDIT_SLICE='3',
            WORKFLOW_SELF_HOSTED_GRANULARITY=granularity, WORKFLOW_PREFIX_WARM_SECONDS='0'),
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return state, result

    def test_archived_resolver_answers_are_not_live_merge_inputs(self):
        import updated_plan_edits as edits
        import updated_plan_ops as ops
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            archived = {'group': 'G1', 'ops': [], 'patch': {}}
            live = {'group': 'G2', 'ops': [], 'patch': {}}
            (directory / 'resolutions-G1-r1.json').write_text(json.dumps({'resolutions': [archived]}))
            (directory / 'resolutions-G2.json').write_text(json.dumps({'resolutions': [live]}))
            with self.subTest(kind='ops'):
                self.assertEqual(ops.read_answers(directory, [{'id': 'G1'}, {'id': 'G2'}]), {'G2': live})
            with self.subTest(kind='text-edits'):
                self.assertEqual(edits.read_resolutions(directory)['resolutions'], [live])
            plan = directory / 'plan.json'
            plan.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'plan',
                                         'narrative': order.NARRATIVE, 'verification_commands': 'true'}))
            (directory / 'conflicts.json').write_text(json.dumps([{'id': 'G1', 'kind': 'ops', 'heading': 'Notes'}]))
            (directory / 'prompts').mkdir()
            (directory / 'prompts/resolve-G1.md').write_text('Resolve G1.')
            for helper in (ops, edits):
                with self.subTest(validator=helper.__name__):
                    self.assertIn('G1', helper.check_resolutions(plan, directory))

    def test_exhausted_resolvers_record_terminal_failure_and_keep_sibling(self):
        for change in (False, True):
            with self.subTest(change=change):
                state, result = self.run_resolvers(change)
                self.assertTrue((state / 'updated-plan-writers-exhausted').exists(), result.stdout + result.stderr)
                self.assertIn('writer attempts exhausted', (state / 'stop-reason').read_text())
                directory = state / ('updated-change-plan-edits' if change else 'updated-plan-edits')
                self.assertTrue((directory / 'resolutions-G2.json').exists())
                records = [json.loads(line) for path in state.glob('attempts-*-resolve-G2.jsonl')
                           for line in path.read_text().splitlines()]
                self.assertEqual(len(records), 1)

    def test_final_semantic_rejection_is_logged_and_terminal_in_both_profiles(self):
        for change in (False, True):
            for granularity, attempts in (('small', 3), ('large', 2)):
                with self.subTest(change=change, granularity=granularity):
                    state, result = self.run_resolvers(change, semantic=True, granularity=granularity)
                    self.assertTrue((state / 'updated-plan-writers-exhausted').exists(), result.stdout + result.stderr)
                    self.assertIn('writer attempts exhausted', (state / 'stop-reason').read_text())
                    for name in ('UPDATED_PLAN.log', 'UPDATED_PLAN.speculative.log'):
                        lines = (state / 'logs' / name).read_text().splitlines()
                        rejections = [line for line in lines if 'resolve-G1' in line and 'schema rejection' in line]
                        self.assertEqual(len(rejections), attempts, lines)
                        self.assertTrue(all('B-999' in line for line in rejections), lines)

    def test_resolver_retry_and_alternate_keep_separate_failure_evidence(self):
        for change in (False, True):
            with self.subTest(change=change):
                state, result = self.run_resolvers(change)
                text = '\n'.join(path.read_text() for path in (state / 'logs').glob('*resolve-G1*.log'))
                for n in (1, 2, 3):
                    self.assertIn('resolver-attempt-%d' % n, text, result.stdout + result.stderr)
                for name in ('UPDATED_PLAN.log', 'UPDATED_PLAN.speculative.log'):
                    self.assertIn('resolve-G1', (state / 'logs' / name).read_text())



class WriterConcurrency(unittest.TestCase):
    def test_both_drivers_cap_writers_below_provider_pool(self):
        original_run = subprocess.run
        for change in (False, True):
            with self.subTest(change=change):
                ended = {}
                def run(*args, **kwargs):
                    result = original_run(*args, **kwargs)
                    if args and args[0] == ['bash', 'run.sh']:
                        state = Path(kwargs['cwd']) / '.uncle/workflow'
                        ended.update({p.name.removeprefix('ended-'): int(p.read_text()) for p in state.glob('ended-*')})
                    return result
                stub = order.STUB + "\ntime.sleep(1)\n(root / ('ended-' + stage)).write_text(str(time.monotonic_ns()))\n"
                with patch.object(order, 'STUB', stub), patch.object(order.subprocess, 'run', side_effect=run):
                    rows = order.AttemptOrder().run_driver(change=change, overrides={
                        'WORKFLOW_SELF_HOSTED_MAX_CONCURRENCY': '24',
                        'WORKFLOW_SELF_HOSTED_WRITER_JOBS': '2', 'WORKFLOW_UPDATED_PLAN_EDIT_SLICE': '1'})
                writers = [row for row in rows if '-edits-' in row['stage']]
                self.assertEqual(len(writers), 6)
                events = sorted([(row['started'], 1) for row in writers] +
                                [(ended[row['stage']], -1) for row in writers])
                active = peak = 0
                for _, delta in events:
                    active += delta
                    peak = max(active, peak)
                self.assertEqual(active, 0)
                self.assertLessEqual(peak, 2)



class AttemptEvidence(unittest.TestCase):
    def run_writers(self, change=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / '.uncle/workflow'
        logs = state / 'logs'
        logs.mkdir(parents=True)
        (state / 'documents').mkdir()
        directory = state / 'updated-plan-edits'
        (directory / 'prompts').mkdir(parents=True)
        plan = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan' if change else 'plan',
                'narrative': order.NARRATIVE, 'verification_commands': 'true',
                'protected_verification_paths': 'tests/a.test.js'}
        review = {'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review', 'findings': [{'id': 'AR-1'}]}
        workers = {'schema': 'uncle.artifact/v1', 'kind': 'updated-plan-worker-packets', 'workers': [], 'findings': []}
        (state / 'documents' / ('CHANGE_PLAN.json' if change else 'PROJECT_PLAN.json')).write_text(json.dumps(plan))
        (root / 'prompt.md').write_text(prompt.prompt(plan, review, workers, change=change))
        name = 'updated_change_plan_launch_writer' if change else 'updated_plan_launch_writer'
        script = functions('change-workflow.sh' if change else 'stagegate.sh', [name]) + r'''
. "$ROOT/scripts/lib/model-jobs.sh"
stage_uses_self_hosted() { return 0; }
UPDATED_PLAN_PROMPT="$PWD/prompt.md"
MODEL_UPDATED_PLAN=m; EFFORT_UPDATED_PLAN=low; BUDGET_UPDATED_PLAN=
run_claude() {
    echo "evidence-$ATTEMPT" > "$LOG_DIR/$2.jsonl"
    echo "evidence-$ATTEMPT runner exit code 7" >&2
    return 7
}
''' + '\n'.join('ATTEMPT=%d %s "$STATE_DIR/updated-plan-edits" local 1 AR-1 owner\nwait "$!" || true' % (n, name) for n in range(1, 4))
        result = subprocess.run(['bash', '-c', script], cwd=root,
            env=environment(root, WORKFLOW_SELF_HOSTED_MAX_CONCURRENCY='2'), capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return root, result

    def test_repeated_writer_launches_keep_every_log_and_jsonl(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result = self.run_writers(change)
                logs = root / '.uncle/workflow/logs'
                for suffix in ('.log', '.jsonl'):
                    paths = list(logs.glob('*' + suffix))
                    contents = [p.read_text() for p in paths]
                    for n in range(1, 4):
                        self.assertTrue(any('evidence-%d' % n in text for text in contents), (paths, contents))
                    self.assertGreaterEqual(len(paths), 3)

    def test_schema_rejection_reason_is_retained_after_successful_private_retry(self):
        original_run = subprocess.run
        for change in (False, True):
            with self.subTest(change=change):
                captured = {}
                def run(*args, **kwargs):
                    result = original_run(*args, **kwargs)
                    if args and args[0] == ['bash', 'run.sh']:
                        logs = Path(kwargs['cwd']) / '.uncle/workflow/logs'
                        captured.update({p.name: p.read_text() for p in logs.glob('*.log')})
                    return result
                harness = order.AttemptOrder()
                with patch.object(order.subprocess, 'run', side_effect=run):
                    rows = harness.run_driver(mode='writer-invalid', change=change)
                self.assertEqual(sum('edits-1' in row['stage'] for row in rows), 2)
                for name in ('UPDATED_PLAN.log', 'UPDATED_PLAN.speculative.log'):
                    self.assertIn(name, captured)
                    self.assertIn('B-999', captured[name])
                    self.assertRegex(captured[name], r'(?i)writer.*(?:reject|schema|invalid|unknown)')

    def test_failed_writer_reason_reaches_stage_and_speculative_logs(self):
        for change in (False, True):
            with self.subTest(change=change):
                root, result = self.run_writers(change)
                logs = root / '.uncle/workflow/logs'
                for name in ('UPDATED_PLAN.speculative.log', 'UPDATED_PLAN.log'):
                    path = logs / name
                    self.assertTrue(path.exists(), (name, result.stdout, result.stderr))
                    text = path.read_text()
                    self.assertRegex(text, r'(?i)writer.*(?:exit|status|code).*7')
                    self.assertGreaterEqual(len(text.splitlines()), 3)


if __name__ == '__main__':
    unittest.main()
