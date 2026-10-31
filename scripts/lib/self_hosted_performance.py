"""Project-local advisory budgets and exact, read-only deliverable reuse.

No credentials, Git commands, hosted-runner hooks or model-specific tokenizer.
Incomplete snapshots disable reuse rather than weakening its identity.
"""
import contextlib
import contextvars
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit

ACTIVE = contextvars.ContextVar('self_hosted_budget', default=None)
REPLAY = contextvars.ContextVar('self_hosted_replay', default=None)
VERSION = 1


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def enabled(name, default='on'):
    from self_hosted_http import option
    value = option(name, default)
    if value not in ('on', 'off', 'true', 'false', '1', '0'):
        raise ValueError('self-hosted.%s must be on or off' % name)
    return value in ('on', 'true', '1')


def event(kind, **fields):
    print(json.dumps(dict(type='self_hosted_' + kind, stage=os.environ.get('UNCLE_STATUS_STAGE', ''), **fields)), flush=True)


def location(root):
    return Path(root) / '.uncle' / 'self-hosted-performance'


@contextlib.contextmanager
def locked(root):
    path = location(root)
    for candidate in (Path(root) / '.uncle', path):
        if candidate.is_symlink():
            raise OSError('Performance storage must not be a symlink')
    path.mkdir(parents=True, exist_ok=True)
    if any((path / name).is_symlink() for name in ('.gitignore', 'lock')):
        raise OSError('Performance storage files must not be symlinks')
    # Also ignored in projects without an Uncle-managed root .gitignore.
    (path / '.gitignore').write_text('*\n', encoding='utf-8')
    with (path / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield path


def read_json(path, default, max_bytes=4 * 1024 * 1024):
    try:
        if any(p.is_symlink() for p in (path, path.parent, path.parent.parent)) or path.stat().st_size > max_bytes:
            return default
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def atomic(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(value))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def kind_for(name):
    name = name.replace('_', '-')
    if 'ops' in name or 'edits' in name or 'resolution' in name:
        return 'ops'
    if 'outline' in name:
        return 'outline'
    if 'review' in name or 'worker-packet' in name:
        return 'review'
    return 'document'


class Budget:
    DEFAULTS = {'ops': 1024, 'review': 2048, 'outline': 4096, 'document': 8192}

    def __init__(self, root, name, cap):
        from self_hosted import config_stage
        from self_hosted_http import _config_values, positive_option
        self.root = Path(os.environ.get('UNCLE_PROJECT_ROOT') or root)
        self.kind = kind_for(name)
        stage = os.environ.get('UNCLE_STATUS_STAGE', '')
        self.family = config_stage(stage, _config_values()) or stage or name
        self.enabled = enabled('learned-budgets')
        self.soft = False
        self.retried = False
        self.tokens, self.estimates = [], []
        self.last_tools, self.repeats = None, 0
        self.repeat_limit = positive_option('budget-repeat-turns', 3, minimum=2)
        history = read_json(location(self.root) / 'history.json', []) if self.enabled else []
        if not isinstance(history, list):
            history = []
        samples = sorted(t for row in history if isinstance(row, dict) and row.get('family') == self.family
                         and row.get('kind') == self.kind and row.get('outcome') == 'valid'
                         and isinstance(row.get('output_tokens'), list)
                         for t in row['output_tokens'] if isinstance(t, int) and t > 0)
        expected = samples[math.ceil(len(samples) * .9) - 1] if samples else self.DEFAULTS[self.kind]
        self.expected = min(cap, positive_option('budget-max-tokens', 16384), max(128, expected))
        self.threshold = min(cap, positive_option('budget-max-tokens', 16384), self.expected * 2)

    def intervene(self, reason):
        if self.soft:
            event('budget_intervention', action='hard', reason=reason, expected_tokens=self.expected)
            raise ValueError('Self hosted step made no progress after its final-deliverable request')
        self.soft = True
        event('budget_intervention', action='soft', reason=reason, expected_tokens=self.expected,
              threshold_tokens=self.threshold)

    def observe(self, usage, reason):
        self.tokens.append((usage or {}).get('completion_tokens'))
        if str(reason).startswith('early_stop:') or reason == 'length':
            self.retried = True
            if self.enabled and self.soft:
                event('budget_intervention', action='hard', reason=reason)

    def repeated(self, observations):
        if not self.enabled or not observations:
            self.last_tools, self.repeats = None, 0
            return False
        identity = digest(encoded(observations))
        self.repeats = self.repeats + 1 if identity == self.last_tools else 1
        self.last_tools = identity
        return self.repeats >= self.repeat_limit

    def finish(self, text, outcome):
        if not self.enabled:
            return
        row = dict(family=self.family, kind=self.kind, deliverable_bytes=len(text.encode('utf-8')),
                   output_tokens=self.tokens[-256:], estimated_output_tokens=self.estimates[-256:], turns=len(self.tokens),
                   outcome=('retried' if (self.soft or self.retried) and outcome == 'valid' else outcome))
        try:
            with locked(self.root) as path:
                rows = read_json(path / 'history.json', [])
                rows = rows if isinstance(rows, list) else []
                atomic(path / 'history.json', (rows + [row])[-256:])
        except OSError:
            pass  # advisory state must never turn a valid delivery into a failure


def snapshot(policy, ignored=()):
    """Hash all tool-visible files, including untracked and supplied workflow inputs.

    This intentionally over-invalidates: additions affect grep/list_dir, even if
    the earlier execution did not read that path. No mtime or Git shortcut.
    Symlinks, special files and oversized trees fail closed. Secret contents
    are never opened, including for a digest.
    """
    entries, total = [], 0
    def unreadable(error):
        raise error
    for directory, dirs, files in os.walk(policy.root, followlinks=False, onerror=unreadable):
        relative = Path(directory).relative_to(policy.root)
        dirs[:] = sorted(d for d in dirs if (relative / d).as_posix() not in ignored and
                         ((relative / d).parts == ('.uncle',) or not policy.hidden((relative / d).parts)))
        for name in sorted(dirs + files):
            rel = (relative / name).as_posix()
            if rel in ignored or policy.hidden((relative / name).parts):
                continue
            entries.append([rel, 'name'])
            if len(entries) > 20000:
                return None
            original = policy.root / rel
            if original.is_symlink():
                return None
            try:
                path = policy.resolve(rel)
            except ValueError:
                continue
            if path.is_dir():
                continue
            if not path.is_file():
                return None
            total += path.stat().st_size
            if total > 64 * 1024 * 1024:
                return None
            entries.append([rel, digest(path.read_bytes())])
    return digest(encoded(entries))


class Reuse:
    def __init__(self, values, prompt, policy, schema, name, limit, turns, seconds, stage, tools_required=True, side='agent'):
        from self_hosted_http import configure_request_options, reasoning_effort, temperature, positive_option
        self.root = Path(os.environ.get('UNCLE_PROJECT_ROOT') or policy.root)
        self.key, self.inputs = None, None
        self.max_bytes = positive_option('reuse-max-bytes', 16 * 1024 * 1024)
        self.policy = policy
        # These are produced by the runner itself during a turn. They are not
        # task inputs unless referenced or inspected. Such tasks are ineligible,
        # including ancestor searches/listings whose result could depend on them.
        self.ignored = {'.uncle/workflow/logs', '.uncle/workflow/read-cache'}
        status = os.environ.get('UNCLE_STATUS_FILE')
        if status:
            try:
                self.ignored.add(Path(status).resolve().relative_to(policy.root).as_posix())
            except ValueError:
                pass
        if (not enabled('result-reuse') or policy.write or policy.shell or schema is None or stage is not None
                or (temperature() > 0 and not enabled('reuse-nonzero-temperature', 'off'))):
            return
        if any(path in prompt or Path(path).name in prompt for path in self.ignored):
            return
        values = configure_request_options(values)
        base = urlsplit(values.get('base_url', ''))
        # A URL containing userinfo/query credentials is ineligible, never persisted.
        if base.username or base.password or base.query or base.fragment:
            return
        try:
            self.inputs = snapshot(policy, self.ignored)
            if self.inputs is None:
                return
            # Hash the implementation too: changed validators/tools/system text
            # cannot reuse an entry from an older runtime.
            implementation = [digest((Path(__file__).parent / file).read_bytes()) for file in
                              ('self_hosted_performance.py', 'http_agent.py', 'self_hosted_http.py',
                               'self_hosted_stream.py', 'self_hosted.py')]
            controls = {k: v for k, v in os.environ.items() if k.startswith(('WORKFLOW_SELF_HOSTED_', 'WORKFLOW_EFFORT_'))
                        and not any(s in k for s in ('API_KEY', 'SECRET', 'PASSWORD'))}
            from self_hosted_http import _config_values
            config = {k: v for k, v in _config_values().items() if k.startswith('self-hosted.') or
                      k.endswith(('.effort', '.request-options', '.turn-output-tokens', '.final-output-tokens'))}
            self.key = digest(encoded(dict(version=VERSION, model=values.get('model'),
                base=urlunsplit(base), options=values['_request_options'], effort=reasoning_effort(values),
                temperature=temperature(), prompt=prompt, root=str(policy.root), tools=policy.tools(),
                schema=schema, name=name, inputs=self.inputs, limit=limit, turns=turns, seconds=seconds,
                stage=os.environ.get('UNCLE_STATUS_STAGE', ''), delivery=os.environ.get('UNCLE_ARTIFACT_DELIVERY', ''),
                tools_required=tools_required, side=side,
                ignored=sorted(self.ignored),
                implementation=implementation, controls=controls, config=config)))
        except (OSError, ValueError):
            self.key = None

    def get(self):
        if not self.key:
            return None
        try:
            with locked(self.root) as path:
                self.evict(path)
                file = path / (self.key + '.json')
                row = read_json(file, {}, self.max_bytes)
                text = row.get('text') if isinstance(row, dict) else None
                if isinstance(text, str) and row.get('digest') == digest(text.encode()):
                    file.touch()
                    return text
        except OSError:
            pass
        return None

    def discard(self):
        if self.key:
            try:
                with locked(self.root) as path:
                    (path / (self.key + '.json')).unlink(missing_ok=True)
            except OSError:
                pass

    def evict(self, path):
        files = sorted((p for p in path.glob('*.json') if p.name != 'history.json'), key=lambda p: p.stat().st_mtime_ns)
        size = sum(p.stat().st_size for p in files)
        for file in files:
            if size <= self.max_bytes:
                break
            size -= file.stat().st_size
            file.unlink()

    def put(self, text):
        if not self.key or self.policy.reuse_unsafe:
            return
        row = dict(text=text, digest=digest(text.encode()))
        if len(encoded(row)) > self.max_bytes:
            return
        try:
            # Inputs may have changed while the model was thinking. Never save
            # a result under a stale snapshot; no clean-tree requirement.
            if snapshot(self.policy, self.ignored) != self.inputs:
                return
            # Verify actual reads too, including transient changes that were
            # reverted before the closing snapshot. Full file bytes matter even
            # when the model requested only a few lines.
            for file, observed in list(self.policy.input_digests.items()):
                if any(file == self.policy.root / name or self.policy.root / name in file.parents
                       for name in self.ignored):
                    return
                if digest(file.read_bytes()) != observed:
                    return
            from http_agent import run_tool
            for name, arguments, observed in self.policy.reuse_observations:
                try:
                    target = self.policy.resolve(arguments.get('path'))
                except ValueError:
                    return
                if any(target == self.policy.root / entry or self.policy.root / entry in target.parents or
                       (name in ('grep', 'list_dir') and target in (self.policy.root / entry).parents)
                       for entry in self.ignored):
                    return
                if digest(run_tool(self.policy, name, arguments).encode()) != observed:
                    return
            with locked(self.root) as path:
                atomic(path / (self.key + '.json'), row)
                self.evict(path)
        except OSError:
            pass


def replay(text):
    """Use the SSE assembler and ordinary agent validation/publication path."""
    from self_hosted_stream import assemble
    def lines():
        for offset in range(0, len(text), 1024):
            yield 'data: ' + json.dumps({'choices': [{'delta': {'content': text[offset:offset + 1024]}}]})
            yield ''
        yield 'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': 'stop'}]})
        yield ''
        yield 'data: [DONE]'
        yield ''
    token = ACTIVE.set(None)
    try:
        return assemble(lines())
    finally:
        ACTIVE.reset(token)


def clear(root):
    with locked(root) as path:
        for file in path.glob('*.json'):
            if file.name != 'history.json':
                file.unlink()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['clear'])
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    clear(Path(args.root).resolve())
