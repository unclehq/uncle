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
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triage_guard import make_sandbox, drop_sandbox           # noqa: E402
from step_groups import covers                                # noqa: E402

SKIP = ('.uncle/', '.git/')


# framework -> its default build-output directory, ignored even before any
# .gitignore says so. A step that scaffolds *and builds* in the same pass
# (a real run's "npm create vite@latest -- --template svelte" step, which
# also ran the build) writes this directory before anyone -- the plan, the
# agent, or a later step -- has had a chance to gitignore it, so waiting on
# .gitignore catches it one merge failure too late. Keyed on the actual
# dependency a project of that framework will have, not a guess from its name.
FRAMEWORK_BUILD_DIRS = (
    (('svelte', '@sveltejs/kit'), 'dist/'),
)


def framework_build_dirs(sandbox):
    try:
        package = json.loads((Path(sandbox) / 'package.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ()
    deps = {}
    if isinstance(package, dict):
        for name in ('dependencies', 'devDependencies'):
            value = package.get(name)
            if isinstance(value, dict):
                deps.update(value)
    return tuple(build_dir for markers, build_dir in FRAMEWORK_BUILD_DIRS if any(m in deps for m in markers))


def ignored_prefixes(project, sandbox):
    """Directories/files this sandbox's git status reports as ignored, plus
    any framework-specific build output (see framework_build_dirs) that is
    always treated the same way regardless of what .gitignore says.

    A step's own setup command (`npm install`, `pip install -e .`, ...) fills
    a gitignored directory with files no plan step ever declared ownership
    of. Left visible to the merge, that always aborts the group -- "the
    plan's file ownership was wrong" -- for a directory nobody was ever
    meant to own. Treating it as invisible to ownership tracking matches how
    the read-only step-groups probe already excludes it, via
    `git ls-files --exclude-standard` in step_groups.changed_files.

    Tries the sandbox's own git status first, then the project's. Either can
    resolve to either repository, and that decides what the returned paths
    are relative to -- not which `cwd` was passed:

    - A worktree sandbox has its own `.git`, is its own repository root, and
      git reports paths relative to it directly.
    - A plain-copy sandbox (an unborn repo, or a project with no git at all
      beyond an empty `.git/`) has no `.git` of its own; it is nested inside
      the *project's* repository (`.uncle/workflow/parallel/step-N`), so git
      run there walks up and finds the project's `.git`, succeeds, and
      reports paths relative to the *project* -- not the sandbox. Stripping
      by a fixed offset computed from the wrong assumption silently returned
      unstripped project-relative paths here once already.

    `git rev-parse --show-toplevel` says which root actually applies in
    either case, so the offset to strip is always `sandbox` relative to
    *that*, never assumed from which command happened to be tried. Empty
    only when neither the sandbox nor the project is a usable git
    repository, in which case every path is tracked exactly as before this
    existed.
    """
    sandbox = Path(sandbox)
    always = framework_build_dirs(sandbox)
    for cwd in (sandbox, project):
        try:
            toplevel = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=cwd,
                                      capture_output=True, check=True, text=True).stdout.strip()
            output = subprocess.run(['git', 'status', '--porcelain', '-z', '--ignored'],
                                    cwd=cwd, capture_output=True, check=True).stdout
            prefix = sandbox.resolve().relative_to(Path(toplevel).resolve()).as_posix()
        except (OSError, ValueError, subprocess.CalledProcessError):
            continue
        prefix = '' if prefix == '.' else prefix + '/'
        result = list(always)
        for entry in output.decode('utf-8', 'replace').split('\0'):
            if entry[:2] != '!!':
                continue
            rel = entry[3:]
            if prefix:
                if not rel.startswith(prefix):
                    continue
                rel = rel[len(prefix):]
            result.append(rel)
        return tuple(result)
    return always


def snapshot(root, project):
    """path -> content hash for every file in the sandbox.

    Not `git diff HEAD`: the sandbox is seeded with the working tree's dirty
    overlay, so everything an earlier group produced is already "changed"
    against HEAD and would be attributed to this step.

    Recomputes ignored_prefixes fresh on every call rather than once up
    front: `git status --ignored` only reports paths that currently exist,
    so a directory a setup command creates (e.g. `npm install`'s
    `node_modules`) is invisible to it before that command has run. Reusing
    a "before" result for the "after" snapshot missed every file the step's
    own setup created, defeating the exclusion for exactly the case it
    exists for.
    """
    root = Path(root)
    ignored = ignored_prefixes(project, root)
    out = {}
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in SKIP):
            continue
        if any(rel == prefix or rel.startswith(prefix.rstrip('/') + '/') for prefix in ignored):
            continue
        try:
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def changed(before, after):
    """Paths this step created or whose content it altered."""
    return {rel for rel, digest in after.items() if before.get(rel) != digest}


