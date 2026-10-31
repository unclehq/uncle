"""Create and terminate isolated child trees on POSIX and native Windows."""
import os
import signal
import shutil
import subprocess
import sys
import time
import stat
from pathlib import Path

from execution_options import option, seconds


def check_timeout(name='WORKFLOW_CHECK_TIMEOUT_SECONDS', default=900):
    value = float(os.environ.get(name, default))
    if not 0 < value <= 86400:
        raise ValueError(name + ' must be greater than 0 and at most 86400')
    return value


def tree_cpu(child):
    """Cumulative CPU and membership of the owned tree; unknown is never idle."""
    try:
        job = getattr(child, '_uncle_job', None)
        if job is not None:
            import ctypes
            from windows_job import Accounting
            info = Accounting()
            if not job.api.QueryInformationJobObject(job.handle, 1, ctypes.byref(info),
                                                     ctypes.sizeof(info), None):
                return None
            return (info.TotalUserTime + info.TotalKernelTime) / 10000000, info.TotalProcesses
        rows = subprocess.run(['ps', '-axo', 'pid=,ppid=,pgid=,time='],
                              capture_output=True, text=True, timeout=2, check=True).stdout
        processes = {}
        for row in rows.splitlines():
            pid, parent, group, elapsed = row.split()
            days, _, elapsed = elapsed.rpartition('-')
            parts = [float(p) for p in elapsed.split(':')]
            cpu = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
            processes[int(pid)] = (int(parent), int(group), cpu + int(days or 0) * 86400)
        owned = {pid for pid, (_, group, _) in processes.items() if group == child.pid}
        owned.add(child.pid)
        while True:
            descendants = {pid for pid, (parent, _, _) in processes.items() if parent in owned}
            if descendants <= owned:
                break
            owned.update(descendants)
        return sum(processes[pid][2] for pid in owned if pid in processes), frozenset(owned)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def wait_check(child, timeout, output, idle=None, cancelled=None):
    """Bound a check's lifetime, including its owned descendants."""
    idle = seconds('check-idle-seconds', 90, allow_zero=True) if idle is None else idle
    cpu_percent = float(option('check-idle-cpu-percent', '1'))
    if not 0 <= cpu_percent <= 100:
        raise ValueError('execution.check-idle-cpu-percent must be from 0 to 100')
    started = active = time.monotonic()
    previous_cpu = None
    previous_size = None
    while child.poll() is None:
        now = time.monotonic()
        if cancelled is not None and cancelled.is_set():
            label, limit, status = 'CANCELLED', now - started, 130
            break
        if now - started >= timeout:
            label, limit, status = 'TIMEOUT', timeout, 124
            break
        if idle:
            output.flush()
            try:
                info = os.fstat(output.fileno())
                size = info.st_size if stat.S_ISREG(info.st_mode) else None
            except (OSError, ValueError):
                size = None
            cpu = tree_cpu(child)
            if (size is None or cpu is None or previous_cpu is None
                    or size != previous_size or cpu[1] != previous_cpu[1]
                    or abs(cpu[0] - previous_cpu[0]) >= max(.05, (now - active) * cpu_percent / 100)):
                active = now
                previous_cpu = cpu
            previous_size = size
            if now - active >= idle:
                label, limit, status = 'STALLED', idle, 123
                break
        try:
            return child.wait(timeout=min(1, max(.02, idle / 4) if idle else 1,
                                          max(.01, timeout - (now - started))))
        except subprocess.TimeoutExpired:
            pass
    else:
        return child.returncode
    kill_tree(child)
    child.wait()
    output.write(('\n%s after %gs; check process tree terminated; preceding output retained.\n' %
                  (label, limit)).encode())
    output.flush()
    return status


def cleanup_directory(directory, timeout=30):
    """Allow terminated Windows descendants to release inherited file handles.

    CI hosts and malware scanners hold new files open for seconds, so the
    window is generous. A lock that outlives it still must not mask the error
    the cleanup runs under: with another exception in flight, the failure is
    reported and the temporary directory is left for the OS to reclaim.
    Standalone calls keep raising so persistent cleanup errors stay visible.
    """
    in_flight = sys.exc_info()[1]
    deadline = time.monotonic() + timeout
    while True:
        try:
            directory.cleanup()
            return
        except OSError as error:
            # TerminateProcess is asynchronous; taskkill returning and the
            # direct child exiting do not imply every descendant closed its
            # handles. Retry only sharing/lock violations, never other errors.
            if getattr(error, 'winerror', None) not in (32, 33):
                raise
            if time.monotonic() >= deadline:
                if in_flight is not None:
                    print('cleanup_directory: leaving %s behind: %s' % (directory.name, error),
                          file=sys.stderr)
                    return
                raise
            time.sleep(0.05)


def python3_executable():
    """The interpreter to launch a NEW python subprocess with, not `sys.executable`.

    CPython resolves symlinks to compute `sys.executable`, which defeats the
    stable `opt_libexec` symlink a packaged install (e.g. Homebrew) relies on
    for a long-running process to survive an upgrade: a reinstall mid-run
    deletes the versioned keg directory `sys.executable` had already resolved
    to and frozen, so a later `subprocess.run([sys.executable, ...])` fails
    with ENOENT even though this same process keeps running fine (its own
    loaded image needs no re-stat). `shutil.which` does a literal PATH-string
    lookup with no symlink resolution, so it re-resolves through the stable
    opt-symlink chain fresh on every call.
    """
    return shutil.which('python3') or sys.executable


