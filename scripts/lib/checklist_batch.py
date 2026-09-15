"""Execute reusable check commands in reviewer-approved groups."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import threading
import time
import uuid

from build_timing import event
from checklist_groups import parse, runs, validate
from process_tree import finish_check, kill_tree, launch_command, start_check


def report_draft(checks, results):
    """Deterministic command evidence, deliberately not acceptance decisions."""
    def cell(value):
        return str(value).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')
    lines = ['# Checklist command evidence',
             'Draft only: EXIT_0 does not establish acceptance. Review exact assertions.',
             '', '| ID | Command outcome | Exit | Evidence |',
             '|---|---|---|---|']
    for check in checks:
        row = results.get(check.id, {})
        evidence = row.get('log') or row.get('reason') or 'Not executed in this batch'
        lines.append('| ' + ' | '.join(map(cell, [check.id, row.get('status', 'NOT_RUN'),
                                                   row.get('exit_code', ''), evidence])) + ' |')
    return '\n'.join(lines) + '\n'


def run(mapping, checklist, groups_file, output, jobs=4, timeout=300):
    if not 1 <= jobs <= 8 or timeout <= 0:
        raise ValueError('Jobs must be 1–8 and timeout must be positive')
    raw = Path(checklist).read_bytes()
    checks, by_id, warnings = parse(raw.decode('utf-8'))
    errors = validate(checks, by_id)
    if not checks or errors or warnings:
        raise ValueError('Checklist declarations are missing or invalid: ' + '; '.join(errors + warnings))
    data = json.loads(Path(mapping).read_text())
    if not isinstance(data, dict):
        raise ValueError('Command mapping must be a JSON object')
    digest = hashlib.sha256(raw).hexdigest()
    if data.get('checklist_sha256') != digest:
        raise ValueError('Checklist changed: review and refresh the command mapping')
    commands = data.get('commands')
    if not isinstance(commands, dict) or any(cid not in by_id for cid in commands):
        raise ValueError('Commands must be keyed by known checklist IDs')
    for command in commands.values():
        if not isinstance(command, list) or not command or not all(isinstance(a, str) and a and '\0' not in a for a in command):
            raise ValueError('Each command must be a nonempty argument array')
    expected = runs(checks)
    path = Path(groups_file)
    if path.is_file():
        groups = [line.split() for line in path.read_text().splitlines() if line.strip()]
        if groups != expected:
            raise ValueError('Approved groups are stale or differ from the checklist')
    else:
        groups = [[c.id] for c in checks]
        positions = {c.id: i for i, c in enumerate(checks)}
        if any(positions[d] >= positions[c.id] for c in checks for d in c.depends):
            raise ValueError('Serial order conflicts with dependencies; regenerate approved groups')
    folder = Path(output) / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    results = {}
    stopped = threading.Event()
    active = set()
    lock = threading.Lock()

    def cancel(*_):
        stopped.set()
        with lock:
            for child in active:
                if child.poll() is None:
                    kill_tree(child)

    def execute(cid):
        if stopped.is_set():
            return {"status": "ERROR", "reason": "Batch cancelled"}
        command = commands.get(cid)
        if command is None:
            return {'status': 'NOT_RUN', 'reason': 'No reusable command; requires separate evidence or human action'}
        blocked = [d for d in by_id[cid].depends if results.get(d, {}).get('status') != 'EXIT_0']
        if blocked:
            return {'status': 'NOT_RUN', 'reason': 'Prerequisites did not pass: ' + ', '.join(blocked)}
        # Hash IDs for filenames so checklist identifiers cannot escape output.
        log = folder / (hashlib.sha256(cid.encode()).hexdigest()[:16] + '.log')
        started, tick = time.time(), time.monotonic()
        status, code, reason = 'ERROR', None, ''
        child = None
        with log.open('wb') as stream:
            try:
                with lock:
                    if stopped.is_set():
                        return {"status": "ERROR", "reason": "Batch cancelled"}
                    child = start_check(launch_command(command),
                                        stdout=stream, stderr=subprocess.STDOUT)
                    active.add(child)
                code = child.wait(timeout=timeout)
                status = 'EXIT_0' if code == 0 else 'FAILED'
            except subprocess.TimeoutExpired:
                status, reason = 'TIMEOUT', 'Check exceeded timeout'
                kill_tree(child)
                child.wait()
            except OSError as error:
                reason = str(error)
            finally:
                if child is not None:
                    with lock:
                        active.discard(child)
                    finish_check(child)
        elapsed = time.monotonic() - tick
        event('checklist_item', cid, started, elapsed, code, check_status=status)
        return dict(status=status, exit_code=code, seconds=elapsed, log=str(log), command=command, reason=reason)

    previous = {}
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, cancel)
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for group in groups:
                futures = {cid: pool.submit(execute, cid) for cid in group}
                group_results = {cid: task.result() for cid, task in futures.items()}
                results.update(group_results)
                # Persist after every barrier so earlier evidence survives interruption.
                (folder / 'results.json').write_text(json.dumps({'checklist_sha256': digest, 'results': results}, indent=2) + '\n')
                (folder / 'report-draft.md').write_text(report_draft(checks, results), encoding='utf-8')
                for cid, result in group_results.items():
                    print(cid + ': ' + result['status'], flush=True)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    print('Evidence: ' + str(folder / 'results.json'), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mapping')
    parser.add_argument('--checklist', default='MANUAL_CHECKLIST.md')
    parser.add_argument('--groups', default='.uncle/workflow/checklist-groups/groups.txt')
    parser.add_argument('--output', default='.uncle/workflow/check-runs')
    parser.add_argument('--jobs', type=int, default=int(os.environ.get('WORKFLOW_VERIFY_JOBS', '4')))
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    try:
        results = run(args.mapping, args.checklist, args.groups, args.output, args.jobs, args.timeout)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    # Exit zero describes command execution, not acceptance: the agent still
    # compares exact assertions and accounts for manual or externally covered rows.
    return int(any(row['status'] in ('ERROR', 'FAILED', 'TIMEOUT') for row in results.values()))


if __name__ == '__main__':
    raise SystemExit(main())
