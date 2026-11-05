"""The persistent housekeeping runner behind the homepage chat.

`housekeeping-workflow.sh` starts one `claude -p` per request and pays about
three seconds of process and connection setup every time. The homepage keeps a
single long-lived worker instead: same tools, same deny list, same model
settings as the script, but running in the project checkout and answering many
turns on one stream-json conversation.

It reuses the supervisor's session machinery (one turn at a time under a lock,
any failure kills the process and marks the session dead so the caller can
start a fresh one).
"""
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time

import housekeeping_config
from process_tree import KEEP_STDIN, kill_tree, launch_command, start_check
from supervisor_runner import GRACE_SECONDS, SupervisorSession

TOOLS = 'Read,Glob,Grep,Write,Edit,TodoWrite,Bash'
EXTRA_DENY = ('git push --force', 'git push -f', 'git push --force-with-lease',
              'rm -rf /', 'rm -rf ~', 'rm -fr /', 'rm -fr ~')
# Environment that must never reach the runner: the OAuth login has to be what
# authenticates (see scripts/lib/stage-config.sh).
STRIP_ENV = ('ANTHROPIC_API_KEY', 'UNCLE_MODEL_REFRESH_KEY')


def deny_patterns(config_path):
    """Command-prefix patterns the runner may never execute (floor + extras + editable list)."""
    patterns = []
    for pattern in (list(housekeeping_config.floor_patterns()) + list(EXTRA_DENY)
                    + list(housekeeping_config.load(config_path))):
        if any(ch in pattern for ch in ',()'):
            raise ValueError('deny pattern cannot be expressed safely: %s' % pattern)
        if pattern not in patterns:
            patterns.append(pattern)
    return patterns


def system_prompt(root, patterns):
    with open(os.path.join(root, 'prompts', 'housekeeping-plan.md'), encoding='utf-8') as fh:
        text = fh.read()
    text += '\n## Never run commands starting with\n\n'
    text += ''.join('- `%s`\n' % pattern for pattern in patterns)
    text += ('\n## Conversation\n\nThis is a continuing conversation with the operator, who types '
             'plain-language requests one at a time. Answer each request directly and briefly.\n')
    return text


def build_command(root, config_path, model, effort, environ=None):
    """(argv, env) for the persistent runner, or ValueError('unavailable ...')."""
    environ = os.environ if environ is None else environ
    executable = environ.get('WORKFLOW_CLAUDE_CMD') or 'claude'
    resolved = shutil.which(executable)
    if not resolved:
        raise ValueError('unavailable: %s is not on PATH' % executable)
    patterns = deny_patterns(config_path)
    argv = [resolved, '-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
            '--strict-mcp-config', '--no-session-persistence',
            '--model', model, '--effort', effort,
            '--allowedTools', TOOLS,
            '--disallowedTools', ','.join('Bash(%s:*)' % p for p in patterns),
            '--append-system-prompt', system_prompt(root, patterns)]
    env = {k: v for k, v in environ.items() if k not in STRIP_ENV}
    return argv, env


PERSISTENT_RUNNERS = ('claude', 'codex', 'kimi')
_SEGMENT = re.compile(r'&&|\|\||[;|\n]')
_ENV_ASSIGN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')


