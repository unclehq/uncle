"""Create and terminate isolated child trees on POSIX and native Windows."""
import os
import signal
import shutil
import subprocess
from pathlib import Path


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
            return ['bash', Path(executable).as_posix(), *command[1:]]
    return command


def group_options():
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def kill_tree(process):
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
