"""Race N isolated candidates for one self-hosted stage; promote the first to validate.

A single self-hosted (local-model) worker makes a stage's latency and
reliability depend on one request: it can return malformed or missing
output, stall, or simply take too long. This module runs several candidates
concurrently, each fully isolated (its own directory; nothing it does is
visible to the others or to the live project), validates each as it
finishes with the stage's own existing validator, and promotes only the
first one that actually passes. Every other candidate -- including one that
finishes later, even after a winner is already selected -- is killed and
never touches the canonical output. It has no vote in whether it won.

`launch(n)` starts candidate `n` and returns `(process, directory)`; the
process must already be launched via `process_tree.start_check` (or
equivalent) so it has its own killable process group. `validate(directory)`
inspects a finished candidate's own directory and returns `(ok, result,
detail)`: `ok` is whether it passed, `result` is whatever the caller wants
back for the winner (typically a path to promote), `detail` is a short
diagnostic string kept for every candidate, winner or not.

Selection is "first to report a valid result", not "first to finish": a
candidate that finishes quickly but fails validation does not block a
still-running candidate from winning once it validates. The moment any
candidate validates, every other still-running candidate is killed
synchronously before this function returns -- a candidate that goes on to
"finish" after that point was already killed and cannot overwrite anything,
by construction: candidates only ever write inside their own directory, and
promotion is the caller copying the winner's own result out of it, never
candidates writing to a shared or canonical path themselves.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from process_tree import bash_executable, kill_tree, start_check


class AllCandidatesFailed(RuntimeError):
    """Every candidate crashed, timed out, or failed validation."""

    def __init__(self, candidates):
        self.candidates = candidates
        detail = '; '.join('%s: %s' % (c['id'], c.get('detail', '?')) for c in candidates)
        super().__init__('all %d candidates failed: %s' % (len(candidates), detail))


def run(stage, launch, validate, count=4, timeout=None, evidence_path=None):
    """Race `count` candidates for `stage`. Returns (winner_id, winner_directory,
    winner_result). Raises AllCandidatesFailed if none pass validation."""
    if count < 1:
        raise ValueError('count must be at least 1')
    candidates = [{'id': n, 'status': 'queued', 'detail': ''} for n in range(count)]
    processes = {}
    results = queue.Queue()
    cancel = threading.Event()
    lock = threading.Lock()

    def worker(n):
        started = time.monotonic()
        try:
            process, directory = launch(n)
        except Exception as error:
            candidates[n]['status'] = 'crashed'
            candidates[n]['detail'] = 'launch failed: %s' % error
            results.put((n, False, None))
            return
        with lock:
            processes[n] = process
            candidates[n]['status'] = 'running'
            candidates[n]['directory'] = str(directory)
        try:
            if timeout:
                deadline = started + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        process.wait(timeout=min(remaining, 0.2))
                        break
                    except Exception:
                        if cancel.is_set():
                            candidates[n]['status'] = 'stopped-nonselected'
                            candidates[n]['detail'] = 'stopped: another candidate already won'
                            results.put((n, False, None))
                            return
                        continue
            else:
                while process.poll() is None:
                    if cancel.is_set():
                        candidates[n]['status'] = 'stopped-nonselected'
                        candidates[n]['detail'] = 'stopped: another candidate already won'
                        results.put((n, False, None))
                        return
                    time.sleep(0.05)
        except TimeoutError:
            kill_tree(process)
            process.wait()
            candidates[n]['status'] = 'stopped-timeout'
            candidates[n]['detail'] = 'exceeded %gs timeout' % timeout
            candidates[n]['elapsed'] = time.monotonic() - started
            results.put((n, False, None))
            return
        candidates[n]['elapsed'] = time.monotonic() - started
        if cancel.is_set():
            candidates[n]['status'] = 'stopped-nonselected'
            candidates[n]['detail'] = 'stopped: another candidate already won'
            results.put((n, False, None))
            return
        try:
            ok, result, detail = validate(directory)
        except Exception as error:
            candidates[n]['status'] = 'crashed'
            candidates[n]['detail'] = 'validator raised: %s' % error
            results.put((n, False, None))
            return
        candidates[n]['detail'] = detail or ''
        if ok:
            candidates[n]['status'] = 'validated-winner'
            results.put((n, True, result))
        else:
            candidates[n]['status'] = 'rejected-invalid'
            results.put((n, False, None))

    threads = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(count)]
    for t in threads:
        t.start()

    winner = None
    for _ in range(count):
        n, ok, result = results.get()
        if ok and winner is None:
            winner = (n, result)
            cancel.set()
            with lock:
                stale = dict(processes)
            for other, process in stale.items():
                if other != n and process.poll() is None:
                    kill_tree(process)
    for t in threads:
        t.join()

    # Two candidates can both finish and pass validate() before either one's
    # result is dequeued above -- neither was cancelled yet, so both ran
    # validate() and both saw ok=True, and worker() has no way to know in
    # advance which one this loop will treat as first. Only the one actually
    # dequeued first is promoted (`winner`); relabel every other
    # 'validated-winner' so the evidence never shows two winners for one
    # race, which would otherwise also render as two winning glyphs (AC-6).
    if winner is not None:
        for candidate in candidates:
            if candidate['id'] != winner[0] and candidate['status'] == 'validated-winner':
                candidate['status'] = 'rejected-invalid'
                candidate['detail'] = 'validated, but after another candidate was already selected'

    if evidence_path:
        payload = {
            'schema': 'uncle.artifact/v1', 'kind': 'candidate-race-evidence', 'stage': stage,
            'candidates': candidates, 'selected': winner[0] if winner else None,
        }
        Path(evidence_path).parent.mkdir(parents=True, exist_ok=True)
        Path(evidence_path).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    if winner is None:
        raise AllCandidatesFailed(candidates)
    winning_id, result = winner
    return winning_id, candidates[winning_id]['directory'], result


def _cli(argv):
    """`run` subcommand: race N shell-script candidates.

    Bash callers (stagegate.sh) define what a candidate does, not this
    module: `--launch-script` is executed once per candidate with
    `CANDIDATE_ID`/`CANDIDATE_DIR` in its environment, and `--validate-script`
    inspects that same directory afterward. This keeps the coordinator itself
    generic while letting the existing self-hosted invocation body (streamed
    output, delivery-file contract, etc.) stay exactly what it already is.
    """
    import argparse

    parser = argparse.ArgumentParser(prog='candidate_race.py')
    sub = parser.add_subparsers(dest='action', required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--stage', required=True)
    run_parser.add_argument('--count', type=int, default=4)
    run_parser.add_argument('--timeout', type=float, default=None)
    run_parser.add_argument('--work-dir', required=True)
    run_parser.add_argument('--launch-script', required=True)
    run_parser.add_argument('--validate-script', required=True)
    run_parser.add_argument('--evidence')
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    def launch(n):
        directory = work_dir / ('candidate-%d' % n)
        directory.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CANDIDATE_ID=str(n), CANDIDATE_DIR=str(directory))
        process = start_check([bash_executable(), args.launch_script], env=env)
        return process, directory

    def validate(directory):
        candidate_id = Path(directory).name.rpartition('-')[2]
        env = dict(os.environ, CANDIDATE_ID=candidate_id, CANDIDATE_DIR=str(directory))
        result = subprocess.run([bash_executable(), args.validate_script], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, check=False)
        detail = result.stdout.strip()[:500]
        return result.returncode == 0, str(directory), detail

    try:
        _, directory, _ = run(args.stage, launch, validate, count=args.count,
                               timeout=args.timeout, evidence_path=args.evidence)
    except AllCandidatesFailed as error:
        print(str(error), file=sys.stderr)
        return 1
    print(directory)
    return 0


if __name__ == '__main__':
    sys.exit(_cli(sys.argv[1:]))