def publish_worker_start(spec):
    """Tell the TUI a worker began, the same way status_stage_context does for
    every other stage. Without this the sidepanel has nothing to show until
    the one-shot completion record below lands, so a whole fan-out group looks
    idle for its entire run and only appears, already finished, at the end."""
    path = spec['env'].get('UNCLE_STATUS_FILE')
    if not path:
        return
    stage = 'implementation-step-%d' % spec['number']
    line = json.dumps({'event': 'start', 'model': spec['env'].get('PARALLEL_AGENT_MODEL', ''),
                       'mode': 'act', 'stage': stage, 'stage_index': 0, 'stage_total': 0,
                       'stage_turns': 0}) + '\n'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line.encode('utf-8'))
        finally:
            os.close(fd)
    except OSError:
        pass


def extract_usage(log_path):
    """The same last-`result`-event usage perf_record reads from a stream-json
    log, so a fanned-out step reports real tokens/cost instead of a permanent
    'Unavailable' in the session panel."""
    try:
        lines = Path(log_path).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return {}
    result = {}
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            result = event
    usage = result.get('usage') or {}
    return {
        'reported_error': bool(result.get('is_error')) if result else None,
        'input_tokens': usage.get('input_tokens'),
        'output_tokens': usage.get('output_tokens'),
        'reported_total_tokens': usage.get('total_tokens'),
        'cache_read_tokens': usage.get('cache_read_input_tokens') or usage.get('cached_input_tokens'),
        'cache_write_tokens': usage.get('cache_creation_input_tokens') or usage.get('cache_write_input_tokens'),
        'reported_cost_usd': result.get('total_cost_usd'),
    }


def publish_worker_end(spec, result):
    """Publish the same durable completion record used by normal stage runners."""
    ended = time.time()
    stage = 'implementation-step-%d' % spec['number']
    directory = Path(spec['project']) / '.uncle' / 'workflow' / 'metrics'
    usage = extract_usage(spec['log'])
    row = {'schema': 1, 'kind': 'agent', 'stage': stage,
           'started_at': ended - result['seconds'], 'ended_at': ended,
           'elapsed_seconds': result['seconds'], 'process_exit': result['exit'],
           'reported_error': usage.get('reported_error') if usage.get('reported_error') is not None else result['exit'] != 0,
           'runner': spec['env'].get('UNCLE_RESOLVED_RUNNER', ''),
           'model': spec['env'].get('PARALLEL_AGENT_MODEL', ''),
           'effort': spec['env'].get('PARALLEL_AGENT_EFFORT', ''),
           'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
           'reported_total_tokens': usage.get('reported_total_tokens'), 'cache_read_tokens': usage.get('cache_read_tokens'),
           'cache_write_tokens': usage.get('cache_write_tokens'), 'reported_cost_usd': usage.get('reported_cost_usd'),
           'usage_scope': 'last reported result', 'usage_source': None,
           'input_includes_cache': False,
           'log': spec['log']}
    temporary = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.parallel-worker-', suffix='.json', dir=directory)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(row, stream)
        os.replace(temporary, directory / ('parallel-worker-%d-%d.json' % (spec['number'], int(ended * 1000))))
        subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('session-totals.py')),
                        str(Path(spec['project']) / '.uncle' / 'workflow')],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except OSError:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def run_step(spec, results):
    """One step in its own mirror of the tree. Never raises into the caller."""
    number, sandbox = spec['number'], spec['sandbox']
    started = time.monotonic()
    publish_worker_start(spec)
    try:
        before = snapshot(sandbox, spec['project'])
        proc = subprocess.run(spec['command'], cwd=sandbox, env=spec['env'],
                              stdout=open(spec['log'], 'wb'), stderr=subprocess.STDOUT)
        results[number] = {'exit': proc.returncode,
                           'seconds': round(time.monotonic() - started, 3),
                           'wrote': sorted(changed(before, snapshot(sandbox, spec['project'])))}
    except (OSError, ValueError) as error:
        results[number] = {'exit': 1, 'seconds': round(time.monotonic() - started, 3),
                           'wrote': [], 'detail': str(error)}
    publish_worker_end(spec, results[number])


def merge(project, steps, results, owned, allowlist=()):
    """Copy each step's owned files back, or refuse the whole group.

    Verification happens for every step before any file is copied: a partial
    merge of a group that contained one bad step is the worst outcome
    available, because the tree then holds half an abandoned change.

    `allowlist` (supervision.files_allowlist, e.g. package.json,
    package-lock.json, and vite.config.js) exempts specific paths from the ownership check
    entirely, regardless of which step wrote them or what any step declared.
    Real plans repeatedly under-declared these: one step scaffolds a manifest,
    a later step's own setup command (`npm install` adding a dev dependency)
    rewrites it too, and no step ever claimed that. The merge still applies
    its ordinary last-writer-wins copy to an allowlisted path -- this only
    widens what counts as an expected write, it does not add new merge logic.
    """
    allowlist = set(allowlist)
    violations = {}
    for number in steps:
        claimed = owned.get(number) or set()
        wrote = set(results.get(number, {}).get('wrote') or ())
        stray = sorted(f for f in wrote if f not in allowlist and not covers(claimed, f))
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
    allowlist = request.get('files_allowlist') or ()
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
        specs.append({'number': number, 'project': project, 'sandbox': str(sandbox),
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

    violations = merge(project, numbers, results, owned, allowlist)
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
