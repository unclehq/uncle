from process_tree import check_timeout, wait_check
"""Run explicitly approved independent check groups; keep evidence ordered."""
from process_tree import bash_executable, cleanup_directory, finish_check, start_check, kill_tree

import argparse
import difflib
from concurrent.futures import ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import re
import signal
import shlex
import subprocess
import tempfile
import threading
import time

from verification_manifest import manifest
from shell_syntax import syntax_command
import check_reuse
from browser_install import prepare


# These are prerequisites, not an attempt to infer arbitrary application test
# dependencies.  A browser suite that starts `vite preview` cannot give useful
# evidence after its preceding build has failed; it otherwise waits for
# Playwright's 60-second webServer timeout.  Mutation controls likewise have
# no useful meaning after the ordinary unit suite is already red.
BUILD = re.compile(r'\b(?:npm|yarn|pnpm)\s+(?:run\s+)?build\b|\bvite\s+build\b|\btsc\b|\bwebpack\b|\brollup\b|\besbuild\b', re.I)
E2E = re.compile(r'\bplaywright\s+test\b|\bcypress\b|\be2e\b|\bwdio\b|\bselenium\b|\bpuppeteer\b|\bnightwatch\b', re.I)
UNIT = re.compile(r'\b(?:vitest|jest|mocha|pytest)\b|\bgo\s+test\b|\bcargo\s+test\b|\bnode\s+--test\b', re.I)
MUTATION = re.compile(r'mutat|defect|inject', re.I)


