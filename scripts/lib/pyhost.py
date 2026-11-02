#!/usr/bin/env python3
"""A per-run Python host: serves `python3 helper.py args...` calls from a warm interpreter, one forked child per call.

A driver launches thousands of short helpers and each launch costs an interpreter start (17-25 ms of CPU). The host starts once with
its driver, listens on a private loopback socket, and runs each call in a child forked from the warm process. The call sees what it
would have seen under a plain `python3`: the same argv, working directory, environment, stdout, stderr and exit status. This module is
the first stage of the driver cutover (docs/driver-cutover-plan.md); the bash client is scripts/lib/pyhost.sh.

    pyhost.py serve DIR OWNER_PID ROOT

Safety rules, each tested in scripts/tests/pyhost-test.sh:
  * only a helper under ROOT/scripts/lib that a static scan shows is short-lived and never reads stdin or manages processes is served;
    everything else is REFUSEd and the client runs the real interpreter;
  * the request is acknowledged (ACK) before anything runs, so a client may fall back freely until then and never after;
  * the socket is bound to 127.0.0.1 and every request carries the run's token;
  * the host exits when its owner does, removes its directory, and bounds every child with an alarm.

Wire format. Request: a sequence of fields, each `<byte length>\n<bytes>`: token, working directory, argument count, each argument,
the environment as `export -p` text. Reply: `ACK\n` or `REFUSE\n`, then after the call `<exit status> <child pid>\n`; the child's
stdout and stderr are in DIR/o.<pid> and DIR/e.<pid>, which the host deletes after a short while.
"""
import os
import re
import runpy
import secrets
import shutil
import signal
import socket
import sys
import threading
import time

# Imported once so every child inherits them already loaded.
import argparse, collections, datetime, hashlib, itertools, json, pathlib, subprocess, tempfile, textwrap, traceback, uuid  # noqa: F401,E401

REQUEST_SECONDS = 30
CALL_SECONDS = 900
KEEP_OUTPUT_SECONDS = 120
# Helpers the static scan refuses as a whole but whose short subcommands are safe to serve: build_timing.py's long-lived sampler is
# `run`; its `stage` and `report` are one-shot.
SUBCOMMANDS = {'build_timing.py': {'stage', 'report'}}
UNSAFE = re.compile(r'stdin|setsid|killpg|os\.fork|Popen|signal\.|daemon|os\.exec|input\(')
DECLARE = re.compile(r'declare -x ([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$', re.S)


def parse_env(text):
    """`export -p` output: declare -x NAME="value" (a value may span lines; backslash escapes \\ " $ and backtick)."""
    env, i, n = {}, 0, len(text)
    while i < n:
        end = text.find('\n', i)
        line = text[i:end if end >= 0 else n]
        match = DECLARE.match(line)
        if not match:
            i = end + 1 if end >= 0 else n
            continue
        name, rest = match.group(1), match.group(2)
        if rest is None:
            env[name] = ''
            i = end + 1 if end >= 0 else n
            continue
        k, out = text.find('="', i) + 2, []
        while k < n:
            c = text[k]
            if c == '\\' and k + 1 < n:
                out.append(text[k + 1])
                k += 2
                continue
            if c == '"':
                break
            out.append(c)
            k += 1
        env[name] = ''.join(out)
        nl = text.find('\n', k)
        i = nl + 1 if nl >= 0 else n
    return env


def safe_helpers(lib):
    """Names of the helpers in `lib` a call may be served for: short-lived, no stdin, no process control."""
    names = set()
    for entry in os.scandir(lib):
        if entry.name.endswith('.py') and entry.is_file():
            try:
                if not UNSAFE.search(open(entry.path, encoding='utf-8', errors='replace').read()):
                    names.add(entry.name)
            except OSError:
                pass
    return names


def read_field(stream):
    header = stream.readline()
    if not header:
        raise EOFError
    data = stream.read(int(header))
    if len(data) != int(header):
        raise EOFError
    return data


