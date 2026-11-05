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
from process_tree import launch_command, kill_tree, group_options
from triage_chat import extract_reply_from_log, runner_flags, scrub_env, MAX_REPLY, TIMEOUT_TICKS


class ChatError(Exception):
    """A chat turn failed; the message is untrusted text for the caller to filter."""


_lock = threading.Lock()
_current = None
_cancelled = threading.Event()


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
    """Holds the one conversation history owner's runner config (I-6); history is passed in."""

    def __init__(self, root, env):
        self.root, self.env = root, dict(env)

    def command(self):
        override = self.env.get('UNCLE_REPL_RUNNER')
        if override:
            return shlex.split(override)
        return ['claude'] + runner_flags('low', '', 'Read,Glob,Grep', 8)

    def ask(self, line, history):
        """Return (reply_text, action_dict_or_None). Raises ChatError."""
        turns = [{'role': r, 'text': t} for r, t in history]
        if not turns or turns[-1] != {'role': 'user', 'text': line}:
            turns.append({'role': 'user', 'text': line})
        prompt = home_actions.prompt(turns, self.root)
        with tempfile.TemporaryDirectory(prefix='uncle-repl-') as d:
            reply = ask(self.command(), prompt, self.root, scrub_env(self.env), os.path.join(d, 'chat.log'))
        try:
            data = home_actions.parse_reply(reply)
        except ValueError as exc:
            raise ChatError(str(exc))
        if data is None:
            return reply, None
        return data.get('message') or '', data

    def cancel(self):
        terminate()

    def terminate(self):
        terminate()
