"""Create and terminate isolated child trees on POSIX and native Windows."""
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path


def cleanup_directory(directory, timeout=3):
    """Allow terminated Windows descendants to release inherited file handles."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            directory.cleanup()
            return
        except OSError as error:
            # TerminateProcess is asynchronous; taskkill returning and the
            # direct child exiting do not imply every descendant closed its
            # handles. Retry only sharing/lock violations, never other errors.
            if getattr(error, 'winerror', None) not in (32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


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


def group_options():
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def track_process(process, command, started, tick):
    from build_timing import event
    import uuid
    name = Path(str(command[0])).name
    if len(command) > 1 and (name.startswith('python') or name in ('bash', 'sh')):
        script = Path(str(command[1]))
        if script.suffix in ('.py', '.sh'):
            name += ' ' + script.name
    identity = uuid.uuid4().hex
    process._uncle_timing = (name, started, tick, identity)
    event('process_start', name, started, 0, child_pid=process.pid,
          span_id=identity, workflow_state=os.environ.get('UNCLE_TIMING_STAGE', ''))
    return process


def timed_popen(command, **kwargs):
    started, tick = time.time(), time.monotonic()
    return track_process(subprocess.Popen(command, **kwargs), command, started, tick)


def start_check(command, **kwargs):
    started, tick = time.time(), time.monotonic()
    if os.name == 'nt':
        from windows_job import start
        return track_process(start(command, **kwargs, **group_options()), command, started, tick)
    return timed_popen(command, stdin=subprocess.DEVNULL, **kwargs, **group_options())


def finish_check(process):
    timing = getattr(process, '_uncle_timing', None)
    if timing is not None:
        process._uncle_timing = None
        from build_timing import event
        name, started, tick, identity = timing
        event('process', name, started, time.monotonic() - tick,
              process.returncode, child_pid=process.pid, span_id=identity,
              workflow_state=os.environ.get('UNCLE_TIMING_STAGE', ''))
    job = getattr(process, '_uncle_job', None)
    if job is not None:
        try:
            job.terminate()
        finally:
            job.close()


def kill_tree(process):
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