def bash_executable():
    # Resolve before CreateProcess: its bare-name search checks System32 (WSL)
    # before PATH, even when Git Bash is first on PATH.
    selected = os.environ.get('UNCLE_WINDOWS_BASH') if os.name == 'nt' else None
    executable = shutil.which(selected or 'bash')
    if not executable:
        raise FileNotFoundError('Cannot locate Git Bash' if os.name == 'nt' else 'Cannot locate bash')
    return str(Path(executable).absolute())


def launch_command(command):
    if os.name != 'nt':
        return command
    executable = shutil.which(command[0])
    if not executable:
        for directory in ['', *os.get_exec_path()]:
            candidate = Path(directory) / command[0]
            if candidate.is_file():
                executable = str(candidate)
                break
    if executable:
        with open(executable, 'rb') as source:
            shebang = source.readline(256)
        if shebang.startswith(b'#!') and b'sh' in shebang:
            return [bash_executable(), Path(executable).as_posix(), *command[1:]]
    return command


def track_process(process, command, started, tick):
    """Attach the timing record finish_check completes; name interpreter
    launches by their script so the report reads `python3 foo.py`, not `python3`."""
    try:
        import uuid
        from build_timing import event
        name = Path(str(command[0])).name
        if len(command) > 1 and (name.startswith('python') or name in ('bash', 'sh')):
            script = Path(str(command[1]))
            if script.suffix in ('.py', '.sh'):
                name += ' ' + script.name
        identity = uuid.uuid4().hex
        process._uncle_timing = (name, started, tick, identity)
        event('process_start', name, started, 0, child_pid=process.pid,
              span_id=identity, workflow_state=os.environ.get('UNCLE_TIMING_STAGE', ''))
    except Exception:
        pass  # Optional telemetry must not strand a successfully launched child.
    return process


def timed_popen(command, **kwargs):
    """Launch a process with optional timing; preserve caller process options."""
    started, tick = time.time(), time.monotonic()
    return track_process(subprocess.Popen(command, **kwargs), command, started, tick)


def group_options():
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


# A POSIX child that outlives its parent is otherwise unowned: this shim is
# the session leader of the check, and kills its whole group when the parent
# that started it disappears. Windows checks get the same from the Job's
# kill-on-close limit.
_PARENT_WATCH = (
    'import os, signal, subprocess, sys, threading, time\n'
    'parent = os.getppid()\n'
    'child = subprocess.Popen(sys.argv[1:])\n'
    'def watch():\n'
    '    while True:\n'
    '        time.sleep(0.2)\n'
    '        if os.getppid() != parent:\n'
    '            os.killpg(os.getpgid(0), signal.SIGKILL)\n'
    'threading.Thread(target=watch, daemon=True).start()\n'
    'sys.exit(child.wait())\n')


KEEP_STDIN = object()


def start_check(command, prompt=None, **kwargs):
    """Start `command` as its own owned tree. `prompt` (bytes) is written to
    its stdin and then closed; without one stdin is /dev/null as before.
    Pass KEEP_STDIN to leave stdin open for a worker fed more than once."""
    started, tick = time.time(), time.monotonic()
    if os.name == 'nt':
        from windows_job import start
        return track_process(start(command, prompt=prompt, **kwargs, **group_options()), command, started, tick)
    import sys
    wrapped = [python3_executable(), '-B', '-c', _PARENT_WATCH, *command]
    if prompt is KEEP_STDIN:
        # A worker that answers many turns is fed over its whole life, so stdin
        # stays open. It keeps the parent watch: the tree still dies with us.
        child = subprocess.Popen(wrapped, stdin=subprocess.PIPE, **kwargs, **group_options())
        return track_process(child, command, started, tick)
    if prompt is None:
        child = subprocess.Popen(wrapped, stdin=subprocess.DEVNULL, **kwargs, **group_options())
        return track_process(child, command, started, tick)
    child = subprocess.Popen(wrapped, stdin=subprocess.PIPE, **kwargs, **group_options())
    try:
        child.stdin.write(prompt)
    except (BrokenPipeError, OSError):
        pass
    child.stdin.close()
    child.stdin = None
    return track_process(child, command, started, tick)


def finish_check(process):
    timing = getattr(process, '_uncle_timing', None)
    # Only track_process's explicit record is timing data. Mock/proxy objects
    # can synthesize attributes even when no record was ever attached.
    if isinstance(timing, tuple) and len(timing) == 4:
        process._uncle_timing = None
        try:
            from build_timing import event
            name, started, tick, identity = timing
            event('process', name, started, time.monotonic() - tick,
                  process.returncode, child_pid=process.pid, span_id=identity,
                  workflow_state=os.environ.get('UNCLE_TIMING_STAGE', ''))
        except Exception:
            pass  # Observability must never prevent Job Object cleanup.
    job = getattr(process, '_uncle_job', None)
    if job is not None:
        try:
            job.terminate()
        finally:
            job.close()


def kill_tree(process):
    if getattr(process, '_uncle_tree_killed', False) is True:
        return
    job = getattr(process, '_uncle_job', None)
    if job is not None:
        job.terminate()
        return
    if os.name == 'nt':
        # Native PID, not an MSYS PID. /T includes grandchildren holding pipes.
        try:
            subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                raise
        process._uncle_tree_killed = True
