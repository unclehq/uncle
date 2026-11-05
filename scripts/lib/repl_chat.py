"""Synchronous chat adapter for the headless REPL.

One chat turn runs through the agent-runner contract (prompt on stdin,
stream-json log, reply extracted from the log). The runner runs in its own
process group so terminate() can kill it from Ctrl-C or SIGTERM. This module
does no direct output: it returns text or raises ChatError.
"""
import os
import shlex
import subprocess
import tempfile
import threading
from pathlib import Path

import home_actions
import home_agent_session
from process_tree import launch_command, kill_tree, group_options
from triage_chat import extract_reply_from_log, runner_flags, scrub_env, MAX_REPLY, TIMEOUT_TICKS


class ChatError(Exception):
    """A chat turn failed; the message is untrusted text for the caller to filter."""


_lock = threading.Lock()
_current = None
_cancelled = threading.Event()
last_denials = []
INSTALL_ROOT = str(Path(__file__).resolve().parents[2])


def terminate():
    """Kill the in-flight chat runner's process group, if any."""
    _cancelled.set()
    process = _current
    if process is not None:
        try:
            kill_tree(process)
        except Exception:
            pass


def ask(command, prompt, cwd, env, log_path):
    """Run one turn and return the reply text. Blocks until done, cancelled or timed out."""
    global _current
    _cancelled.clear()
    log_path = str(log_path)
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        prompt_path = log_path + '.prompt'
        with open(prompt_path, 'w', encoding='utf-8') as fh:
            fh.write(prompt)
        process = None
        with open(log_path, 'wb') as log, open(prompt_path, 'rb') as stdin:
            try:
                with _lock:
                    process = subprocess.Popen(launch_command(command), cwd=cwd, env=env, stdin=stdin,
                                               stdout=log, stderr=subprocess.STDOUT, **group_options())
                    _current = process
                if _cancelled.is_set():
                    raise ChatError('Chat request cancelled')
                code = None
                for _ in range(TIMEOUT_TICKS):
                    if _cancelled.is_set():
                        raise ChatError('Chat request cancelled')
                    try:
                        code = process.wait(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                else:
                    raise ChatError('Chat request timed out after five minutes')
            finally:
                _current = None
                if process is not None:
                    kill_tree(process)
                    process.wait()
        if os.path.getsize(log_path) > MAX_REPLY:
            raise ChatError('Chat reply exceeds 1 MiB; discarded.')
        reply, error = extract_reply_from_log(log_path)
        with open(log_path, encoding='utf-8', errors='replace') as fh:
            last_denials[:] = home_agent_session.permission_denials(fh.read().splitlines())
        if error:
            raise ChatError('Chat runner reported an error: %s' % error)
        if code:
            raise ChatError('Chat runner exited with status %s' % code)
        if not reply.strip():
            raise ChatError('Chat runner returned an empty reply')
        return reply
    except OSError as exc:
        raise ChatError(str(exc))


class ChatSession:
    """Holds the one conversation history owner's runner config (I-6); history is passed in.

    Without UNCLE_REPL_RUNNER the turn runs the same tool-enabled home agent the
    curses UI uses: read tools plus any exact-match grants, with denied tool
    calls reported back so the REPL can grant them (auto in unattended mode,
    after a y/N in attended mode) and retry once.
    """

    def __init__(self, root, env, attended=True, confirm=None, say=None):
        self.root, self.env = root, dict(env)
        self.attended, self.confirm, self.say = attended, confirm, say
        self.grants = []
        self.last_cwd = None
        self.notes = []

    def _agent_command(self):
        model, effort = 'sonnet', 'low'
        try:
            import supervisor
            config = supervisor.load_config(self.env.get('UNCLE_CONFIG') or os.path.join(self.root, '.uncle', 'config'))
            model = getattr(config, 'model', None) or model
            effort = getattr(config, 'effort', None) or effort
        except Exception:
            pass
        argv, env = home_agent_session.build_command(INSTALL_ROOT, model, effort, tuple(self.grants), self.env)
        return argv, env

    def command(self):
        override = self.env.get('UNCLE_REPL_RUNNER')
        if override:
            return shlex.split(override)
        return self._agent_command()[0]

    def _once(self, line, history):
        turns = [{'role': r, 'text': t} for r, t in history]
        if not turns or turns[-1] != {'role': 'user', 'text': line}:
            turns.append({'role': 'user', 'text': line})
        override = self.env.get('UNCLE_REPL_RUNNER')
        if override:
            prompt, env = home_actions.prompt(turns, self.root), scrub_env(self.env)
            command = shlex.split(override)
        else:
            try:
                command, env = self._agent_command()
            except ValueError as exc:
                raise ChatError(str(exc))
            lines = ['%s: %s' % ('Operator' if t['role'] == 'user' else 'You', t['text'][:4000]) for t in turns[-12:]]
            prompt = 'Conversation so far:\n' + '\n'.join(lines) + '\n\nReply to the operator\'s last message.'
        with tempfile.TemporaryDirectory(prefix='uncle-repl-') as d:
            return ask(command, prompt, self.root, env, os.path.join(d, 'chat.log'))

    def _grant_denials(self):
        """Add exact grants for this turn's denials; True when any was added."""
        added = False
        for denial in list(last_denials):
            try:
                rule = home_agent_session.grant_for_denial(denial)
            except ValueError as exc:
                if self.say:
                    self.say('Cannot grant %s: %s' % (denial.get('tool_name'), exc))
                continue
            if rule in self.grants:
                continue
            subject = (denial.get('tool_input') or {}).get('command') or (denial.get('tool_input') or {}).get('file_path') or ''
            if self.attended:
                if not (self.confirm and self.confirm('The agent wants to use %s:\n%s\nAllow exactly this for the session?'
                                                      % (denial.get('tool_name'), subject))):
                    continue
            elif self.say:
                self.say('Auto mode: allowing %s for this session: %s' % (denial.get('tool_name'), subject))
            self.grants.append(rule)
            added = True
        return added

    def ask(self, line, history):
        """Return (reply_text, action_dict_or_None). Raises ChatError."""
        reply = self._once(line, history)
        if not self.env.get('UNCLE_REPL_RUNNER') and last_denials and self._grant_denials():
            reply = self._once(line, history)
        if not self.env.get('UNCLE_REPL_RUNNER'):
            return self._split_agent_reply(reply)
        try:
            data = home_actions.parse_reply(reply)
        except ValueError as exc:
            raise ChatError(str(exc))
        if data is None:
            return reply, None
        return data.get('message') or '', data

    def _split_agent_reply(self, reply):
        """Split trailing uncle_action / uncle_cwd blocks off a reply (same rules as the TUI)."""
        import json
        import re
        self.last_cwd = None
        self.notes = []
        pat = re.compile(r'(?:\A|\n)```(uncle_action|uncle_cwd)[ \t]*\n((?:(?!```).)*?)\n?```[ \t]*\Z', re.S)
        rest, blocks = reply.rstrip(), []
        while True:
            m = pat.search(rest)
            if m is None:
                break
            blocks.insert(0, (m.group(1), m.group(2)))
            rest = rest[:m.start()].rstrip()
        text = rest if blocks else reply
        action = None
        seen = {}
        for kind, body in blocks:
            seen.setdefault(kind, []).append(body)
        for kind, bodies in seen.items():
            if len(bodies) > 1:
                self.notes.append('The reply had more than one %s block; none was executed.' % kind)
                continue
            if kind == 'uncle_cwd':
                try:
                    data = json.loads(bodies[0])
                except ValueError:
                    data = None
                if isinstance(data, dict) and isinstance(data.get('path'), str):
                    self.last_cwd = data['path']
                else:
                    self.notes.append('Ignored a malformed uncle_cwd block.')
            else:
                try:
                    action = home_actions.parse_reply(bodies[0])
                except ValueError as exc:
                    raise ChatError(str(exc))
        return text, action

    def cancel(self):
        terminate()

    def terminate(self):
        terminate()
