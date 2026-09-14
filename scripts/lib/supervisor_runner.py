"""The tool-free, bounded supervisor worker: one prompt in, one reply out.

Only `claude` is supported. The argv is fixed (CAP-4): bare mode, no tools,
no slash commands, no setting sources, no MCP, no session persistence, a
dollar cap. The environment is an allowlist, the cwd an empty temporary
directory, and the parent enforces the deadline and a 1 MiB output cap
itself while the worker runs: a runner that ignores its own limits is
killed with its whole tree, and the tree dies with the parent (D-16).
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from process_tree import launch_command, kill_tree, start_check

MAX_REPLY = 1024 * 1024
POLL_SECONDS = 0.1
GRACE_SECONDS = 12 if os.name == 'nt' else 2
ENV_ALLOW = ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TERM', 'ANTHROPIC_API_KEY')
ENV_ALLOW_WINDOWS = ('SYSTEMROOT', 'SYSTEMDRIVE', 'COMSPEC', 'PATHEXT', 'WINDIR', 'TEMP', 'TMP',
                     'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMDATA')


def worker_env(environ, home):
    """The allowlisted environment: resolved PATH, locale, the API key, temporary HOME/config/cache."""
    env = {}
    names = ENV_ALLOW + (ENV_ALLOW_WINDOWS if os.name == 'nt' else ())
    for name in names:
        value = environ.get(name)
        if value:
            env[name] = value
    home = str(home)
    env['HOME'] = home
    env['XDG_CONFIG_HOME'] = os.path.join(home, 'config')
    env['XDG_CACHE_HOME'] = os.path.join(home, 'cache')
    env['TMPDIR'] = os.path.join(home, 'tmp')
    for sub in ('config', 'cache', 'tmp', 'cwd'):
        os.makedirs(os.path.join(home, sub), exist_ok=True)
    return env


def build_command(config, root, environ=None):
    """(argv, env, temporary-home) for one call, or ValueError('unavailable ...')."""
    environ = os.environ if environ is None else environ
    if config.runner not in ('claude',):
        raise ValueError('unavailable: supervision.runner %s is not supported; use claude' % config.runner)
    executable = environ.get('WORKFLOW_CLAUDE_CMD') or 'claude'
    resolved = shutil.which(executable)
    if not resolved:
        raise ValueError('unavailable: %s is not on PATH' % executable)
    home = tempfile.mkdtemp(prefix='uncle-supervisor-')
    env = worker_env(environ, home)
    argv = [resolved, '--bare', '-p', '--tools', '', '--disable-slash-commands', '--setting-sources', '',
            '--strict-mcp-config', '--permission-mode', 'dontAsk', '--no-session-persistence',
            '--output-format', 'stream-json', '--verbose', '--model', config.model, '--effort', config.effort,
            '--max-budget-usd', '%.2f' % config.call_max_cost_usd]
    return argv, env, home


def _text_of(content):
    if isinstance(content, str):
        return content
    return ''.join(str(item.get('text', '')) for item in content or []
                   if isinstance(item, dict) and item.get('type') == 'text')


def parse_stream(lines):
    """(reply, usage, cost, error) from stream-json: last assistant text, the result's usage."""
    reply, usage, cost, error = '', None, None, ''
    for line in lines:
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get('type')
        if kind == 'assistant':
            text = _text_of((event.get('message') or {}).get('content'))
            if text.strip():
                reply = text
        elif kind == 'result':
            if isinstance(event.get('usage'), dict):
                usage = event['usage']
            cost = event.get('total_cost_usd', cost)
            flag = event.get('is_error')
            if flag is True or str(flag).lower() == 'true':
                error = str(event.get('error_detail') or event.get('subtype') or 'runner reported an error')
            if isinstance(event.get('result'), str) and not reply.strip():
                reply = event['result']
    return reply, usage, cost, error


