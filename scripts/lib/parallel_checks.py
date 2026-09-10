"""Run explicitly approved independent check groups; keep evidence ordered."""
from process_tree import bash_executable, cleanup_directory, finish_check, start_check, kill_tree

import argparse
import difflib
from concurrent.futures import ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

from verification_manifest import manifest


def run(args):
    run_started = time.monotonic()
    passed = failed = 0
    commands = Path(args.commands).read_text(encoding="utf-8").splitlines()
    groups = {}
    previous = 0
    for row in Path(args.groups).read_text(encoding="utf-8").splitlines():
        indices = [int(i) for i in row.split()]
        if (len(indices) < 2 or indices[0] <= previous or indices[-1] > len(commands)
                or indices != list(range(indices[0], indices[-1] + 1))):
            raise ValueError("Parallel groups must contain ordered, disjoint, consecutive command numbers.")
        groups[indices[0] - 1] = indices[-1]
        previous = indices[-1]
    if not 1 <= args.jobs <= 8:
        raise ValueError("WORKFLOW_VERIFY_JOBS must be from 1 to 8.")
    expected = Path(args.expected).read_text(encoding="utf-8") if args.expected else None
    scopes = args.paths
    halted = threading.Event()
    children = set()
    lock = threading.Lock()
    violations = []

    def intact():
        if expected is None:
            return True
        try:
            actual = manifest(scopes)
            if actual == expected:
                return True
            reason = "Protected verification inputs changed.\n" + "".join(
                difflib.unified_diff(expected.splitlines(keepends=True),
                                     actual.splitlines(keepends=True),
                                     "approved-manifest", "current-manifest"))
        except (OSError, ValueError) as error:
            reason = str(error)
        with lock:
            violations.append(reason)
        halted.set()
        return False

    def record(command, elapsed, status, log):
        if not args.metrics:
            return
        try:
            directory = Path(args.metrics)
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=directory, prefix=".pending.", delete=False) as out:
                json.dump(dict(schema=1, kind="check", stage=command,
                               elapsed_seconds=round(elapsed, 6), process_exit=status,
                               ended_at=time.time(), speculative=False, log=log,
                               input_tokens=None, output_tokens=None), out)
            os.replace(out.name, out.name + ".json")
        except OSError:
            pass  # Metrics do not change acceptance.

    def check(index, directory):
        command = commands[index]
        started = time.monotonic()
        log = directory / str(index)
        with log.open("wb") as output:
            if halted.is_set() or not intact():
                output.write(b"NOT RUN: protected verification inputs changed.\n")
                return 125, log
            with lock:
                if halted.is_set():
                    output.write(b"NOT RUN: protected verification inputs changed.\n")
                    return 125, log
                check_env = dict(os.environ)
                for key in ('UNCLE_STATUS_FILE', 'UNCLE_PROJECT_ROOT', 'UNCLE_CONFIG',
                            'STAGEGATE_RUN_ID', 'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE',
                            'DOCUMENT_BUDGET_SOURCE'):
                    check_env.pop(key, None)
                child = start_check([bash_executable(), "-c", command], env=check_env,
                                    stdout=output, stderr=subprocess.STDOUT)
                children.add(child)
            status = child.wait()
            with lock:
                finish_check(child)
                children.discard(child)
            intact()  # Check each command, even if a peer later restores bytes.
        record(command, time.monotonic() - started, status, args.log)
        return status, log

    # Stop all running process groups when the executor is interrupted.
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt

    old_term = signal.signal(signal.SIGTERM, interrupted)
    old_break = signal.signal(signal.SIGBREAK, interrupted) if hasattr(signal, 'SIGBREAK') else None
    temporary = tempfile.TemporaryDirectory(prefix="uncle-checks-")
    pool = ThreadPoolExecutor(max_workers=args.jobs)
    try:
        with open(args.out, "w", encoding="utf-8", newline="\n") as results, open(args.log, "wb") as combined:
            index = 0
            while index < len(commands):
                end = groups.get(index, index + 1)
                futures = [pool.submit(check, i, Path(temporary.name)) for i in range(index, end)]
                for i, future in zip(range(index, end), futures):
                    # Python <=3.13 on Windows cannot dispatch SIGBREAK while
                    # blocked in an unbounded condition wait. Return to Python
                    # regularly so cancellation reaches the cleanup below.
                    while not future.done():
                        wait([future], timeout=0.1)
                    status, log = future.result()
                    if status == 0:
                        passed += 1
                    else:
                        failed += 1
                    results.write(f"{status}\t{commands[i]}\n")
                    results.flush()
                    combined.write(f"\n$ {commands[i]}\n".encode())
                    with log.open("rb") as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            combined.write(chunk)
                    combined.flush()
                    label = 'INVALID' if halted.is_set() else ('PASS' if status == 0 else f'FAIL({status})')
                    print(f"  {label}      {commands[i]}", flush=True)
                if halted.is_set():
                    Path(args.integrity_log).write_bytes(("\n".join(violations) + "\n").encode("utf-8"))
                    return 3
                index = end
        print(f"Verification summary: {passed} passed, {failed} failed; "
              f"{time.monotonic() - run_started:.1f}s elapsed; up to {args.jobs} workers. "
              f"Full output: {args.log}", flush=True)
        return 0  # Individual test failures are classified by the driver.
    finally:
        halted.set()
        with lock:
            for child in children:
                try:
                    kill_tree(child)
                except ProcessLookupError:
                    pass
        pool.shutdown(wait=True)
        try:
            cleanup_directory(temporary)
        finally:
            if old_break is not None:
                signal.signal(signal.SIGBREAK, old_break)
            signal.signal(signal.SIGTERM, old_term)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("commands", "groups", "out", "log"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    for name in ("paths", "expected", "integrity-log", "metrics"):
        parser.add_argument("--" + name, default="")
    try:
        raise SystemExit(run(parser.parse_args()))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    except KeyboardInterrupt:
        raise SystemExit(130)