def command_denied(command, patterns):
    """True when any command in a shell line starts with a denied prefix.

    Codex and Kimi cannot be given per-command deny rules the way Claude can, so
    every approval request they raise is vetted here instead. A line that cannot
    be read is refused rather than guessed at.
    """
    command = command.strip()
    try:
        tokens = shlex.split(command)
    except ValueError:
        return True
    if len(tokens) >= 3 and os.path.basename(tokens[0]) in ('sh', 'bash', 'zsh') and tokens[1] in ('-c', '-lc', '-ic'):
        command = tokens[2]
    for segment in _SEGMENT.split(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            return True
        while words and _ENV_ASSIGN.match(words[0]):
            words.pop(0)
        for pattern in patterns:
            wanted = pattern.split()
            if words[:len(wanted)] == wanted:
                return True
    return False


class _Dead(Exception):
    pass


class RpcSession:
    """A persistent JSON-RPC worker (codex app-server, kimi acp) with the session contract the chat expects.

    One turn at a time under a lock. Any failure, cancellation or timeout kills
    the process and marks the session dead, and the caller starts a fresh one.
    `turn()` returns Claude-shaped stream lines so parse_stream reads the result.
    """
    name = 'rpc'

    def __init__(self, argv, env, cwd, instructions, model, effort, patterns):
        self.cwd, self.env, self.model, self.effort = cwd, env, model, effort
        self.instructions, self.patterns = instructions, list(patterns)
        self.command = list(argv)
        self.home = tempfile.mkdtemp(prefix='uncle-housekeeping-')
        self.lock = threading.Lock()
        self.messages = queue.Queue()
        self.next_id = 0
        self.ready = False
        self.process = None
        try:
            self.process = start_check(launch_command(self.command), prompt=KEEP_STDIN, cwd=cwd, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.process = None
            return
        threading.Thread(target=self._read, args=(self.process,), daemon=True).start()

    # -- plumbing -----------------------------------------------------------
    def _read(self, process):
        try:
            for raw in iter(process.stdout.readline, b''):
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    self.messages.put((raw, message))
        except (OSError, ValueError):
            pass
        finally:
            self.messages.put(None)

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.close()
            except OSError:
                pass
            if process.poll() is None:
                kill_tree(process)
                try:
                    process.wait(timeout=GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        shutil.rmtree(self.home, ignore_errors=True)

    def _send(self, message):
        try:
            self.process.stdin.write((json.dumps(message) + '\n').encode('utf-8'))
            self.process.stdin.flush()
        except (OSError, ValueError, AttributeError):
            raise _Dead('worker stdin closed')

    def _next(self, deadline, cancelled, log):
        while True:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise _Dead('cancelled or timed out')
            try:
                item = self.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                raise _Dead('worker exited')
            raw, message = item
            log.write(raw if raw.endswith(b'\n') else raw + b'\n')
            return message

    def _request(self, method, params, deadline, cancelled, log, on_message=None, version=None):
        self.next_id += 1
        mine = self.next_id
        message = {'id': mine, 'method': method, 'params': params}
        if version:
            message['jsonrpc'] = version
        self._send(message)
        while True:
            reply = self._next(deadline, cancelled, log)
            if reply.get('id') == mine and 'method' not in reply:
                if reply.get('error'):
                    raise _Dead('%s failed: %s' % (method, reply['error']))
                return reply.get('result') or {}
            if 'method' in reply and 'id' in reply:
                self._server_request(reply)
            elif on_message is not None:
                on_message(reply)

    # -- subclass hooks -------------------------------------------------------
    def _handshake(self, deadline, cancelled, log):
        raise NotImplementedError

    def _prompt(self, text, deadline, cancelled, log, progress):
        raise NotImplementedError

    def _server_request(self, message):
        self._send({'id': message['id'], 'error': {'code': -32601, 'message': 'unsupported'}})

    # -- the session contract -------------------------------------------------
    def prime(self):
        if not self.alive():
            return False
        import io
        try:
            lines = self.turn('Warm-up only, sent by the application before the operator has typed anything. '
                              'It is not from the operator and authorizes nothing. Reply with exactly: ready',
                              io.BytesIO(), time.monotonic() + 90, threading.Event())
        except (OSError, ValueError):
            return False
        return lines is not None

    def turn(self, prompt, log, deadline, cancelled, progress=None):
        if not self.alive():
            return None
        with self.lock:
            if not self.alive():
                return None
            try:
                if not self.ready:
                    self._handshake(deadline, cancelled, log)
                    self.ready = True
                reply, usage, error = self._prompt(prompt, deadline, cancelled, log, progress)
            except _Dead:
                self.close()
                return None
        lines = [json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': reply}]}})]
        result = {'type': 'result', 'is_error': bool(error), 'result': error or reply}
        if usage:
            result['usage'] = usage
        lines.append(json.dumps(result))
        return lines


class CodexSession(RpcSession):
    """`codex app-server`: one thread, one turn per message, commands vetted against the deny list."""
    name = 'codex'

    def _handshake(self, deadline, cancelled, log):
        self._request('initialize', {'clientInfo': {'name': 'uncle', 'title': 'uncle', 'version': '1'}},
                      deadline, cancelled, log)
        self._send({'method': 'initialized'})
        params = {'cwd': self.cwd, 'approvalPolicy': 'untrusted', 'sandbox': 'workspace-write',
                  'ephemeral': True, 'developerInstructions': self.instructions}
        if self.model and self.model != 'sonnet':
            params['model'] = self.model
        started = self._request('thread/start', params, deadline, cancelled, log)
        self.thread = (started.get('thread') or {}).get('id')
        if not self.thread:
            raise _Dead('no thread id')

    def _server_request(self, message):
        method, params = message.get('method'), message.get('params') or {}
        if method == 'item/commandExecution/requestApproval':
            denied = command_denied(str(params.get('command') or ''), self.patterns)
            decision = 'decline' if denied else 'accept'
        elif method == 'item/fileChange/requestApproval':
            decision = 'accept'
        else:
            return super()._server_request(message)
        self._send({'id': message['id'], 'result': {'decision': decision}})

    def _prompt(self, text, deadline, cancelled, log, progress):
        state = {'final': '', 'last': '', 'usage': None, 'error': '', 'done': False, 'phases': {}, 'streamed': False}

        def on_message(message):
            method, params = message.get('method'), message.get('params') or {}
            item = params.get('item') or {}
            if method == 'item/started' and item.get('type') == 'agentMessage':
                state['phases'][item.get('id')] = item.get('phase')
                if progress is not None and state['streamed']:
                    progress.put('\n\n')
            elif method == 'item/agentMessage/delta':
                if progress is not None:
                    progress.put(params.get('delta') or '')
                    state['streamed'] = True
            elif method == 'item/completed' and item.get('type') == 'agentMessage':
                state['last'] = item.get('text') or ''
                if item.get('phase') == 'final_answer':
                    state['final'] = state['last']
            elif method == 'thread/tokenUsage/updated':
                last = (params.get('tokenUsage') or {}).get('last') or {}
                state['usage'] = {'input_tokens': last.get('inputTokens', 0), 'output_tokens': last.get('outputTokens', 0)}
            elif method == 'turn/completed':
                turn = params.get('turn') or {}
                if turn.get('status') == 'failed':
                    state['error'] = str((turn.get('error') or {}).get('message') or 'turn failed')
                state['done'] = True

        params = {'threadId': self.thread, 'input': [{'type': 'text', 'text': text}]}
        if self.effort:
            params['effort'] = self.effort
        self._request('turn/start', params, deadline, cancelled, log, on_message)
        while not state['done']:
            message = self._next(deadline, cancelled, log)
            if 'method' in message and 'id' in message:
                self._server_request(message)
            else:
                on_message(message)
        return state['final'] or state['last'], state['usage'], state['error']


class KimiSession(RpcSession):
    """`kimi acp`: one session, one prompt per message, tool permission requests vetted against the deny list."""
    name = 'kimi'
    RPC = '2.0'

    def _handshake(self, deadline, cancelled, log):
        self._request('initialize', {'protocolVersion': 1, 'clientCapabilities': {}}, deadline, cancelled, log,
                      version=self.RPC)
        created = self._request('session/new', {'cwd': self.cwd, 'mcpServers': []}, deadline, cancelled, log,
                                version=self.RPC)
        self.session_id = created.get('sessionId')
        if not self.session_id:
            raise _Dead('no session id')
        self.first = True

    def _send(self, message):
        message.setdefault('jsonrpc', self.RPC)
        super()._send(message)

    def _server_request(self, message):
        if message.get('method') != 'session/request_permission':
            return super()._server_request(message)
        params = message.get('params') or {}
        call = params.get('toolCall') or {}
        text = ' '.join(str(((c or {}).get('content') or {}).get('text') or '') for c in call.get('content') or [])
        denied = False
        if call.get('title') == 'Bash' or 'Running:' in text:
            denied = command_denied(text.split('Running:', 1)[-1], self.patterns)
        wanted = 'reject_once' if denied else 'allow_once'
        options = params.get('options') or []
        chosen = next((o.get('optionId') for o in options if o.get('kind') == wanted), None)
        if chosen is None:
            self._send({'id': message['id'], 'result': {'outcome': {'outcome': 'cancelled'}}})
        else:
            self._send({'id': message['id'], 'result': {'outcome': {'outcome': 'selected', 'optionId': chosen}}})

    def _prompt(self, text, deadline, cancelled, log, progress):
        if self.first:
            text = self.instructions + '\n\n## Request\n\n' + text
            self.first = False
        parts = []

        def on_message(message):
            update = (message.get('params') or {}).get('update') or {}
            if message.get('method') == 'session/update' and update.get('sessionUpdate') == 'agent_message_chunk':
                chunk = (update.get('content') or {}).get('text') or ''
                parts.append(chunk)
                if progress is not None:
                    progress.put(chunk)

        result = self._request('session/prompt', {'sessionId': self.session_id,
                                                  'prompt': [{'type': 'text', 'text': text}]},
                               deadline, cancelled, log, on_message, version=self.RPC)
        error = '' if result.get('stopReason') in ('end_turn', None) else 'stopped: %s' % result.get('stopReason')
        return ''.join(parts), None, error


def persistent_session(runner, root, config_path, model, effort, cwd, environ=None):
    """The persistent tool-enabled worker for the supervisor's runner, or ValueError('unavailable ...').

    Returns (session, base_command). Claude enforces the deny list through its
    own tool rules; Codex and Kimi have every command approval vetted against it.
    """
    environ = os.environ if environ is None else environ
    if runner == 'claude':
        argv, env = build_command(root, config_path, model, effort, environ)
        return HousekeepingSession(argv, env, cwd), argv
    patterns = deny_patterns(config_path)
    instructions = system_prompt(root, patterns)
    env = {k: v for k, v in environ.items() if k not in STRIP_ENV}
    if runner == 'codex':
        binary = shutil.which(environ.get('WORKFLOW_CODEX_CMD') or 'codex')
        argv = [binary, 'app-server']
        cls = CodexSession
    elif runner == 'kimi':
        binary = shutil.which(environ.get('WORKFLOW_KIMI_CMD') or 'kimi')
        argv = [binary, 'acp']
        cls = KimiSession
    else:
        raise ValueError('unavailable: no housekeeping worker for runner %s' % runner)
    if not binary:
        raise ValueError('unavailable: %s is not on PATH' % runner)
    return cls(argv, env, cwd, instructions, model, effort, patterns), argv


class HousekeepingSession(SupervisorSession):
    """A SupervisorSession that runs in the project checkout with tools enabled."""

    def __init__(self, command, env, cwd):
        self.cwd = cwd
        home = tempfile.mkdtemp(prefix='uncle-housekeeping-')
        super().__init__(command, env, home, cwd=cwd)

    def close(self):
        super().close()
        shutil.rmtree(self.home, ignore_errors=True)