class SupervisorRequest:
    """One worker call in a background thread; `poll()` returns the result dict once."""

    def __init__(self, command, prompt, env, home, log_path, meta):
        self.meta = dict(meta)
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.log_path = str(log_path)
        self.home = home
        self._result = None
        self.thread = threading.Thread(target=self._run, args=(command, prompt, env), daemon=True)
        self.thread.start()

    def cancel(self):
        self.cancelled.set()

    def poll(self):
        if self._result is None:
            try:
                self._result = self.events.get_nowait()
            except queue.Empty:
                return None
        return self._result

    def result(self, wait=False):
        if wait and self._result is None:
            self.thread.join(timeout=self.meta.get('deadline', 300) + GRACE_SECONDS + 5)
            return self.poll()
        return self.poll()

    def _run(self, command, prompt, env):
        started = time.monotonic()
        outcome = {'status': 'error', 'detail': '', 'reply': '', 'usage': None, 'cost': None, 'exit': None,
                   'log': self.log_path, 'usage_source': None}
        process = None
        try:
            Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
            prompt_path = self.log_path + '.prompt'
            with open(prompt_path, 'w', encoding='utf-8') as fh:
                fh.write(prompt)
            deadline = started + float(self.meta.get('deadline', 300))
            written = 0
            flooded = threading.Event()
            with open(self.log_path, 'wb') as log:
                try:
                    # The worker is an owned tree (POSIX session under a parent
                    # watch, Windows Job with kill-on-close) fed the prompt on
                    # stdin; its combined output is read here and capped while
                    # it runs, not measured after it exits (D-16).
                    process = start_check(launch_command(command), prompt=prompt.encode('utf-8'),
                                          cwd=os.path.join(self.home, 'cwd'), env=env,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                except OSError as exc:
                    outcome.update(status='unavailable', detail=str(exc))
                    return

                def pump():
                    nonlocal written
                    try:
                        while True:
                            chunk = process.stdout.read(65536)
                            if not chunk:
                                return
                            written += len(chunk)
                            if written > MAX_REPLY:
                                flooded.set()
                                return
                            log.write(chunk)
                    except (OSError, ValueError):
                        return

                reader = threading.Thread(target=pump, daemon=True)
                reader.start()
                try:
                    while True:
                        if self.cancelled.is_set():
                            outcome.update(status='cancelled', detail='cancelled by the host')
                            break
                        if flooded.is_set():
                            outcome.update(status='error', detail='reply exceeds 1 MiB; worker killed and output discarded')
                            break
                        if time.monotonic() >= deadline:
                            outcome.update(status='timeout', detail='deadline %ds' % self.meta.get('deadline', 300))
                            break
                        try:
                            outcome['exit'] = process.wait(timeout=POLL_SECONDS)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                finally:
                    if process.poll() is None:
                        kill_tree(process)
                        try:
                            process.wait(timeout=GRACE_SECONDS)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    try:
                        process.stdout.close()
                    except OSError:
                        pass
                    reader.join(timeout=GRACE_SECONDS)
                    if outcome['exit'] is None:
                        outcome['exit'] = process.returncode
                log.flush()
            if outcome['status'] in ('cancelled', 'timeout') or flooded.is_set():
                return
            with open(self.log_path, encoding='utf-8', errors='replace') as fh:
                reply, usage, cost, error = parse_stream(fh)
            outcome.update(usage=usage, cost=cost, usage_source='stream-json result' if usage else None)
            if error:
                outcome.update(status='error', detail=error)
            elif outcome['exit']:
                outcome.update(status='unavailable' if outcome['exit'] in (127, 126) else 'error',
                               detail='runner exited with status %s' % outcome['exit'])
            elif not reply.strip():
                outcome.update(status='error', detail='runner returned no reply')
            else:
                outcome.update(status='reply', reply=reply)
        except (OSError, ValueError) as exc:
            outcome.update(status='error', detail=str(exc))
        finally:
            outcome['elapsed'] = time.monotonic() - started
            shutil.rmtree(self.home, ignore_errors=True)
            self.events.put(outcome)


if __name__ == '__main__':
    sys.exit(0)