def run_call(directory, conn, token, lib, allowed):
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    for name in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(name, signal.SIG_DFL)               # a call is an ordinary process: signalling it must not remove the host's directory
    signal.alarm(REQUEST_SECONDS)
    stream = conn.makefile('rb')
    try:
        given = read_field(stream).decode('utf-8', 'surrogateescape')
        cwd = read_field(stream).decode('utf-8', 'surrogateescape')
        count = int(read_field(stream))
        args = [read_field(stream).decode('utf-8', 'surrogateescape') for _ in range(count)]
        env = parse_env(read_field(stream).decode('utf-8', 'surrogateescape'))
    except (EOFError, ValueError):
        os._exit(1)
    if not secrets.compare_digest(given, token):
        os._exit(1)
    dont_write = False
    if args and args[0] == '-B':
        dont_write, args = True, args[1:]
    script = os.path.realpath(os.path.join(cwd, args[0])) if args else ''
    name = os.path.basename(script)
    served = name in allowed or (name in SUBCOMMANDS and len(args) > 1 and args[1] in SUBCOMMANDS[name])
    if not (script.startswith(lib + os.sep) and served and os.path.isfile(script)):
        conn.sendall(b'REFUSE\n')
        os._exit(0)
    conn.sendall(b'ACK\n')
    signal.alarm(CALL_SECONDS)
    code = 0
    out_path, err_path = f'{directory}/o.{os.getpid()}', f'{directory}/e.{os.getpid()}'
    try:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(env)
        os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
        os.dup2(os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 1)
        os.dup2(os.open(err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 2)
        sys.stdin = open(0, closefd=False)
        sys.stdout = open(1, 'w', closefd=False, buffering=1)
        sys.stderr = open(2, 'w', closefd=False, buffering=1)
        sys.dont_write_bytecode = dont_write or bool(env.get('PYTHONDONTWRITEBYTECODE'))
        sys.argv = args
        sys.path.insert(0, os.path.dirname(os.path.abspath(args[0])))
        runpy.run_path(args[0], run_name='__main__')      # the path as the caller gave it, so tracebacks and __file__ read the same
    except SystemExit as stop:
        value = stop.code
        if value is None:
            code = 0
        elif isinstance(value, int):
            code = int(value)       # sys.exit(True) is 1 and sys.exit(False) is 0, as in the real interpreter
        else:
            print(value, file=sys.stderr)
            code = 1
    except BaseException:
        kind, value, trace = sys.exc_info()
        while trace is not None and ('runpy' in trace.tb_frame.f_code.co_filename or trace.tb_frame.f_code.co_filename == __file__):
            trace = trace.tb_next                           # the host's own frames are not the helper's
        traceback.print_exception(kind, value, trace)
        code = 1
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        try:
            conn.sendall(f'{code & 0xFF} {os.getpid()}\n'.encode())
            conn.close()
        finally:
            os._exit(0)


def serve(directory, owner, root):
    root = os.path.realpath(root)
    lib = os.path.join(root, 'scripts', 'lib')
    allowed = safe_helpers(lib)
    token = secrets.token_hex(16)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)       # children are reaped without waiting

    def leave(*_):
        shutil.rmtree(directory, ignore_errors=True)
        os._exit(0)
    # A driver stops its background jobs when it exits; the host must tidy up on that signal too, not only when it notices the owner gone.
    for name in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(name, leave)

    def watch():
        while True:
            time.sleep(1)
            try:
                os.kill(owner, 0)
            except OSError:
                shutil.rmtree(directory, ignore_errors=True)
                os._exit(0)
            horizon = time.time() - KEEP_OUTPUT_SECONDS
            try:
                for entry in os.scandir(directory):
                    if entry.name[:2] in ('o.', 'e.') and entry.stat().st_mtime < horizon:
                        os.unlink(entry.path)
            except OSError:
                pass

    threading.Thread(target=watch, daemon=True).start()
    for name, value in (('token', token), ('port', str(listener.getsockname()[1]))):
        with open(f'{directory}/{name}', 'w') as handle:
            handle.write(value + '\n')
    open(f'{directory}/ready.tmp', 'w').close()
    os.replace(f'{directory}/ready.tmp', f'{directory}/ready')       # the client reads port and token only after this appears
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            continue
        try:
            pid = os.fork()
        except OSError:
            conn.close()
            continue
        if pid == 0:
            try:
                listener.close()
                run_call(directory, conn, token, lib, allowed)
            finally:
                os._exit(1)
        conn.close()


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == 'serve':
        serve(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    print(__doc__, file=sys.stderr)
    sys.exit(2)