def npm_script(command):
    """Resolve a simple npm script without executing shell text or guessing its name."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        words = list(lexer)
        if not words or words.pop(0) != 'npm':
            return ''
        root = Path.cwd()
        if words[:1] == ['--prefix'] and len(words) >= 2:
            root = root / words[1]
            words = words[2:]
        if len(words) < 2 or words[0] not in ('run', 'run-script'):
            return ''
        name = words[1]
        tail = words[2:]
        if tail and (tail[0] != '--' or any(re.search(r'[;&|<>`$()]', arg) for arg in tail)):
            return ''
        value = json.loads((root / 'package.json').read_text())['scripts'][name]
        return value if isinstance(value, str) else ''
    except (OSError, ValueError, KeyError, TypeError):
        return ''


def command_evidence(command):
    return command + '\n' + npm_script(command)


def prerequisite_skip(command, failed_build, failed_unit, failed_e2e):
    command = command_evidence(command)
    if E2E.search(command) and failed_build:
        return 'NOT RUN: an earlier build command failed; browser tests require its build output.\n'
    if MUTATION.search(command) and (failed_build or failed_unit or failed_e2e):
        return 'NOT RUN: an earlier build, unit, or browser command failed; mutation controls would be unreliable.\n'
    return ''


# How many Playwright failures a green-check run tolerates before it stops. One failure used to end the run, which turned
# "2 of 33 browser tests ran" into the evidence the test review, supervisor and audit all worked from: the 29 untouched tests
# were unknown, and the mutation controls were skipped because "a browser command failed". It also made
# browser_application_unrunnable() unable to ever fire, since that needs two or more missing-element failures. Five still bounds
# a blank page (every locator waits out its timeout, and the suite stops after five of them) while letting an ordinary
# suite with a failure or two report all of its results.
DEFAULT_E2E_MAX_FAILURES = 5


def e2e_max_failures():
    return os.environ.get('WORKFLOW_GREEN_E2E_MAX_FAILURES', str(DEFAULT_E2E_MAX_FAILURES)).strip()


def execution_command(command):
    """Bound a known-bad browser suite without changing its approved evidence.

    A blank application page makes every locator in a Playwright suite wait for
    its timeout, so the suite gets a small, overridable failure budget while it
    executes (DEFAULT_E2E_MAX_FAILURES). Keep the command recorded in the report
    unchanged. Set WORKFLOW_GREEN_E2E_MAX_FAILURES=0 to retain Playwright's
    normal unlimited behavior, or another number to change the budget.
    """
    script = npm_script(command)
    # Forward only to a single known Playwright invocation. Arbitrary scripts,
    # pipelines and other runners must never receive Playwright-specific flags.
    if script and re.fullmatch(r'(?:npx\s+)?playwright\s+test(?:\s+[^;&|<>`$()]*)?', script):
        configured = e2e_max_failures()
        if (configured.isdigit() and int(configured) > 0
                and '--max-failures' not in script + command):
            separator = ' ' if ' -- ' in command else ' -- '
            return command + separator + '--max-failures=' + configured
        return command
    if not E2E.search(command) or not re.search(r'\bplaywright\s+test\b', command, re.I):
        return command
    if re.search(r'--max-failures(?:=|\s+)', command):
        return command
    configured = e2e_max_failures()
    if not configured.isdigit() or int(configured) <= 0:
        return command
    # Attach the flag to the Playwright invocation itself, not the end of the line: in a
    # compound command such as `(npx vitest run) & (npx playwright test) & wait` the end
    # of the line is `wait`, which rejects it and fails the whole parallel group.
    return re.sub(r'(\bplaywright\s+test\b)', rf'\1 --max-failures={configured}', command, flags=re.I)


def browser_application_unrunnable(log):
    """Recognize the browser's empty-root failure without parsing test prose.

    A build can compile successfully while React crashes during its first
    render.  In that case the browser suite records a number of selector
    misses, including its root-mount check.  That is not an ordinary failed
    assertion which an unattended run may carry to final audit: there is no
    usable application.  Require both the explicit root reference and several
    missing-element failures so one unrelated locator failure remains a normal
    test result.
    """
    try:
        text = Path(log).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    return '#root' in text and text.count('element(s) not found') >= 2


def _test_status(state):
    path = os.environ.get('UNCLE_STATUS_FILE')
    if not path:
        return
    try:
        event = json.dumps({'event': 'test_execution', 'state': state,
                            'id': str(os.getpid())}) + '\n'
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, event.encode('utf-8'))
        finally:
            os.close(fd)
    except OSError:
        pass  # Display telemetry cannot change verification outcomes.


def run(args):
    _test_status('Running')
    try:
        return _run_checks(args)
    finally:
        _test_status('Stopped')


def _run_checks(args):
    timeout = check_timeout()
    run_started = time.monotonic()
    passed = failed = 0
    commands = [row.removesuffix(b'\r').decode('utf-8')
                for row in Path(args.commands).read_bytes().split(b'\n')]
    if commands and commands[-1] == '':
        commands.pop()
    groups = {}
    previous = 0
    for row in Path(args.groups).read_text(encoding="utf-8").splitlines():
        indices = [int(i) for i in row.split()]
        if (len(indices) < 2 or indices[0] <= previous or indices[-1] > len(commands)
                or indices != list(range(indices[0], indices[-1] + 1))):
            raise ValueError("Parallel groups must contain ordered, disjoint, consecutive command numbers.")
        groups[indices[0] - 1] = indices[-1]
        previous = indices[-1]
    if not 1 <= args.jobs <= 16:
        raise ValueError("WORKFLOW_VERIFY_JOBS must be from 1 to 16.")
    expected = Path(args.expected).read_text(encoding="utf-8") if args.expected else None
    scopes = args.paths
    halted = threading.Event()
    children = set()
    lock = threading.Lock()
    violations = []
    failed_build = False
    failed_unit = False
    failed_e2e = False

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
                               run_id=Path(os.environ.get("UNCLE_TIMING_DIR", "")).name,
                               workflow_state=os.environ.get("UNCLE_TIMING_STAGE", ""),
                               elapsed_seconds=round(elapsed, 6), process_exit=status,
                               ended_at=time.time(), speculative=False, log=log,
                               input_tokens=None, output_tokens=None), out)
            os.replace(out.name, out.name + ".json")
        except OSError:
            pass  # Metrics do not change acceptance.

    skip = set()
    if getattr(args, 'skip', ''):
        try:
            skip = set(Path(args.skip).read_text(encoding='utf-8').splitlines())
        except OSError:
            pass

    def check(index, directory):
        command = commands[index]
        invoked = execution_command(command)
        started = time.monotonic()
        log = directory / str(index)
        with log.open("wb") as output:
            # Commands in the same declared group have already started and
            # remain genuinely independent. This only prunes *later* work.
            reason = prerequisite_skip(command, failed_build, failed_unit, failed_e2e)
            if reason:
                output.write(reason.encode('utf-8'))
                record(command, time.monotonic() - started, 125, args.log)
                return 125, log
            if command in skip:
                # Recorded as already run in the background against this exact manifest (state/prewarm/results.tsv).
                output.write(b"PREWARMED: ran in the background during implementation and succeeded.\n")
                record(command, time.monotonic() - started, 0, args.log)
                return 0, log
            if halted.is_set() or not intact():
                output.write(b"NOT RUN: protected verification inputs changed.\n")
                return 125, log
            reuse_key = check_reuse.key(command)
            if check_reuse.restore(reuse_key, output):
                if intact():
                    record(command, time.monotonic() - started, 0, args.log)
                    return 0, log
                return 125, log
            check_env = dict(os.environ)
            try:
                with prepare(command, output, check_env, halted):
                    with lock:
                        if halted.is_set():
                            output.write(b"NOT RUN: protected verification inputs changed.\n")
                            return 125, log
                        for key in ('UNCLE_STATUS_FILE', 'UNCLE_PROJECT_ROOT', 'UNCLE_CONFIG',
                                    'STAGEGATE_RUN_ID', 'STAGEGATE_ORIGIN_REPO', 'STAGEGATE_ORIGIN_ISSUE',
                                    'DOCUMENT_BUDGET_SOURCE', 'UNCLE_STEERING', 'UNCLE_SUPERVISION_HOST'):
                            check_env.pop(key, None)
                        if invoked != command:
                            output.write(f"EXECUTION: {invoked}\n".encode('utf-8'))
                        argv = syntax_command(invoked, args.jobs) or [bash_executable(), '-o', 'pipefail', '-c', invoked]
                        output.flush()
                        child = start_check(argv, env=check_env,
                                            stdout=output, stderr=subprocess.STDOUT)
                        children.add(child)
                    try:
                        status = wait_check(child, timeout, output, cancelled=halted)
                    finally:
                        with lock:
                            kill_tree(child)
                            child.wait()
                            finish_check(child)
                            children.discard(child)
            except (OSError, ValueError) as error:
                output.write((str(error) + '\n').encode())
                status = 126
            intact()  # Check each command, even if a peer later restores bytes.
        if status != 0 and E2E.search(command_evidence(command)) and browser_application_unrunnable(log):
            with log.open('ab') as output:
                output.write(
                    b'APPLICATION_RUNTIME_UNRUNNABLE: browser checks found no mounted application root; '
                    b'return to implementation instead of treating this as a nonblocking test failure.\n')
        if status == 0 and not halted.is_set() and reuse_key == check_reuse.key(command):
            check_reuse.record(reuse_key, log)
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
                # Mutation evidence requires a passing ordinary baseline, even
                # when a generated plan incorrectly groups them together.
                if MUTATION.search(command_evidence(commands[index])):
                    end = index + 1
                else:
                    for candidate in range(index + 1, end):
                        if MUTATION.search(command_evidence(commands[candidate])):
                            end = candidate
                            break
                futures = [pool.submit(check, i, Path(temporary.name)) for i in range(index, end)]
                for i, future in zip(range(index, end), futures):
                    # Python <=3.13 on Windows cannot dispatch SIGBREAK while
                    # blocked in an unbounded condition wait. Return to Python
                    # regularly so cancellation reaches the cleanup below.
                    combined.write(f"\n$ {commands[i]}\n".encode())
                    combined.flush()
                    print(f"  RUNNING   {commands[i]}", flush=True)
                    live_log = Path(temporary.name) / str(i)
                    offset = 0
                    last_progress = time.monotonic()
                    latest_output = ''
                    def stream_available():
                        nonlocal offset, latest_output
                        if live_log.exists():
                            with live_log.open('rb') as source:
                                source.seek(offset)
                                chunk = source.read()
                                offset += len(chunk)
                            lines = chunk.decode('utf-8', errors='replace').splitlines()
                            if lines:
                                latest_output = lines[-1][-240:]
                            combined.write(chunk)
                            combined.flush()
                    while not future.done():
                        stream_available()
                        if time.monotonic() - last_progress >= 15:
                            print(f"  STILL RUNNING   {commands[i]} | {latest_output or 'waiting for output'}", flush=True)
                            last_progress = time.monotonic()
                        wait([future], timeout=0.1)
                    status, log = future.result()
                    stream_available()
                    if status == 0:
                        passed += 1
                    else:
                        failed += 1
                    if status != 0:
                        if BUILD.search(command_evidence(commands[i])):
                            failed_build = True
                        if UNIT.search(command_evidence(commands[i])):
                            failed_unit = True
                        if E2E.search(command_evidence(commands[i])):
                            failed_e2e = True
                    results.write(f"{status}\t{commands[i]}\n")
                    results.flush()
                    label = 'INVALID' if halted.is_set() else ('PASS' if status == 0 else ('SKIP' if status == 125 else ('STALLED' if status == 123 else f'FAIL({status})')))
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
