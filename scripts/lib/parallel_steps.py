#!/usr/bin/env python3
"""Run one group of implementation steps concurrently, then merge them back.

Each step gets a mirror of the working tree -- a git worktree plus the dirty
overlay, so it sees what earlier groups produced even though none of it is
committed. Steps in a group own disjoint files by the plan's own declaration,
so their writes cannot collide; the merge copies each step's owned files back.

The declaration is verified, never trusted. A step that writes outside the files
it claimed aborts the whole group and leaves every sandbox in place: the plan's
partition was wrong, and quietly keeping the parts that happened not to collide
would turn a planning error into a silent corruption of the tree.

Nothing here decides what may run together. That is the plan's statement and the
driver's grouping, for the same reason the checklist's grouping is the
reviewer's: the thing doing the work is not the thing that gets to say what is
safe to do at the same time.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triage_guard import make_sandbox, drop_sandbox           # noqa: E402
from step_groups import covers                                # noqa: E402

SKIP = ('.uncle/', '.git/')


def snapshot(root):
    """path -> content hash for every file in the sandbox.

    Not `git diff HEAD`: the sandbox is seeded with the working tree's dirty
    overlay, so everything an earlier group produced is already "changed"
    against HEAD and would be attributed to this step.
    """
    root = Path(root)
    out = {}
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in SKIP):
            continue
        try:
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def changed(before, after):
    """Paths this step created or whose content it altered."""
    return {rel for rel, digest in after.items() if before.get(rel) != digest}


def publish_worker_end(spec, result):
    """Tell the shared TUI stream that this isolated worker has exited.

    Worker runners execute in a sandbox, so their local metrics are not a
    reliable completion signal to the parent TUI.  The scheduler is the one
    process that observes every runner's exit, independent of runner type.
    """
    path = spec['env'].get('UNCLE_STATUS_FILE', '')
    if not path:
        return
    event = {'event': 'end', 'stage': 'implementation-step-%d' % spec['number'],
             'process_exit': result['exit'], 'elapsed_seconds': result['seconds'],
             'runner': spec['env'].get('UNCLE_RESOLVED_RUNNER', ''),
             'model': spec['env'].get('PARALLEL_AGENT_MODEL', '')}
    try:
        with open(path, 'a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(event) + '\n')
    except OSError:
        pass


def run_step(spec, results):
    """One step in its own mirror of the tree. Never raises into the caller."""
    number, sandbox = spec['number'], spec['sandbox']
    started = time.monotonic()
    try:
        before = snapshot(sandbox)
        proc = subprocess.run(spec['command'], cwd=sandbox, env=spec['env'],
                              stdout=open(spec['log'], 'wb'), stderr=subprocess.STDOUT)
        results[number] = {'exit': proc.returncode,
                           'seconds': round(time.monotonic() - started, 3),
                           'wrote': sorted(changed(before, snapshot(sandbox)))}
    except (OSError, ValueError) as error:
        results[number] = {'exit': 1, 'seconds': round(time.monotonic() - started, 3),
                           'wrote': [], 'detail': str(error)}
    publish_worker_end(spec, results[number])


def merge(project, steps, results, owned):
    """Copy each step's owned files back, or refuse the whole group.

    Verification happens for every step before any file is copied: a partial
    merge of a group that contained one bad step is the worst outcome
    available, because the tree then holds half an abandoned change.
    """
    violations = {}
    for number in steps:
        claimed = owned.get(number) or set()
        wrote = set(results.get(number, {}).get('wrote') or ())
        stray = sorted(f for f in wrote if not covers(claimed, f))
        if stray:
            violations[number] = stray
    if violations:
        return violations

    for number in steps:
        sandbox = Path(project) / '.uncle' / 'workflow' / 'parallel' / ('step-%d' % number)
        for name in results.get(number, {}).get('wrote') or ():
            source, target = sandbox / name, Path(project) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return {}


def capture_notes(project, steps, results):
    """Copy worker handoffs, synthesizing one when an agent omitted its prose."""
    synthesized = []
    for step in steps:
        note = step.get('note', '')
        if not note:
            continue
        sandbox = Path(project) / '.uncle' / 'workflow' / 'parallel' / ('step-%d' % step['number'])
        source = sandbox / note
        target = Path(project) / note
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file() and source.read_text(encoding='utf-8').strip():
            shutil.copy2(source, target)
            continue
        result = results.get(step['number'], {})
        files = sorted(result.get('wrote') or ())
        target.write_text(
            '# Implementation step %d handoff\n\n'
            '- Worker exited successfully.\n'
            '- Changed files: %s\n'
            '- Worker log: `%s`\n'
            '- Agent-authored handoff was unavailable; this record was synthesized by the driver.\n'
            % (step['number'], ', '.join(files) if files else '(none)', step.get('log', '')),
            encoding='utf-8')
        synthesized.append(step['number'])
    return synthesized


def main():
    started = time.monotonic()
    request = json.loads(Path(sys.argv[1]).read_text())
    project = request['project']
    steps = request['steps']
    owned = {int(k): set(v) for k, v in request['owned'].items()}
    base = Path(project) / '.uncle' / 'workflow' / 'parallel'

    specs, threads, results = [], [], {}
    for step in steps:
        number = step['number']
        sandbox = base / ('step-%d' % number)
        try:
            make_sandbox(project, sandbox)
        except (OSError, ValueError) as error:
            print('Could not mirror the tree for step %d: %s' % (number, error), file=sys.stderr)
            return 2
        specs.append({'number': number, 'sandbox': str(sandbox),
                      'command': step['command'], 'log': step['log'],
                      'env': dict(os.environ, **step.get('env', {}))})

    for spec in specs:
        thread = threading.Thread(target=run_step, args=(spec, results))
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()

    numbers = [s['number'] for s in steps]
    failed = [n for n in numbers if results.get(n, {}).get('exit')]
    if failed:
        print('Steps failed: %s' % ', '.join(str(n) for n in failed), file=sys.stderr)
        print('Sandboxes kept under %s' % base, file=sys.stderr)
        return 1

    synthesized_notes = capture_notes(project, steps, results)
    if synthesized_notes:
        print('Agent handoff notes were missing for steps %s; driver synthesized them from '
              'verified worker results.' % ', '.join(str(n) for n in synthesized_notes), file=sys.stderr)

    violations = merge(project, numbers, results, owned)
    if violations:
        for number, stray in sorted(violations.items()):
            print('Step %d wrote files it did not declare: %s'
                  % (number, ', '.join(stray)), file=sys.stderr)
        print('Nothing was merged. The plan\'s file ownership was wrong, so the '
              'partition it implies is not safe to act on.', file=sys.stderr)
        print('Sandboxes kept under %s' % base, file=sys.stderr)
        return 3

    for number in numbers:
        drop_sandbox(project, base / ('step-%d' % number))
    print(json.dumps({'merged': numbers,
                      'files': sorted({f for n in numbers for f in results[n]['wrote']}),
                      'elapsed_seconds': round(time.monotonic() - started, 3),
                      'step_seconds': {str(n): results[n]['seconds'] for n in numbers},
                      'worktrees': 'removed'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
