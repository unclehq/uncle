#!/usr/bin/env python3
"""Direct-HTTP document stages: schema injection, capability fallback, exploration."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/lib'))
import self_hosted_http as http_transport
import http_agent
from self_hosted import artifact_schema, reviewer_artifact_kind, run_opencode, OutputTruncated

PLAN = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': 'Do it.', 'verification_commands': 'true'}


class Raw(str):
    """A reply sent as-is rather than JSON-encoded."""


class Server:
    """Scripted OpenAI-compatible endpoint; `reject` names request fields it 400s on."""

    def __init__(self, reply, reject=(), version=None, tool_script=(), drop_after=0, redirect=False, delay=0):
        self.requests, self.reject, self.reply, self.version = [], set(reject), reply, version
        self.peers, self.drop_after, self.redirect, self.delay = [], drop_after, redirect, delay
        self.tool_script = list(tool_script)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'  # keep-alive, as real model servers speak it

            def log_message(self, *args):
                pass

            def send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.peers.append(self.client_address[1])
                if outer.version and self.path == outer.version[0]:
                    return self.send(200, {'version': '1.0'})
                if self.path.endswith('/models'):
                    return self.send(200, {'data': [{'id': 'm'}]})
                self.send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.peers.append(self.client_address[1])
                outer.requests.append((self.path, body))
                if outer.drop_after and len(outer.requests) == outer.drop_after:
                    # Answer, then close the socket without announcing it.
                    self.close_connection = True
                if outer.redirect:
                    self.send_response(302)
                    self.send_header('Location', 'http://127.0.0.1:1/')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if outer.reject & set(body) or (self.path == '/api/chat' and 'ollama' in outer.reject):
                    return self.send(400, {'error': 'unsupported'})
                if self.path == '/api/chat':
                    return self.send(200, {'message': {'content': json.dumps(outer.reply)}, 'done_reason': 'stop',
                                           'prompt_eval_count': 3, 'eval_count': 4})
                if outer.delay and body.get('tools'):
                    time.sleep(outer.delay)
                if body.get('tools') and outer.tool_script:
                    message = outer.tool_script.pop(0)
                else:
                    message = {'role': 'assistant', 'content': outer.reply if isinstance(outer.reply, Raw) else json.dumps(outer.reply)}
                self.send(200, {'choices': [{'message': message, 'finish_reason': 'stop'}],
                                'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:%d/v1' % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class SelfHostedHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='self hosted http ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        patcher = patch.dict(os.environ, {'UNCLE_OUTAGE_DIR': str(self.root)})     # an outage mark must not leak between tests
        patcher.start()
        self.addCleanup(patcher.stop)
        http_transport._capabilities.clear()
        http_transport.close_connections()
        self.addCleanup(http_transport.close_connections)
        # What the driver learns about the server is stored in the project; keep it in this test's.
        isolate = patch.dict(os.environ, {'UNCLE_PROJECT_ROOT': str(self.root)})
        isolate.start()
        self.addCleanup(isolate.stop)

    def serve(self, *args, **kwargs):
        server = Server(*args, **kwargs)
        self.addCleanup(server.close)
        return server

    def values(self, server):
        return {'base_url': server.url, 'model': 'm', 'api_key': 'k'}

    def plan(self, server, **kwargs):
        return http_agent.run_document(self.values(server), 'Plan', self.root, artifact_schema('plan'), 'plan', 4096, **kwargs)

    def final(self, server):
        return [body for path, body in server.requests if not body.get('tools')][-1]

    def test_schema_is_attached_as_response_format(self):
        # The model ends in prose, so the closing request is what carries the schema.
        server = self.serve(PLAN, tool_script=[{'role': 'assistant', 'content': 'finished'}])
        usage = {}
        text, turns = self.plan(server, usage=usage)
        self.assertEqual(json.loads(text), PLAN)
        body = self.final(server)
        self.assertEqual(body['response_format']['type'], 'json_schema')
        self.assertEqual(body['response_format']['json_schema']['schema'], artifact_schema('plan'))
        self.assertEqual((usage['constraint_mode'], usage['input_tokens'], usage['output_tokens']), ('json_schema', 20, 10))

    def test_a_valid_json_message_is_the_answer_and_is_not_generated_a_second_time(self):
        server = self.serve('unused', tool_script=[{'role': 'assistant', 'content': json.dumps(PLAN)}])
        usage = {}
        text, _ = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage=usage,
                                       final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(json.loads(text), PLAN)
        self.assertEqual([body for _path, body in server.requests if not body.get('tools')], [], 'a closing request was sent')
        self.assertIn('already valid', usage['constraint_mode'])

    def test_a_fenced_answer_with_prose_around_it_is_accepted_as_is(self):
        message = 'Here is the plan.\n\n```json\n' + json.dumps(PLAN, indent=2) + '\n```\nDone.'
        server = self.serve('unused', tool_script=[{'role': 'assistant', 'content': message}])
        text, _ = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage={},
                                       final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(json.loads(text), PLAN)
        self.assertEqual([body for _path, body in server.requests if not body.get('tools')], [])

    def test_newlines_in_the_models_own_answer_survive(self):
        plan = dict(PLAN, verification_commands='npm ci\nnpm test\nnpm run build')
        server = self.serve('unused', tool_script=[{'role': 'assistant', 'content': json.dumps(plan)}])
        text, _ = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage={},
                                       final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(json.loads(text)['verification_commands'].splitlines(), ['npm ci', 'npm test', 'npm run build'])

    def test_a_message_that_breaks_the_schema_still_gets_the_closing_request(self):
        broken = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': 'x'}   # no verification_commands
        server = self.serve(PLAN, tool_script=[{'role': 'assistant', 'content': json.dumps(broken)}])
        text, _ = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage={},
                                       final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(json.loads(text), PLAN)
        self.assertEqual(len([1 for _path, body in server.requests if not body.get('tools')]), 1)

    def test_a_message_that_is_only_prose_gets_the_closing_request(self):
        server = self.serve(PLAN, tool_script=[{'role': 'assistant', 'content': 'All done, the work is finished.'}])
        http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage={},
                             final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(len([1 for _path, body in server.requests if not body.get('tools')]), 1)

    def test_reasoning_text_in_think_tags_is_ignored_when_looking_for_the_answer(self):
        message = '<think>maybe {"schema": "decoy"}</think>' + json.dumps(PLAN)
        self.assertEqual(json.loads(http_agent.answer_already_given(message, artifact_schema('plan'))), PLAN)

    def test_final_call_defaults_to_temperature_zero_and_honours_override(self):
        server = self.serve(PLAN)
        self.plan(server, explore_first=False)
        self.assertEqual(self.final(server)['temperature'], 0.0)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_TEMPERATURE': '0.3'}):
            self.plan(server, explore_first=False)
        self.assertEqual(self.final(server)['temperature'], 0.3)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_TEMPERATURE': 'hot'}):
            with self.assertRaisesRegex(ValueError, 'must be a number'):
                self.plan(server, explore_first=False)
        ollama = self.serve(PLAN, version=('/api/version',))
        http_transport._capabilities.clear()
        self.plan(ollama, explore_first=False)
        self.assertEqual(ollama.requests[-1][1]['options']['temperature'], 0.0)

    def temperature_for(self, stage, env=None, config=None):
        directory = Path(tempfile.mkdtemp(dir=self.root))
        path = directory/'config'
        path.write_text(config or '', encoding='utf-8')
        clean = {k: v for k, v in os.environ.items() if not k.startswith('WORKFLOW_SELF_HOSTED_TEMPERATURE')}
        clean.update(env or {}, UNCLE_CONFIG=str(path), UNCLE_STATUS_STAGE=stage)
        with patch.dict(os.environ, clean, clear=True):
            return http_transport.temperature()

    def test_requirements_runs_at_temperature_one_and_everything_else_at_zero(self):
        for stage in ('requirements', 'requirements-investigate'):
            self.assertEqual(self.temperature_for(stage), 1.0, stage)
        for stage in ('project-plan', 'project-plan-investigate', 'implementation', 'adversarial-review-worker-security', ''):
            self.assertEqual(self.temperature_for(stage), 0.0, stage)

    def test_the_requirements_stage_sends_temperature_one_on_every_request(self):
        reply = {'schema': 'uncle.artifact/v1', 'kind': 'requirements-interpretation', 'sections': {
            key: 'text' for key in ('required_functionality', 'optional_functionality', 'constraints', 'user_visible_behaviors',
                                    'system_behaviors', 'failure_behaviors', 'ambiguities', 'assumptions', 'explicit_non_goals',
                                    'definition_of_done')}}
        server = self.serve(reply, tool_script=[self.call('list_dir', {}), {'role': 'assistant', 'content': 'read it'}])
        clean = {k: v for k, v in os.environ.items() if not k.startswith('WORKFLOW_SELF_HOSTED_TEMPERATURE')}
        clean.update(UNCLE_STATUS_STAGE='requirements-investigate', UNCLE_CONFIG=str(self.root/'none'))
        with patch.dict(os.environ, clean, clear=True):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage={},
                                 final_schema=artifact_schema('requirements-interpretation'), final_name='requirements_interpretation')
        sent = [body['temperature'] for path, body in server.requests if path.endswith('/chat/completions')]
        self.assertGreaterEqual(len(sent), 3)
        self.assertEqual(set(sent), {1.0})

    def test_temperature_is_configurable_per_stage(self):
        config = 'requirements.temperature 0.4\nimplementation.temperature 0.2\nself-hosted.temperature 0.1\n'
        self.assertEqual(self.temperature_for('requirements-investigate', config=config), 0.4)
        self.assertEqual(self.temperature_for('implementation', config=config), 0.2)
        self.assertEqual(self.temperature_for('implementation-step-3', config=config), 0.1)   # falls to the global row
        self.assertEqual(self.temperature_for('project-plan', config=config), 0.1)
        self.assertEqual(self.temperature_for('requirements', config='requirements.temperature 0  # off\n'), 0.0)

    def test_temperature_environment_overrides_win_in_order(self):
        config = 'requirements.temperature 0.4\n'
        self.assertEqual(self.temperature_for('requirements', env={'WORKFLOW_SELF_HOSTED_TEMPERATURE': '0.7'}, config=config), 0.7)
        self.assertEqual(self.temperature_for('requirements', env={'WORKFLOW_SELF_HOSTED_TEMPERATURE': '0.7',
                                                                   'WORKFLOW_SELF_HOSTED_TEMPERATURE_REQUIREMENTS': '1.5'}, config=config), 1.5)
        self.assertEqual(self.temperature_for('adversarial-review-worker-x', env={'WORKFLOW_SELF_HOSTED_TEMPERATURE_ADVERSARIAL_REVIEW': '0.3'}), 0.3)
        with self.assertRaisesRegex(ValueError, 'must be between 0 and 2'):
            self.temperature_for('requirements', config='requirements.temperature 3\n')
        with self.assertRaisesRegex(ValueError, 'must be a number'):
            self.temperature_for('requirements', env={'WORKFLOW_SELF_HOSTED_TEMPERATURE_REQUIREMENTS': 'hot'})

    def test_one_connection_is_reused_for_every_request(self):
        server = self.serve(PLAN, tool_script=[self.call('list_dir', {}, 'a'), self.call('list_dir', {}, 'b'),
                                               {'role': 'assistant', 'content': 'done'}])
        self.plan(server)
        self.assertGreaterEqual(len(server.peers), 4)  # probes, three tool turns, final answer
        self.assertEqual(len(set(server.peers[-5:])), 1, server.peers)
        self.assertIn('HTTP/1.1', http_transport.PROTOCOLS)

    def test_each_stage_run_uses_a_connection_of_its_own(self):
        server = self.serve(PLAN)
        policy = http_agent.Policy(self.root)
        for _ in range(2):
            http_agent.run_agent(self.values(server), 'Go.', policy, 4096, turns=1, usage={})
        first, second = server.peers[:len(server.peers) // 2], server.peers[len(server.peers) // 2:]
        self.assertEqual((len(set(first)), len(set(second))), (1, 1))
        self.assertNotEqual(first[0], second[0])

    def test_retries_within_a_stage_reuse_the_stage_connection(self):
        server = self.serve(PLAN)
        policy = http_agent.Policy(self.root)
        with http_transport.connection_scope():
            for _ in range(3):  # e.g. a format retry, then the next attempt
                http_agent.run_agent(self.values(server), 'Go.', policy, 4096, turns=1, usage={})
        self.assertEqual(len(set(server.peers)), 1, server.peers)

    def supervisor_turn(self, session, text):
        import io
        import queue
        progress = queue.Queue()
        log = io.BytesIO()
        lines = session.turn(text, log, __import__('time').monotonic() + 30, threading.Event(), progress)
        return lines, log.getvalue(), progress

    def test_supervisor_has_its_own_persistent_connection(self):
        import supervisor_runner
        server = self.serve(Raw('Hello operator.'))
        stage_connection = []
        session = supervisor_runner.SelfHostedSession(self.values(server))
        self.assertTrue(session.prime())
        with http_transport.connection_scope():  # a stage running at the same time
            http_transport._request(server.url + '/models', 'k')
            stage_connection.append(server.peers[-1])
        first, log, progress = self.supervisor_turn(session, 'Status?')
        second, _, _ = self.supervisor_turn(session, 'And now?')
        reply, usage, cost, error = supervisor_runner.parse_stream(first)
        self.assertEqual((reply, error, usage['input_tokens']), ('Hello operator.', '', 10))
        self.assertEqual(progress.get_nowait(), 'Hello operator.')
        self.assertIn(b'Hello operator.', log)
        supervisor_ports = {server.peers[0], server.peers[2], server.peers[3]}
        self.assertEqual(len(supervisor_ports), 1, server.peers)          # prime + both turns: one connection
        self.assertNotIn(stage_connection[0], supervisor_ports)           # the stage's was separate
        # Each prompt is complete, so each turn sends only its own prompt, at temperature 0.
        body = server.requests[-1][1]
        self.assertEqual([m['role'] for m in body['messages']], ['user'])
        self.assertEqual(body['temperature'], 0.0)
        self.assertNotIn('tools', body)
        session.close()
        self.assertFalse(session.alive())
        self.assertIsNone(self.supervisor_turn(session, 'late')[0])

    CHAT_PROMPT = 'contract...\n## Data (untrusted)\n{"operator_message": "status?", "workflow_state": {"stage": "preflight"}}'
    ENVELOPE = {'schema': 1, 'reply': 'Preflight is running.', 'steer': None, 'gate_answer': None, 'home_action': None,
                'runner_answer': None}

    def test_the_session_exposes_what_the_tui_reads_from_a_live_session(self):
        # uncle_tui reads session.command/env/home for the per-call fallback; a session without them
        # crashed every chat turn.
        import supervisor_runner
        server = self.serve(Raw('x'))
        session = supervisor_runner.SelfHostedSession(self.values(server))
        command, env, home = session.command, session.env, session.home
        self.assertIsInstance(command, list)
        self.assertIsInstance(env, dict)
        self.assertTrue(os.path.isdir(home))
        fallback = (['agent', '-p'], {'A': '1'}, str(self.root))
        self.assertEqual((lambda s: (s.command, s.env, s.home))(supervisor_runner.SelfHostedSession(self.values(server), fallback=fallback)), fallback)

    def test_a_chat_turn_is_answered_under_the_reply_envelope_schema(self):
        import supervisor_runner, supervisor_chat
        server = self.serve(self.ENVELOPE)
        session = supervisor_runner.SelfHostedSession(self.values(server), reply_schema=supervisor_chat.REPLY_SCHEMA)
        lines, _, progress = self.supervisor_turn(session, self.CHAT_PROMPT)
        body = server.requests[-1][1]
        self.assertEqual(body['response_format']['json_schema']['schema'], supervisor_chat.REPLY_SCHEMA)
        self.assertIn('single line', body['messages'][0]['content'])
        reply, _usage, _cost, error = supervisor_runner.parse_stream(lines)
        self.assertEqual(error, '')
        self.assertEqual(supervisor_chat.parse_reply(reply)['reply'], 'Preflight is running.')
        self.assertEqual(json.loads(progress.get_nowait()), self.ENVELOPE)

    def test_the_whole_chat_path_runs_through_a_chat_request(self):
        import supervisor_runner, supervisor_chat
        server = self.serve(dict(self.ENVELOPE, steer={'text': 'Please add tests.'}))
        session = supervisor_runner.SelfHostedSession(self.values(server), reply_schema=supervisor_chat.REPLY_SCHEMA)
        request = supervisor_chat.ChatRequest(session.command, self.CHAT_PROMPT, session.env, session.home,
                                              str(self.root/'chat.jsonl'), {'deadline': 30}, session=session)
        outcome = request.result(wait=True)
        self.assertEqual(outcome['status'], 'reply', outcome)
        self.assertEqual(supervisor_chat.parse_reply(outcome['reply'])['steer'], {'text': 'Please add tests.'})

    def test_only_chat_prompts_are_constrained_to_the_envelope(self):
        import supervisor_runner, supervisor_chat
        server = self.serve(Raw('{"schema":1,"diagnosis":"d"}'))
        session = supervisor_runner.SelfHostedSession(self.values(server), reply_schema=supervisor_chat.REPLY_SCHEMA)
        self.supervisor_turn(session, 'A workflow diagnosis request with its own envelope.')
        self.assertNotIn('response_format', server.requests[-1][1])
        self.assertTrue(session.alive())

    def test_a_cut_off_grammar_answer_is_retried_without_the_grammar(self):
        import supervisor_runner, supervisor_chat
        server = self.serve('x')
        modes = []
        def fake(values, messages, schema, name, mode, limit, effort, timeout):
            modes.append(mode)
            if mode == 'json_schema':
                return '\n \n', 'length', {}
            return json.dumps(self.ENVELOPE), 'stop', {'prompt_tokens': 5, 'completion_tokens': 9}
        session = supervisor_runner.SelfHostedSession(self.values(server), reply_schema=supervisor_chat.REPLY_SCHEMA)
        with patch.object(http_transport, '_final_call', fake):
            lines, _, _ = self.supervisor_turn(session, self.CHAT_PROMPT)
        self.assertEqual(modes, ['json_schema', 'prompt'])
        self.assertEqual(supervisor_chat.parse_reply(supervisor_runner.parse_stream(lines)[0])['reply'], 'Preflight is running.')

    def test_a_reply_that_breaks_the_envelope_does_not_end_the_session(self):
        import supervisor_runner, supervisor_chat
        server = self.serve(Raw('Sorry, here is some prose.'))
        session = supervisor_runner.SelfHostedSession(self.values(server))      # no schema: plain text comes back
        lines, _, _ = self.supervisor_turn(session, self.CHAT_PROMPT)
        self.assertIsNotNone(lines)
        self.assertTrue(session.alive())
        with self.assertRaisesRegex(ValueError, 'malformed'):
            supervisor_chat.parse_reply(supervisor_runner.parse_stream(lines)[0])   # the TUI reports it; the session lives on

    def test_two_supervisors_do_not_share_a_connection(self):
        import supervisor_runner
        server = self.serve(Raw('ok'))
        sessions = [supervisor_runner.SelfHostedSession(self.values(server)) for _ in range(2)]
        for session in sessions:
            self.supervisor_turn(session, 'hi')
            self.supervisor_turn(session, 'again')
        self.assertEqual(len(set(server.peers)), 2)
        for session in sessions:
            session.close()

    def test_a_failed_supervisor_turn_ends_the_session_so_the_caller_falls_back(self):
        import supervisor_runner
        server = self.serve(Raw('ok'), reject={'messages'})
        session = supervisor_runner.SelfHostedSession(self.values(server))
        self.assertIsNone(self.supervisor_turn(session, 'hi')[0])
        self.assertFalse(session.alive())

    def test_a_subagent_does_not_share_its_parents_connection(self):
        server = self.serve(PLAN)
        url = server.url + '/chat/completions'
        with http_transport.connection_scope() as parent:
            http_transport._request(url, 'k', {'x': 1})
            with http_transport.connection_scope() as child:
                http_transport._request(url, 'k', {'x': 1})
                http_transport._request(url, 'k', {'x': 1})
            self.assertEqual(child.http1, {})            # closed with its scope
            http_transport._request(url, 'k', {'x': 1})  # parent carries on
            self.assertEqual(len(parent.http1), 1)
        parent_port, child_port = server.peers[0], server.peers[1]
        self.assertEqual(server.peers, [parent_port, child_port, child_port, parent_port])
        self.assertNotEqual(parent_port, child_port)
        self.assertEqual(parent.http1, {})

    def test_threads_never_share_connections(self):
        server = self.serve(PLAN)
        url = server.url + '/chat/completions'
        ports = []
        def work():
            with http_transport.connection_scope():
                http_transport._request(url, 'k', {'x': 1})
                http_transport._request(url, 'k', {'x': 1})
        threads = [threading.Thread(target=work) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(server.peers), 6)
        self.assertEqual(len(set(server.peers)), 3)

    def test_tool_turns_have_a_small_output_cap_and_a_bounded_wait(self):
        # A non-streamed turn with the stage-wide 64k cap could run for most of an hour
        # before the server answered: that is what a hung preflight looked like.
        server = self.serve(PLAN, tool_script=[self.call('list_dir', {}), {'role': 'assistant', 'content': 'done'}])
        http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, usage={})
        turns = [body for _path, body in server.requests if body.get('tools')]
        self.assertEqual({body['max_tokens'] for body in turns}, {32768})
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_TURN_OUTPUT_TOKENS': '2048'}):
            self.assertEqual(http_transport.turn_output_tokens(64512), 2048)
        self.assertEqual(http_transport.turn_output_tokens(1000), 1000)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WORKFLOW_SELF_HOSTED_REQUEST_SECONDS', None)
            self.assertEqual(http_transport.request_seconds(3600), 1200)
            self.assertEqual(http_transport.request_seconds(300), 300)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_REQUEST_SECONDS': '90'}):
            self.assertEqual(http_transport.request_seconds(3600), 90)

    def test_a_model_that_never_answers_fails_with_a_readable_error(self):
        server = self.serve(PLAN)
        def silent(*args, **kwargs):
            raise TimeoutError('timed out')
        with patch.object(http_transport, '_request', silent):
            with self.assertRaisesRegex(ValueError, r'did not answer within 1200 seconds.*runaway generation'):
                http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, usage={})
            with self.assertRaisesRegex(ValueError, 'did not answer within'):
                http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                                     final_schema=artifact_schema('plan'), final_name='plan')

    def test_a_connection_the_server_closed_while_idle_is_reopened_once(self):
        server = self.serve(PLAN, drop_after=1)
        values = self.values(server)
        url = server.url + '/chat/completions'
        for _ in range(3):
            self.assertEqual(http_transport._request(url, 'k', {'x': 1})['choices'][0]['finish_reason'], 'stop')
        self.assertEqual(len(server.requests), 3)
        self.assertGreater(len(set(server.peers)), 1)

    def test_redirects_are_refused_not_followed(self):
        server = self.serve(PLAN, redirect=True)
        with self.assertRaises(http_transport.HTTPError) as caught:
            http_transport._request(server.url + '/chat/completions', 'k', {'x': 1})
        self.assertEqual(caught.exception.code, 302)

    def test_connection_failures_name_the_server_and_the_likely_cause(self):
        import socket
        # Refused: nothing is listening.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        with self.assertRaises(http_transport.ServerUnreachable) as caught:
            http_transport._request('http://127.0.0.1:%d/v1/models' % port, 'k', timeout=5)
        self.assertIn('127.0.0.1:%d' % port, str(caught.exception))
        self.assertIn('connection refused', str(caught.exception))
        self.assertIn('VPN', str(caught.exception))
        # Timed out: the OS gave up (macOS errno 60), as on a dropped VPN.
        import errno
        with patch('http.client.HTTPConnection.connect', side_effect=OSError(errno.ETIMEDOUT, 'Operation timed out')):
            with self.assertRaisesRegex(http_transport.ServerUnreachable, r'10\.10\.5\.123:11435 \(timed out\)'):
                http_transport._request('http://10.10.5.123:11435/v1/models', 'k', timeout=3600)

    def test_connecting_has_its_own_short_timeout(self):
        seen = []
        real = http_transport.http.client.HTTPConnection.connect
        def spy(connection):
            seen.append(connection.timeout)
            raise TimeoutError('timed out')
        with patch('http.client.HTTPConnection.connect', spy):
            with self.assertRaises(http_transport.ServerUnreachable):
                http_transport._request('http://10.10.5.123:11435/v1/models', 'k', timeout=3600)
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_CONNECT_SECONDS': '3'}):
                with self.assertRaises(http_transport.ServerUnreachable):
                    http_transport._request('http://10.10.5.123:11435/v1/models', 'k', timeout=3600)
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_CONNECT_SECONDS': 'soon'}):
                with self.assertRaisesRegex(ValueError, 'CONNECT_SECONDS'):
                    http_transport._request('http://10.10.5.123:11435/v1/models', 'k')
        self.assertEqual(seen, [15.0, 3.0])

    def test_a_slow_answer_still_gets_the_long_request_timeout(self):
        server = self.serve(PLAN)
        with http_transport.connection_scope() as pool:
            http_transport._request(server.url + '/models', 'k', timeout=1234)
            (connection,) = pool.http1.values()
            self.assertEqual(connection.sock.gettimeout(), 1234)

    def test_a_lost_network_is_ridden_out_not_fatal(self):
        # Preflight "hung": the VPN dropped, three workers sat on dead sockets, and when
        # the failure finally came it ended the stage.  A request now retries a lost
        # network for a bounded time.
        calls = []
        def flaky(url, key, body, timeout):
            calls.append(url)
            if len(calls) <= 2:
                raise http_transport.ServerUnreachable('Cannot reach the model server at http://x (timed out).')
            return {'ok': True}
        with patch.object(http_transport, '_request', flaky), patch.object(http_transport.time, 'sleep', lambda s: None), \
                patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_RECONNECT_SECONDS': '600'}):
            self.assertEqual(http_transport.post('http://x/v1/chat/completions', 'k', {}, 30), {'ok': True})
        self.assertEqual(len(calls), 3)

    def test_a_connection_that_dies_mid_request_is_retried_too(self):
        calls = []
        def dies_once(url, key, body, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise http_transport.NetworkLost('The connection to the model server was lost (reset).')
            return {'ok': True}
        with patch.object(http_transport, '_request', dies_once), patch.object(http_transport.time, 'sleep', lambda s: None):
            self.assertEqual(http_transport.post('http://x/v1/chat/completions', 'k', {}, 30), {'ok': True})

    def test_a_network_that_stays_down_fails_with_how_long_it_was_tried(self):
        def down(url, key, body, timeout):
            raise http_transport.ServerUnreachable('Cannot reach the model server at http://x (timed out).')
        ticks = iter(range(0, 10000, 100))
        with patch.object(http_transport, '_request', down), patch.object(http_transport.time, 'sleep', lambda s: None), \
                patch.object(http_transport.time, 'monotonic', lambda: next(ticks)), \
                patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_RECONNECT_SECONDS': '250'}):
            with self.assertRaisesRegex(http_transport.ServerUnreachable, r'network stayed down for \d+ seconds'):
                http_transport.post('http://x/v1/chat/completions', 'k', {}, 30)

    def test_a_server_already_waited_out_is_not_waited_for_again_until_it_answers(self):
        # calculator-local: eleven writers waited five minutes each, then the one-call fallback waited five more for the same host
        url = 'http://outage-test.invalid:9/v1/chat/completions'
        http_transport._outage_mark(url, clear=True)
        calls = []
        def down(u, key, body, timeout):
            calls.append(1)
            raise http_transport.ServerUnreachable('Cannot reach the model server at http://outage-test.invalid:9 (timed out).')
        ticks = iter(range(0, 100000, 100))
        try:
            with patch.object(http_transport, '_request', down), patch.object(http_transport.time, 'sleep', lambda s: None), \
                    patch.object(http_transport.time, 'monotonic', lambda: next(ticks)), \
                    patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_RECONNECT_SECONDS': '250'}):
                with self.assertRaises(http_transport.ServerUnreachable):
                    http_transport.post(url, 'k', {}, 30)         # waits out its budget, and leaves the mark
                first = len(calls)
                self.assertGreater(first, 1)
                with self.assertRaises(http_transport.ServerUnreachable):
                    http_transport.post(url, 'k', {}, 30)         # the next call fails on its first attempt
                self.assertEqual(len(calls), first + 1)
            with patch.object(http_transport, '_request', lambda *a: {'ok': True}):
                self.assertEqual(http_transport.post(url, 'k', {}, 30), {'ok': True})    # it answered: the mark is gone
            self.assertFalse(http_transport._outage_recent(url))
        finally:
            http_transport._outage_mark(url, clear=True)

    def test_a_server_that_answered_or_never_does_is_not_retried(self):
        calls = []
        def answers(url, key, body, timeout):
            calls.append(1)
            raise http_transport.HTTPError(url, 500, 'boom', {}, None)
        with patch.object(http_transport, '_request', answers):
            with self.assertRaises(http_transport.HTTPError):
                http_transport.post('http://x/v1/chat/completions', 'k', {}, 30)
        self.assertEqual(len(calls), 1)
        calls.clear()
        def silent(url, key, body, timeout):
            calls.append(1)
            raise TimeoutError('timed out')
        with patch.object(http_transport, '_request', silent):
            with self.assertRaises(TimeoutError):
                http_transport.post('http://x/v1/chat/completions', 'k', {}, 30)
        self.assertEqual(len(calls), 1)

    def test_network_errors_are_told_apart_from_a_slow_server(self):
        import errno as errno_module
        lost = http_transport._failure('http://x/', ConnectionResetError(errno_module.ECONNRESET, 'reset'))
        self.assertIsInstance(lost, http_transport.NetworkLost)
        self.assertIsInstance(http_transport._failure('http://x/', OSError(errno_module.ETIMEDOUT, 'Operation timed out')),
                              http_transport.NetworkLost)
        self.assertIsInstance(http_transport._failure('http://x/', OSError(errno_module.EHOSTUNREACH, 'no route')),
                              http_transport.NetworkLost)
        slow = http_transport._failure('http://x/', TimeoutError('timed out'))   # a read that simply got no answer
        self.assertNotIsInstance(slow, http_transport.NetworkLost)
        self.assertIsInstance(slow, TimeoutError)

    def test_sockets_are_tuned_to_notice_a_dead_path(self):
        import socket as socket_module
        with socket_module.socket() as sock:
            http_transport.tune_socket(sock)
            self.assertEqual(sock.getsockopt(socket_module.SOL_SOCKET, socket_module.SO_KEEPALIVE) != 0, True)
            for name in ('TCP_KEEPIDLE', 'TCP_KEEPALIVE'):
                if hasattr(socket_module, name):
                    self.assertEqual(sock.getsockopt(socket_module.IPPROTO_TCP, getattr(socket_module, name)), 30)
        server = self.serve(PLAN)
        with http_transport.connection_scope() as pool:
            http_transport._request(server.url + '/models', 'k')
            (connection,) = pool.http1.values()
            self.assertNotEqual(connection.sock.getsockopt(socket_module.SOL_SOCKET, socket_module.SO_KEEPALIVE), 0)

    def test_the_model_is_warned_when_three_turns_are_left(self):
        # A repair stage spent all 40 turns probing, ended with an empty message, and the run stopped.
        seen = []
        def scripted(values, messages, tools, limit, effort, timeout):
            seen.append(([m['content'] for m in messages if m['role'] == 'user'], bool(tools)))
            if tools:
                return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'id': 'c%d' % len(seen), 'type': 'function', 'function': {'name': 'list_dir', 'arguments': '{}'}}]},
                    'finish_reason': 'tool_calls'}], 'usage': {}}
            return {'choices': [{'message': {'role': 'assistant', 'content': 'wrapped up'}, 'finish_reason': 'stop'}], 'usage': {}}
        server = self.serve('x')
        with patch.object(http_agent, 'chat', scripted):
            text, _ = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, turns=8, usage={})
        self.assertEqual(text, 'wrapped up')
        warnings = [i for i, (users, _) in enumerate(seen) if any('3 tool turns left' in u for u in users)]
        self.assertEqual(warnings[0], 5)                         # the 6th request of 8 is the first to carry it
        self.assertEqual(sum(1 for u in seen[-1][0] if '3 tool turns left' in u), 1)   # and it is said only once

    def test_a_short_budget_is_not_nagged(self):
        seen = []
        def scripted(values, messages, tools, limit, effort, timeout):
            seen.append(' '.join(m['content'] for m in messages if m['role'] == 'user'))
            return {'choices': [{'message': {'role': 'assistant', 'content': 'done'}, 'finish_reason': 'stop'}], 'usage': {}}
        server = self.serve('x')
        with patch.object(http_agent, 'chat', scripted):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, turns=4, usage={})
        self.assertNotIn('tool turns left', seen[-1])

    def test_an_empty_closing_message_after_the_budget_is_asked_for_once_more(self):
        replies = iter(['', 'Found the cause: the display is an input element.'])
        calls = []
        def scripted(values, messages, tools, limit, effort, timeout):
            calls.append(bool(tools))
            if tools:
                return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'id': 'c%d' % len(calls), 'type': 'function', 'function': {'name': 'list_dir', 'arguments': '{}'}}]},
                    'finish_reason': 'tool_calls'}], 'usage': {}}
            return {'choices': [{'message': {'role': 'assistant', 'content': next(replies)}, 'finish_reason': 'stop'}], 'usage': {}}
        server = self.serve('x')
        with patch.object(http_agent, 'chat', scripted):
            text, _ = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, turns=3, usage={})
        self.assertEqual(text, 'Found the cause: the display is an input element.')
        self.assertEqual(calls, [True, True, True, False, False])

    def test_the_stage_result_names_the_model_api_as_its_usage_source(self):
        import subprocess
        server = self.serve('x', tool_script=[{'role': 'assistant', 'content': 'All done.'}])
        config = self.root/'.uncle'/'config'
        config.parent.mkdir(exist_ok=True)
        config.write_text('implementation.runner self-hosted\nimplementation.model local/m\n', encoding='utf-8')
        env = dict(os.environ, UNCLE_CONFIG=str(config), UNCLE_STATUS_STAGE='implementation', UNCLE_SELF_HOSTED_BASE_URL=server.url,
                   UNCLE_SELF_HOSTED_MODEL='m', UNCLE_SELF_HOSTED_API_KEY='k', WORKFLOW_SELF_HOSTED_TRANSPORT='http')
        env.pop('UNCLE_STEERING', None)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/lib/self_hosted.py'), 'agent', '-p'], input='Do it.',
                                text=True, capture_output=True, cwd=self.root, env=env, timeout=60)
        final = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"type": "result"')][-1]
        self.assertEqual(final['usage_source'], 'Model API usage')

    def test_unreachable_server_is_an_oserror(self):
        with self.assertRaises(OSError):
            http_transport._request('http://127.0.0.1:1/v1/models', 'k', timeout=2)

    def test_http2_policy(self):
        with patch.object(http_transport, 'http2_available', lambda: True):
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_HTTP2': 'auto'}):
                self.assertTrue(http_transport.wants_http2('https'))
                self.assertFalse(http_transport.wants_http2('http'))
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_HTTP2': 'h2c'}):
                self.assertTrue(http_transport.wants_http2('http'))
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_HTTP2': 'off'}):
                self.assertFalse(http_transport.wants_http2('https'))
            with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_HTTP2': 'sometimes'}):
                with self.assertRaisesRegex(ValueError, 'auto, off or h2c'):
                    http_transport.wants_http2('https')
        with patch.object(http_transport, 'http2_available', lambda: False):
            self.assertFalse(http_transport.wants_http2('https'))

    def test_falls_back_to_json_object_then_prompt_only(self):
        server = self.serve(PLAN, reject={'structured_outputs', 'guided_json'})
        server.reject = set()
        calls = []
        original = server.reply

        class Rejects(dict):
            pass
        # Reject json_schema specifically: response_format with that type.
        handler_post = server.httpd.RequestHandlerClass.do_POST

        def post(handler):
            length = int(handler.headers['Content-Length'])
            raw = handler.rfile.read(length)
            body = json.loads(raw)
            calls.append(body)
            fmt = (body.get('response_format') or {}).get('type')
            if fmt == 'json_schema':
                return handler.send(400, {'error': 'unsupported'})
            data = {'choices': [{'message': {'role': 'assistant', 'content': json.dumps(original)}, 'finish_reason': 'stop'}], 'usage': {}}
            handler.send(200, data)
        server.httpd.RequestHandlerClass.do_POST = post
        self.addCleanup(setattr, server.httpd.RequestHandlerClass, 'do_POST', handler_post)
        usage = {}
        self.plan(server, usage=usage, explore_first=False)
        self.assertEqual(usage['constraint_mode'], 'json_object')
        self.assertEqual([(c.get('response_format') or {}).get('type') for c in calls], ['json_schema', 'json_object'])
        # The refusal is remembered for the next stage.
        calls.clear()
        self.plan(server, explore_first=False)
        self.assertEqual([(c.get('response_format') or {}).get('type') for c in calls], ['json_object'])

    def test_ollama_uses_native_format_with_the_schema(self):
        server = self.serve(PLAN, version=('/api/version',))
        # Ollama serves its version at the server root; the /v1 suffix is not part of it.
        usage = {}
        self.plan(server, usage=usage, explore_first=False)
        path, body = server.requests[-1]
        self.assertEqual(path, '/api/chat')
        self.assertEqual(body['format'], artifact_schema('plan'))
        self.assertEqual(usage['constraint_mode'], 'ollama_format')

    def test_ollama_falls_back_when_native_endpoint_is_refused(self):
        server = self.serve(PLAN, version=('/api/version',), reject={'ollama'})
        usage = {}
        self.plan(server, usage=usage, explore_first=False)
        self.assertEqual(usage['constraint_mode'], 'json_schema')

    def test_vllm_detected_and_schema_enforced(self):
        server = self.serve(PLAN, version=('/version',))
        self.plan(server, explore_first=False)
        self.assertEqual(http_transport.capabilities(server.url, 'k')['flavor'], 'vllm')
        self.assertEqual(self.final(server)['response_format']['type'], 'json_schema')

    def test_every_form_refused_is_a_clear_error(self):
        server = self.serve(PLAN, reject={'max_tokens'})
        with self.assertRaisesRegex(ValueError, 'rejected every request form'):
            self.plan(server, explore_first=False)

    def test_response_violating_the_schema_is_rejected(self):
        server = self.serve({'schema': 'uncle.artifact/v1', 'kind': 'plan', 'narrative': 'x'})
        with self.assertRaisesRegex(ValueError, 'violates the artifact schema.*verification_commands'):
            self.plan(server, explore_first=False)
        server = self.serve('not an object')
        with self.assertRaisesRegex(ValueError, 'violates the artifact schema'):
            self.plan(server, explore_first=False)

    def test_truncation_is_reported_as_such(self):
        server = self.serve(PLAN)
        original = http_transport._final_call
        with patch.object(http_transport, '_final_call', lambda *a: (json.dumps(PLAN)[:10], 'length', {})):
            with self.assertRaises(OutputTruncated):
                self.plan(server, explore_first=False)
        self.assertIs(http_transport._final_call, original)

    def test_a_truncated_answer_is_kept_for_diagnosis(self):
        server = self.serve(PLAN)
        partial = '{"schema": "uncle.artifact/v1", "narrative": "' + 'x' * 500
        with patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'updated-plan'}), \
             patch.object(http_transport, '_final_call', lambda *a: (partial, 'length', {'output_tokens': 7})):
            with self.assertRaises(OutputTruncated) as caught:
                self.plan(server, explore_first=False)
        saved = sorted((self.root / '.uncle/workflow/logs').glob('truncated-updated-plan-final-*.txt'))
        self.assertTrue(saved, 'no partial output was kept')
        self.assertIn(str(saved[-1]), str(caught.exception))
        text = saved[-1].read_text(encoding='utf-8')
        self.assertIn('stage: updated-plan', text)
        self.assertIn('output cap:', text)
        self.assertIn(partial, text)

    def test_a_truncated_tool_turn_keeps_its_half_written_call(self):
        call = {'id': 'a', 'type': 'function', 'function': {'name': 'write_file', 'arguments': '{"path": "x.md", "content": "half'}}
        server = self.serve(PLAN, tool_script=[{'role': 'assistant', 'content': 'writing', 'tool_calls': [call]}])
        body = server.httpd.RequestHandlerClass
        original = http_transport.chat
        def length(values, messages, tools, limit, effort, timeout):
            data = original(values, messages, tools, limit, effort, timeout)
            data['choices'][0]['finish_reason'] = 'length'
            return data
        with patch.object(http_agent, 'chat', length), patch.dict(os.environ, {'UNCLE_STATUS_STAGE': 'updated-plan'}):
            with self.assertRaises(OutputTruncated):
                http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, usage={})
        saved = sorted((self.root / '.uncle/workflow/logs').glob('truncated-updated-plan-turn-*.txt'))
        self.assertTrue(saved)
        text = saved[-1].read_text(encoding='utf-8')
        self.assertIn('partial tool call: write_file', text)
        self.assertIn('"content": "half', text)

    def test_exploration_reads_project_files_then_schema_final(self):
        (self.root/'notes.txt').write_text('alpha\nbeta\n', encoding='utf-8')
        (self.root/'.env').write_text('SECRET=1\n', encoding='utf-8')
        call = lambda name, args, ident: {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
        server = self.serve(PLAN, tool_script=[call('read_file', {'path': 'notes.txt'}, 'a'),
                                               call('read_file', {'path': '.env'}, 'b'),
                                               call('read_file', {'path': '../escape'}, 'c'),
                                               {'role': 'assistant', 'content': 'done'}])
        self.plan(server)
        tool_results = [m['content'] for m in self.final(server)['messages'] if m['role'] == 'tool']
        self.assertEqual(tool_results[0], '1\talpha\n2\tbeta')
        self.assertTrue(tool_results[1].startswith('error:'))
        self.assertIn('outside the project', tool_results[2])
        self.assertNotIn('SECRET', json.dumps(server.requests))
        self.assertEqual(self.final(server)['response_format']['type'], 'json_schema')

    def test_server_without_tool_calling_still_delivers(self):
        server = self.serve(PLAN, reject={'tools'})
        text, _ = self.plan(server)
        self.assertEqual(json.loads(text), PLAN)

    def test_grep_and_list_dir_stay_inside_the_project(self):
        (self.root/'a.py').write_text('needle = 1\n', encoding='utf-8')
        self.assertEqual(http_agent.run_tool(http_agent.Policy(self.root), 'grep', {'pattern': 'needle'}), 'a.py:1:needle = 1')
        self.assertIn('a.py', http_agent.run_tool(http_agent.Policy(self.root), 'list_dir', {}))
        self.assertIn('outside the project', http_agent.run_tool(http_agent.Policy(self.root), 'list_dir', {'path': '/'}))

    def test_schemas_enforce_the_documented_contracts(self):
        updated = artifact_schema('plan', protected=True)
        self.assertIn('protected_verification_paths', updated['required'])
        self.assertIn('dispositions', updated['properties'])
        self.assertNotIn('dispositions', artifact_schema('plan')['properties'])
        with self.assertRaisesRegex(ValueError, 'one of'):
            http_transport.conforms({'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': 'n',
                                     'dispositions': [{'finding': 'AR-1', 'disposition': 'Maybe', 'reason': 'r', 'plan_change': 'p'}]},
                                    artifact_schema('change-plan', require_dispositions=True))
        with self.assertRaisesRegex(ValueError, 'dispositions'):
            http_transport.conforms({'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'narrative': 'n'},
                                    artifact_schema('change-plan', require_dispositions=True))
        sections = artifact_schema('requirements-interpretation')['properties']['sections']
        self.assertEqual(len(sections['required']), 10)

    def test_every_string_and_array_in_a_schema_is_bounded(self):
        def unbounded(schema, where='$'):
            found = []
            if schema.get('type') == 'string' and 'maxLength' not in schema and 'const' not in schema:
                found.append(where)
            if schema.get('type') == 'array' and 'maxItems' not in schema:
                found.append(where)
            for key, sub in schema.get('properties', {}).items():
                found += unbounded(sub, where + '.' + key)
            if isinstance(schema.get('items'), dict):
                found += unbounded(schema['items'], where + '[]')
            return found
        from self_hosted import REVIEWER_SCHEMAS
        kinds = list(REVIEWER_SCHEMAS) + ['requirements-interpretation', 'plan', 'change-plan', 'change-planning-bundle']
        for kind in kinds:
            self.assertEqual(unbounded(artifact_schema(kind)), [], kind)
        self.assertEqual(artifact_schema('plan')['properties']['narrative']['maxLength'], 60000)
        self.assertLess(artifact_schema('adversarial-review-worker-packet')['properties']['findings']['maxItems'], 100)

    def test_a_worker_packet_cannot_hold_a_runaway_of_findings(self):
        schema = artifact_schema('adversarial-review-worker-packet')
        items = schema['properties']['findings']
        self.assertEqual(items['maxItems'], 8)
        self.assertEqual(items['items']['properties']['summary']['maxLength'], 400)
        # 8 findings at the largest allowed size is far below the worker-packet cap (8192 tokens).
        biggest = 8 * (60 + 400 + 700 + 100)
        self.assertLess(biggest / 3, 8192)

    def test_whitespace_runaway_in_the_grammar_is_retried_without_it(self):
        server = self.serve(PLAN)
        calls = []
        def fake(values, messages, schema, name, mode, limit, effort, timeout):
            calls.append((mode, limit))
            if mode == 'json_schema':
                return '\n' * 5000, 'length', {'prompt_tokens': 1, 'completion_tokens': 8192}
            return json.dumps(PLAN), 'stop', {'prompt_tokens': 1, 'completion_tokens': 40}
        usage = {}
        with patch.object(http_transport, '_final_call', fake):
            text, _ = self.plan(server, explore_first=False, usage=usage)
        self.assertEqual(json.loads(text), PLAN)
        self.assertEqual([mode for mode, _ in calls], ['json_schema', 'prompt'])
        self.assertEqual(usage['constraint_mode'], 'prompt')
        self.assertEqual(usage['output_tokens'], 8192 + 40)

    def test_a_second_cutoff_reports_whitespace_plainly(self):
        server = self.serve(PLAN)
        with patch.object(http_transport, '_final_call', lambda *a: ('  \n\n  ', 'length', {})):
            with self.assertRaisesRegex(OutputTruncated, r'ended with: \(only whitespace\)'):
                self.plan(server, explore_first=False)

    def test_worker_packets_get_a_small_closing_cap(self):
        server = self.serve({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet', 'findings': []})
        http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                             final_schema=artifact_schema('adversarial-review-worker-packet'),
                             final_name='adversarial_review_worker_packet')
        # The grammar-constrained try is capped lower than the unconstrained retry.
        self.assertEqual(self.final(server)['max_tokens'], 4096)

    def test_a_worker_packet_asks_for_compact_json_and_retries_with_the_full_cap(self):
        server = self.serve({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet', 'findings': []})
        caps = []
        def fake(values, messages, schema, name, mode, limit, effort, timeout):
            caps.append((mode, limit, messages[-1]['content']))
            if mode == 'json_schema':
                return '\n   \n', 'length', {}
            return json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet', 'findings': []}), 'stop', {}
        with patch.object(http_transport, '_final_call', fake):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                                 final_schema=artifact_schema('adversarial-review-worker-packet'),
                                 final_name='adversarial_review_worker_packet')
        self.assertEqual([(m, l) for m, l, _ in caps], [('json_schema', 4096), ('prompt', 8192)])
        self.assertIn('Write it compactly', caps[0][2])

    def test_a_server_that_keeps_looping_on_whitespace_skips_the_grammar_for_packets(self):
        calls = []
        def fake(values, messages, schema, name, mode, limit, effort, timeout):
            calls.append(mode)
            if name == 'plan':
                return json.dumps(PLAN), 'stop', {}
            if mode == 'json_schema':
                return '', 'length', {}
            return json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet', 'findings': []}), 'stop', {}
        server = self.serve('x')
        def run():
            with patch.object(http_transport, '_final_call', fake):
                http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                                     final_schema=artifact_schema('adversarial-review-worker-packet'),
                                     final_name='adversarial_review_worker_packet')
        for _ in range(2):
            run()
        self.assertEqual(calls, ['json_schema', 'prompt', 'json_schema', 'prompt'])   # two wasted tries recorded
        calls.clear()
        run()
        self.assertEqual(calls, ['prompt'])                                           # now it skips straight there
        health = json.loads((self.root/'.uncle/workflow/constraint-health.json').read_text(encoding='utf-8'))
        self.assertEqual(list(health.values())[0]['whitespace_runaways'], 2)
        # Other kinds of answer still use the grammar.
        calls.clear()
        with patch.object(http_transport, '_final_call', fake):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                                 final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(calls[0], 'json_schema')

    def test_a_long_run_of_trailing_whitespace_is_recorded_as_a_runaway(self):
        server = self.serve('x')
        looped = '{"schema":"uncle.artifact/v1","kind":"plan","dispositions":[]' + '\n  \t' * 1500
        def fake(values, messages, schema, name, mode, limit, effort, timeout):
            if mode == 'json_schema':
                return looped, 'length', {}
            return json.dumps(PLAN), 'stop', {}
        with patch.object(http_transport, '_final_call', fake):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                                 final_schema=artifact_schema('plan'), final_name='plan')
        health = json.loads((self.root/'.uncle/workflow/constraint-health.json').read_text(encoding='utf-8'))
        self.assertEqual(list(health.values())[0]['whitespace_runaways'], 1)

    def test_truncated_closing_answer_reports_how_it_ended(self):
        server = self.serve(PLAN)
        with patch.object(http_transport, '_final_call', lambda *a: ('{"findings":[' + '{"id":"AR-1"},' * 400, 'length', {})):
            with self.assertRaisesRegex(OutputTruncated, r'ended with: .*"id":"AR-1"'):
                self.plan(server, explore_first=False)

    def test_a_runaway_repetition_violates_the_bounds(self):
        schema = artifact_schema('adversarial-review-worker-packet')
        finding = {'id': 'AR-1', 'summary': 'x'}
        with self.assertRaisesRegex(ValueError, 'more than'):
            http_transport.conforms({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet',
                                     'findings': [finding] * 500}, schema)
        with self.assertRaisesRegex(ValueError, 'longer than'):
            http_transport.conforms({'schema': 'uncle.artifact/v1', 'kind': 'adversarial-review-worker-packet',
                                     'findings': [{'id': 'AR-1', 'summary': 'x' * 100000}]}, schema)

    def test_the_closing_answer_has_its_own_smaller_token_cap(self):
        server = self.serve(PLAN)
        http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                             final_schema=artifact_schema('plan'), final_name='plan')
        # The first, grammar-constrained try is capped at 16k (the largest real answer is about 10k);
        # only the retry without the grammar gets the full 32768.
        self.assertEqual(self.final(server)['max_tokens'], 16384)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_FINAL_OUTPUT_TOKENS': '2048'}):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 64512, turns=0, usage={},
                                 final_schema=artifact_schema('plan'), final_name='plan')
        self.assertEqual(self.final(server)['max_tokens'], 2048)

    def test_reviewer_kind_comes_from_the_prompts_contract(self):
        self.assertEqual(reviewer_artifact_kind('x `{"schema":"uncle.artifact/v1","kind":"final-audit","findings":[]}`'), 'final-audit')
        self.assertIsNone(reviewer_artifact_kind('no contract'))
        self.assertIsNone(reviewer_artifact_kind('"kind":"final-audit" and "kind":"adversarial-review"'))
        self.assertIsNone(reviewer_artifact_kind('"kind":"unknown-kind"'))

    def test_document_stage_runs_over_http_and_publishes(self):
        reply = {'schema': 'uncle.artifact/v1', 'kind': 'requirements-interpretation', 'sections': {
            key: 'text' for key in ('required_functionality', 'optional_functionality', 'constraints', 'user_visible_behaviors',
                                    'system_behaviors', 'failure_behaviors', 'ambiguities', 'assumptions', 'explicit_non_goals',
                                    'definition_of_done')}}
        server = self.serve(reply, tool_script=[{'role': 'assistant', 'content': 'finished'}])
        (self.root/'REQUIREMENTS.md').write_text('# Requirements\n', encoding='utf-8')
        env = {'WORKFLOW_SELF_HOSTED_TRANSPORT': 'http', 'UNCLE_ARTIFACT_DELIVERY': '.uncle/workflow/artifact-delivery/requirements.json'}
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        with patch.dict(os.environ, env):
            usage = {}
            run_opencode('agent', self.values(server), 'Interpret.', self.root, stage='requirements', usage=usage)
        self.assertTrue((self.root/'.uncle/docs/REQUIREMENTS_INTERPRETATION.md').is_file())
        self.assertEqual(json.loads((self.root/'.uncle/workflow/artifact-delivery/requirements.json').read_text(encoding='utf-8')), reply)
        body = self.final(server)
        self.assertEqual(body['response_format']['json_schema']['schema'], artifact_schema('requirements-interpretation'))
        self.assertNotIn('Use your Write tool', json.dumps(body['messages']))
        self.assertEqual(usage['constraint_mode'], 'json_schema')

    def test_reviewer_with_a_known_contract_uses_http_and_writes_its_delivery(self):
        reply = {'schema': 'uncle.artifact/v1', 'kind': 'final-audit-worker-packet', 'findings': []}
        server = self.serve(reply, tool_script=[{'role': 'assistant', 'content': 'finished'}])
        delivery = self.root/'delivery.json'
        prompt = 'Return `{"schema":"uncle.artifact/v1","kind":"final-audit-worker-packet","findings":[]}`'
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_TRANSPORT': 'http', 'UNCLE_ARTIFACT_DELIVERY': str(delivery)}):
            text, _ = run_opencode('reviewer', self.values(server), prompt, self.root, stage='final-audit-review-worker-x')
        self.assertEqual(json.loads(delivery.read_text(encoding='utf-8')), reply)
        self.assertEqual(self.final(server)['response_format']['json_schema']['schema'],
                         artifact_schema('final-audit-worker-packet'))

    # --- the agent loop: editing stages -------------------------------------

    def call(self, name, arguments, ident='c'):
        return {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}

    def agent(self, server, policy, schema=None, **kwargs):
        return http_agent.run_agent(self.values(server), 'Do the work.', policy, 4096, usage=kwargs.pop('usage', {}),
                                    final_schema=schema, **kwargs)

    def test_editing_stage_writes_edits_and_runs_commands_at_temperature_zero(self):
        (self.root/'app.py').write_text('x = 1\n', encoding='utf-8')
        server = self.serve('unused', tool_script=[
            self.call('write_file', {'path': 'new/mod.py', 'content': 'y = 2\n'}, 'a'),
            self.call('edit_file', {'path': 'app.py', 'old_string': 'x = 1', 'new_string': 'x = 5'}, 'b'),
            self.call('bash', {'command': 'cat app.py; exit 3'}, 'c'),
            {'role': 'assistant', 'content': 'All done.'}])
        text, requests = self.agent(server, http_agent.Policy(self.root, write=True, shell=True))
        self.assertEqual((text, requests), ('All done.', 4))
        self.assertEqual((self.root/'new/mod.py').read_text(encoding='utf-8'), 'y = 2\n')
        self.assertEqual((self.root/'app.py').read_text(encoding='utf-8'), 'x = 5\n')
        results = [m['content'] for m in server.requests[-1][1]['messages'] if m['role'] == 'tool']
        self.assertEqual(results[2], 'x = 5\n[exit status 3]')
        self.assertEqual({body['temperature'] for _path, body in server.requests}, {0.0})
        self.assertTrue(all('response_format' not in body for _path, body in server.requests))

    def test_tool_availability_follows_the_stage_policy(self):
        names = lambda policy: {t['function']['name'] for t in policy.tools()}
        self.assertEqual(names(http_agent.Policy(self.root)), {'read_file', 'list_dir', 'grep'})
        self.assertIn('write_file', names(http_agent.Policy(self.root, write=True)))
        self.assertNotIn('bash', names(http_agent.Policy(self.root, write=True)))
        self.assertIn('bash', names(http_agent.Policy(self.root, write=True, shell=True)))

    def test_writes_are_confined_and_protect_driver_state(self):
        policy = http_agent.Policy(self.root, write=True)
        for path in ('../outside.txt', '/etc/passwd', '.git/config', '.env', '.uncle/config', '.uncle/self-hosted-keys.json'):
            self.assertTrue(http_agent.run_tool(policy, 'write_file', {'path': path, 'content': 'x'}).startswith('error:'), path)
        self.assertEqual(http_agent.run_tool(policy, 'write_file', {'path': '.uncle/workflow/documents/n.json', 'content': '{}'}),
                         'wrote .uncle/workflow/documents/n.json')
        (self.root/'real').mkdir()
        (self.root/'link').symlink_to(self.root/'real')
        self.assertIn('symlink', http_agent.run_tool(policy, 'write_file', {'path': 'link/f.txt', 'content': 'x'}))
        read_only = http_agent.Policy(self.root)
        self.assertIn('not permitted', http_agent.run_tool(read_only, 'write_file', {'path': 'a.txt', 'content': 'x'}))

    def test_reviewer_may_write_only_its_delivery_file(self):
        policy = http_agent.Policy(self.root, write=True, writable=['out/delivery.json'])
        self.assertIn('not permitted', http_agent.run_tool(policy, 'write_file', {'path': 'other.json', 'content': '{}'}))
        self.assertEqual(http_agent.run_tool(policy, 'write_file', {'path': 'out/delivery.json', 'content': '{}'}), 'wrote out/delivery.json')

    def test_edit_requires_a_unique_match(self):
        (self.root/'f.txt').write_text('a a\n', encoding='utf-8')
        policy = http_agent.Policy(self.root, write=True)
        self.assertIn('matches 2 places', http_agent.run_tool(policy, 'edit_file', {'path': 'f.txt', 'old_string': 'a', 'new_string': 'b'}))
        self.assertIn('not found', http_agent.run_tool(policy, 'edit_file', {'path': 'f.txt', 'old_string': 'z', 'new_string': 'b'}))
        http_agent.run_tool(policy, 'edit_file', {'path': 'f.txt', 'old_string': 'a', 'new_string': 'b', 'replace_all': True})
        self.assertEqual((self.root/'f.txt').read_text(encoding='utf-8'), 'b b\n')

    def test_shell_command_times_out_and_is_reported(self):
        policy = http_agent.Policy(self.root, shell=True)
        self.assertIn('timed out after 1s', http_agent.run_tool(policy, 'bash', {'command': 'sleep 30', 'timeout': 1}))

    def test_the_model_is_told_where_the_project_is(self):
        server = self.serve('x', tool_script=[{'role': 'assistant', 'content': 'done'}])
        policy = http_agent.Policy(self.root, shell=True)
        http_agent.run_agent(self.values(server), 'Go.', policy, 4096, usage={})
        body = [b for _p, b in server.requests if b.get('tools')][0]
        system = body['messages'][0]['content']
        self.assertIn(str(self.root), system)
        self.assertIn('Never cd to another directory', system)
        bash = [t for t in body['tools'] if t['function']['name'] == 'bash'][0]
        self.assertIn(str(self.root), bash['function']['description'])

    def test_a_cd_out_of_the_project_is_refused_before_it_runs(self):
        policy = http_agent.Policy(self.root, shell=True)
        marker = self.root/'ran'
        for command in ('cd /Users/brian && touch %s' % marker, 'cd ~ && touch %s' % marker,
                        'cd $HOME/src; touch %s' % marker, 'cd "/Users/brian/Library" && touch %s' % marker):
            out = http_agent.run_tool(policy, 'bash', {'command': command})
            self.assertTrue(out.startswith('error: not run.'), (command, out))
            self.assertIn(str(self.root), out)
        self.assertFalse(marker.exists())

    def test_cd_inside_the_project_and_to_scratch_space_is_allowed(self):
        (self.root/'sub').mkdir()
        policy = http_agent.Policy(self.root, shell=True)
        self.assertIsNone(http_agent.escapes_project(policy, 'cd sub && ls'))
        self.assertIsNone(http_agent.escapes_project(policy, 'cd "%s/sub" && ls' % self.root))
        self.assertIsNone(http_agent.escapes_project(policy, 'cd /tmp/scratch && ls'))
        self.assertIsNone(http_agent.escapes_project(policy, 'echo "cd /etc is only text"'))
        out = http_agent.run_tool(policy, 'bash', {'command': 'cd sub && pwd'})
        self.assertIn('/sub', out)

    def test_a_shell_command_cannot_ask_for_more_than_the_ceiling(self):
        self.assertEqual(http_agent.bash_timeout(None), 120)
        self.assertEqual(http_agent.bash_timeout(30), 30)
        self.assertEqual(http_agent.bash_timeout(3600), 900)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_BASH_MAX_SECONDS': '2'}):
            self.assertEqual(http_agent.bash_timeout(3600), 2)
            out = http_agent.run_tool(http_agent.Policy(self.root, shell=True), 'bash', {'command': 'sleep 30', 'timeout': 3600})
        self.assertIn('timed out after 2s', out)

    def test_a_shell_command_is_announced_before_it_runs(self):
        status = self.root/'announce.jsonl'
        server = self.serve('x', tool_script=[self.call('bash', {'command': 'echo hi', 'timeout': 5}), {'role': 'assistant', 'content': 'ok'}])
        with patch.dict(os.environ, {'UNCLE_STATUS_FILE': str(status), 'UNCLE_STATUS_STAGE': 'execute-checklist'}):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root, shell=True), 4096, usage={})
        events = [json.loads(l) for l in status.read_text(encoding='utf-8').splitlines()]
        notes = [e for e in events if e['event'] == 'chat_output']
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]['stage'], 'execute-checklist')
        self.assertIn('$ echo hi (up to 5s)', notes[0]['text'])

    def test_an_unchanged_command_is_not_run_again(self):
        # A stage re-ran a multi-minute suite five times in a row against unchanged files.
        policy = http_agent.Policy(self.root, write=True, shell=True)
        count = self.root/'count.txt'
        command = 'echo run >> count.txt; echo failing-output; exit 3'
        first = http_agent.run_tool(policy, 'bash', {'command': command})
        again = http_agent.run_tool(policy, 'bash', {'command': command})
        self.assertIn('failing-output', again)
        self.assertIn('exit status 3', again)
        self.assertIn('[repeated:', again)
        self.assertEqual(count.read_text(encoding='utf-8').count('run'), 1)    # the second call never ran it
        self.assertNotIn('[repeated:', first)
        # Changing a project file makes it a different question.
        http_agent.run_tool(policy, 'write_file', {'path': 'src/new.js', 'content': 'x'})
        third = http_agent.run_tool(policy, 'bash', {'command': command})
        self.assertNotIn('[repeated:', third)
        self.assertEqual(count.read_text(encoding='utf-8').count('run'), 2)
        # A different command is always run.
        self.assertNotIn('[repeated:', http_agent.run_tool(policy, 'bash', {'command': 'echo other'}))

    def test_starting_a_server_between_runs_makes_a_rerun_legitimate(self):
        policy = http_agent.Policy(self.root, shell=True)
        command = 'echo checked >> count.txt; echo ok'
        http_agent.run_tool(policy, 'bash', {'command': command})
        http_agent.run_tool(policy, 'bash', {'command': 'sleep 300 & echo started'})   # a server comes up
        out = http_agent.run_tool(policy, 'bash', {'command': command})
        self.assertNotIn('[repeated:', out)
        self.assertEqual((self.root/'count.txt').read_text(encoding='utf-8').count('checked'), 2)
        policy.cleanup()

    def test_build_output_and_dependencies_do_not_count_as_changes(self):
        policy = http_agent.Policy(self.root, shell=True)
        command = 'echo x >> count.txt; echo ok'
        http_agent.run_tool(policy, 'bash', {'command': command})
        (self.root/'node_modules').mkdir(); (self.root/'node_modules/p.js').write_text('1', encoding='utf-8')
        (self.root/'dist').mkdir(); (self.root/'dist/a.js').write_text('1', encoding='utf-8')
        (self.root/'test-results').mkdir(); (self.root/'test-results/r.json').write_text('1', encoding='utf-8')
        self.assertIn('[repeated:', http_agent.run_tool(policy, 'bash', {'command': command}))

    def test_a_timed_out_command_is_never_remembered(self):
        policy = http_agent.Policy(self.root, shell=True)
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_BASH_MAX_SECONDS': '1'}):
            first = http_agent.run_tool(policy, 'bash', {'command': 'sleep 20', 'timeout': 1})
            second = http_agent.run_tool(policy, 'bash', {'command': 'sleep 20', 'timeout': 1})
        self.assertIn('timed out after 1s', first)
        self.assertIn('timed out after 1s', second)
        self.assertNotIn('[repeated:', second)

    def test_servers_a_stage_left_running_are_ended_when_it_finishes(self):
        # `npx vite &` inside a command used to outlive the stage: servers piled up on
        # the same port, one spinning at 70% CPU, and later tests ran against them.
        server = self.serve('x', tool_script=[
            self.call('bash', {'command': 'sleep 300 & echo $!'}, 'a'),
            self.call('bash', {'command': 'kill -0 %s' % '$(cat pid.txt)'}, 'b'),
            {'role': 'assistant', 'content': 'done'}])
        policy = http_agent.Policy(self.root, shell=True)
        # First call: start the background process and remember its pid in the project.
        pid_file = self.root/'pid.txt'
        server.tool_script[0] = self.call('bash', {'command': 'sleep 300 & echo $! > pid.txt'}, 'a')
        http_agent.run_agent(self.values(server), 'Go.', policy, 4096, usage={})
        pid = int(pid_file.read_text(encoding='utf-8'))
        results = [m['content'] for m in server.requests[-1][1]['messages'] if m['role'] == 'tool']
        self.assertIn('exit status 0', results[1])         # still alive for the stage's later commands
        time.sleep(0.5)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)                                # gone once the stage ended

    def test_shell_does_not_inherit_driver_identity(self):
        with patch.dict(os.environ, {'UNCLE_CONFIG': '/secret/config', 'STAGEGATE_RUN_ID': 'r1', 'KEEP_ME': 'yes'}):
            output = http_agent.run_tool(http_agent.Policy(self.root, shell=True), 'bash',
                                         {'command': 'echo "[$UNCLE_CONFIG][$STAGEGATE_RUN_ID][$KEEP_ME]"'})
        self.assertTrue(output.startswith('[][][yes]'), output)

    def test_written_workflow_documents_are_validated_against_their_schema(self):
        from self_hosted import document_schema_for
        policy = http_agent.Policy(self.root, write=True, schema_for=document_schema_for('', 'prompt'))
        path = '.uncle/workflow/documents/AUTOMATED_TEST_REPORT.json'
        bad = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'automated-test-report', 'commands': [{'command': 'x', 'status': 'MAYBE', 'output': 'o'}]})
        result = http_agent.run_tool(policy, 'write_file', {'path': path, 'content': bad})
        self.assertIn('violates its schema', result)
        self.assertFalse((self.root/path).exists())
        self.assertIn('valid JSON', http_agent.run_tool(policy, 'write_file', {'path': path, 'content': 'prose'}))
        good = json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'automated-test-report', 'commands': [{'command': 'x', 'status': 'PASS', 'output': 'ok'}]})
        self.assertEqual(http_agent.run_tool(policy, 'write_file', {'path': path, 'content': good}), 'wrote ' + path)
        # Documents with no registered schema are not constrained.
        self.assertEqual(http_agent.run_tool(policy, 'write_file', {'path': 'notes.md', 'content': 'free'}), 'wrote notes.md')

    def test_editing_stage_final_answer_is_schema_forced(self):
        reply = {'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes', 'changed_files': [{'path': 'a.py'}]}
        server = self.serve(reply, tool_script=[self.call('write_file', {'path': 'a.py', 'content': 'x'}), {'role': 'assistant', 'content': 'finished'}])
        text, _ = self.agent(server, http_agent.Policy(self.root, write=True), schema=artifact_schema('implementation-notes'))
        self.assertEqual(json.loads(text), reply)
        self.assertEqual(self.final(server)['response_format']['json_schema']['schema'], artifact_schema('implementation-notes'))
        self.assertEqual(self.final(server)['temperature'], 0.0)

    def test_editing_stage_requires_tool_calling(self):
        server = self.serve('x', reject={'tools'})
        with self.assertRaisesRegex(ValueError, 'does not support tool calling'):
            self.agent(server, http_agent.Policy(self.root, write=True))

    def test_turn_limit_asks_for_a_final_answer_without_tools(self):
        call = lambda n: self.call('list_dir', {}, 'c%d' % n)
        server = self.serve(Raw('wrapped up'), tool_script=[call(1), call(2), call(3)])
        text, requests = http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, turns=2, usage={})
        self.assertEqual((text, requests), ('wrapped up', 3))
        self.assertNotIn('tools', server.requests[-1][1])

    def test_empty_final_text_gets_one_nudge_then_fails(self):
        server = self.serve('x', tool_script=[{'role': 'assistant', 'content': ''}, {'role': 'assistant', 'content': ''}])
        with self.assertRaisesRegex(ValueError, 'no final text'):
            self.agent(server, http_agent.Policy(self.root))
        server = self.serve('x', tool_script=[{'role': 'assistant', 'content': ''}, {'role': 'assistant', 'content': 'ok'}])
        self.assertEqual(self.agent(server, http_agent.Policy(self.root))[0], 'ok')

    def test_steering_reaches_the_model_and_is_acknowledged(self):
        events = []

        class FakeStage:
            correlation = ''
            pending = {}
            final_answer = ''
            def __init__(inner):
                inner.sent = False
            def incoming(inner, steer):
                if not inner.sent and inner.calls:
                    inner.sent = True
                    steer('Please also add tests.', 'm1')
            calls = 0
            def ack(inner, event): events.append(('ack', event['id']))
            def answered(inner, identifier, response):
                events.append(('answered', identifier))
            def tokens(inner, usage, **kw): inner.calls = 1
            def text(inner, text): pass
        server = self.serve('x', tool_script=[self.call('list_dir', {}), {'role': 'assistant', 'content': 'done'}])
        self.agent(server, http_agent.Policy(self.root), stage=FakeStage())
        contents = [m['content'] for m in server.requests[-1][1]['messages'] if m['role'] == 'user']
        self.assertIn('Please also add tests.', contents)
        self.assertEqual(events, [('ack', 'm1'), ('answered', 'm1')])

    def test_a_message_sent_during_a_long_request_is_taken_in_at_once(self):
        # The request is not streamed and used to be read-to-completion before the
        # inbox was looked at, so chat to a local-model stage sat unanswered for the
        # whole wait. Now the in-flight request is dropped and redone with the message.
        from native_stage import Stage
        status = self.root/'steer-status.jsonl'
        server = self.serve(Raw('Noted: adding a footer.'), delay=3)
        directory = Path(tempfile.mkdtemp(dir=self.root))
        with patch.dict(os.environ, {'UNCLE_STATUS_FILE': str(status), 'UNCLE_STATUS_STAGE': 'implementation'}):
            stage = Stage('self-hosted', 'agent', 'implementation', [], prompt='Do the work.')
            stage.ready(str(directory))
            def operator():
                time.sleep(1)
                (directory/'inbox'/'1.json').write_text(json.dumps({'id': 'm1', 'text': 'Please add a footer.'}), encoding='utf-8')
            threading.Thread(target=operator, daemon=True).start()
            started = time.monotonic()
            usage = {}
            text, requests = http_agent.run_agent(self.values(server), stage.prompt, http_agent.Policy(self.root), 4096,
                                                  usage=usage, stage=stage)
            elapsed = time.monotonic() - started
        chats = [body for path, body in server.requests if body.get('tools')]
        self.assertEqual(len(chats), 2)                      # the dropped request, then the one with the message
        self.assertNotIn('Please add a footer.', json.dumps(chats[0]['messages']))
        self.assertIn('Please add a footer.', json.dumps(chats[1]['messages']))
        self.assertEqual(text, 'Noted: adding a footer.')
        self.assertEqual(usage['input_tokens'], 10)          # the dropped response was never counted
        self.assertLess(elapsed, 4.9)                        # not 3 s + the message + 3 s again
        events = [json.loads(line)['event'] for line in status.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([e for e in events if e.startswith('steering_')], ['steering_ready', 'steering_accepted', 'steering_answered'])

    def test_a_tool_only_turn_does_not_count_as_answering_the_operator(self):
        answered = []
        class FakeStage:
            correlation = ''
            pending = {}
            final_answer = ''
            channel = None
            sent = False
            def incoming(inner, steer):
                if not inner.sent and inner.calls:
                    inner.sent = True
                    steer('Status?', 'm1')
            calls = 0
            def ack(inner, event): pass
            def answered(inner, identifier, response): answered.append(identifier)
            def tokens(inner, usage, **kw): inner.calls = 1
            def text(inner, text): pass
        server = self.serve('x', tool_script=[self.call('list_dir', {}), self.call('list_dir', {}, 'b'),
                                              {'role': 'assistant', 'content': 'All good, still working.'}])
        self.agent(server, http_agent.Policy(self.root), stage=FakeStage())
        self.assertEqual(answered, ['m1'])  # once, with the turn that spoke

    def test_read_cache_learns_files_the_model_read(self):
        (self.root/'doc.md').write_text('hello\n', encoding='utf-8')
        from read_cache import ReadCache
        cache = ReadCache(self.root)
        server = self.serve('x', tool_script=[self.call('read_file', {'path': 'doc.md'}), {'role': 'assistant', 'content': 'done'}])
        self.agent(server, http_agent.Policy(self.root), read_cache=cache)
        self.assertEqual(len(list(cache.directory.glob('*.json'))), 1)

    def test_a_running_stage_publishes_its_token_total_after_every_request(self):
        status = self.root/'status.jsonl'
        server = self.serve(PLAN, tool_script=[self.call('list_dir', {}), self.call('list_dir', {}, 'b'),
                                               {'role': 'assistant', 'content': 'done'}])
        with patch.dict(os.environ, {'UNCLE_STATUS_FILE': str(status), 'UNCLE_STATUS_STAGE': 'preflight-worker-browser'}):
            http_agent.run_agent(self.values(server), 'Go.', http_agent.Policy(self.root), 4096, usage={},
                                 final_schema=artifact_schema('plan'), final_name='plan', side='reviewer')
        events = [json.loads(line) for line in status.read_text(encoding='utf-8').splitlines()]
        self.assertEqual({e['event'] for e in events}, {'usage'})
        self.assertEqual({e['stage'] for e in events}, {'preflight-worker-browser'})
        self.assertEqual({e['mode'] for e in events}, {'review'})
        totals = [e['total_tokens'] for e in events]
        self.assertEqual(len(totals), 4)             # three tool-loop turns and the closing answer
        self.assertEqual(totals, sorted(totals))
        self.assertGreater(totals[-1], totals[0])
        self.assertEqual(events[-1]['usage']['input_tokens'], 40)

    def test_native_stage_runs_over_http_with_its_steering_channel(self):
        from native_stage import Stage
        from self_hosted import run_http_stage
        server = self.serve('x', tool_script=[{'role': 'assistant', 'content': 'Native answer.'}])
        stage = Stage('self-hosted', 'agent', 'implementation', [], prompt='Do it.')
        directory = Path(tempfile.mkdtemp(prefix='native-http-', dir=self.root))
        run_http_stage(stage, str(directory), dict(self.values(server), max_turns=5), self.root)
        self.assertEqual(stage.final_answer, 'Native answer.')
        self.assertTrue((directory/'inbox').is_dir())
        self.assertEqual(server.requests[-1][1]['temperature'], 0.0)

    def test_unlisted_stage_is_free_text_at_temperature_zero(self):
        server = self.serve('x', tool_script=[{'role': 'assistant', 'content': 'Plain report.'}])
        with patch.dict(os.environ, {'WORKFLOW_SELF_HOSTED_TRANSPORT': 'http'}):
            text, turns = run_opencode('agent', self.values(server), 'No contract here.', self.root, stage='preview-build')
        self.assertEqual(text, 'Plain report.')
        self.assertEqual(server.requests[-1][1]['temperature'], 0.0)
        self.assertNotIn('response_format', server.requests[-1][1])
        self.assertEqual(reviewer_artifact_kind('write `{"kind":"implementation-notes"}` only'), 'implementation-notes')


if __name__ == '__main__':
    unittest.main()
