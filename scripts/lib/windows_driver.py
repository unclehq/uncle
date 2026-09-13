"""Native Windows workflow lock and Job Object supervision."""
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid


def api():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        'OpenJobObjectW': ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        'IsProcessInJob': ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'QueryInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        'TerminateJobObject': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(kernel, name); fn.argtypes = args; fn.restype = result
    return kernel


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t),
                ('active', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', ctypes.c_uint64 * 6),
                ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, wintypes.DWORD) for name in ('faults', 'total', 'active', 'terminated')]


def wait_job(kernel, job):
    deadline = time.monotonic() + 3
    info = Accounting()
    while True:
        if not kernel.QueryInformationJobObject(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if not info.active:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError('Previous workflow descendants have not stopped')
        time.sleep(.02)


class ProcessEntry(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                ('exe', wintypes.WCHAR * 260)]


def parent_pid(pid):
    kernel = api()
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        fn = getattr(kernel, name)
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        fn.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry(); entry.size = ctypes.sizeof(entry)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            if entry.pid == pid: return entry.parent
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return None
    finally:
        kernel.CloseHandle(snapshot)


def child_valid(owner):
    """Git Bash PIDs differ from native PIDs; verify native Job membership."""
    name = owner.get('job')
    if (not name or os.environ.get('UNCLE_DRIVER_JOB') != name
            or parent_pid(os.getppid()) != owner.get('pid')):
        return False
    kernel = api()
    job = kernel.OpenJobObjectW(4, False, name)  # JOB_OBJECT_QUERY
    process = kernel.OpenProcess(0x1000, False, os.getppid())
    try:
        found = wintypes.BOOL()
        return bool(job and process and kernel.IsProcessInJob(process, job, ctypes.byref(found)) and found.value)
    finally:
        if process: kernel.CloseHandle(process)
        if job: kernel.CloseHandle(job)


def lock_run(command, state):
    from process_tree import launch_command
    state.mkdir(parents=True, exist_ok=True)
    # A separate byte-lock file allows children to read the ownership journal.
    with (state/'driver.guard').open('a+b') as guard:
        guard.seek(0, 2)
        if not guard.tell(): guard.write(b'1'); guard.flush()
        guard.seek(0)
        try:
            msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError('another workflow holds this checkout') from error
        kernel = api()
        owner_path = state/'driver.lock'
        if owner_path.exists():
            prior = json.loads(owner_path.read_text())
            if prior.get('job'):
                prior_job = kernel.OpenJobObjectW(4, False, prior['job'])
                if prior_job:
                    try: wait_job(kernel, prior_job)
                    finally: kernel.CloseHandle(prior_job)
        name = 'Local\\UncleWorkflow-' + uuid.uuid4().hex
        job = kernel.CreateJobObjectW(None, name)
        if not job: raise ctypes.WinError(ctypes.get_last_error())
        child = None
        handlers = {}
        try:
            limits = ExtendedLimits(); limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            with tempfile.TemporaryDirectory(prefix='uncle-driver-') as directory:
                ready = str(Path(directory)/'ready')
                # Keep stdin inherited for interactive gates. The bootstrap cannot
                # launch Bash until Job assignment and ownership are complete.
                bootstrap = ('import os,sys,time,subprocess; p=sys.argv[1]; '
                             'deadline=time.monotonic()+30\n'
                             'while not os.path.exists(p):\n'
                             ' if time.monotonic()>deadline: sys.exit(125)\n'
                             ' time.sleep(.01)\n'
                             'sys.exit(subprocess.call(sys.argv[2:]))')
                child = subprocess.Popen([sys.executable, '-c', bootstrap, ready, *launch_command(command)],
                    env=dict(os.environ, UNCLE_DRIVER_SUPERVISED='1', UNCLE_DRIVER_JOB=name),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                if not kernel.AssignProcessToJobObject(job, int(child._handle)):
                    raise ctypes.WinError(ctypes.get_last_error())
                owner = state/'driver.lock'; temporary = owner.with_suffix('.tmp')
                temporary.write_text(json.dumps({'job': name, 'pid': child.pid, 'supervisor': os.getpid()}))
                os.replace(temporary, owner)
                def stop(*_):
                    kernel.TerminateJobObject(job, 130)
                signals = [signal.SIGINT, signal.SIGTERM]
                if hasattr(signal, 'SIGBREAK'): signals.append(signal.SIGBREAK)
                for sig in signals:
                    handlers[sig] = signal.signal(sig, stop)
                Path(ready).touch()
                return child.wait()
        finally:
            kernel.TerminateJobObject(job, 130)
            if child is not None:
                if child.poll() is None: child.kill()
                child.wait()
            try:
                wait_job(kernel, job)
            finally:
                kernel.CloseHandle(job)
                for sig, handler in handlers.items(): signal.signal(sig, handler)
                guard.seek(0); msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
