"""Start checks inside a Windows job before allowing them to spawn descendants."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import time


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in (
        'TotalUserTime', 'TotalKernelTime', 'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime'
    )] + [(name, ctypes.c_uint32) for name in (
        'TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses'
    )]


class Job:
    def __init__(self):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'TerminateJobObject': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            'QueryInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.kill_on_close()

    def kill_on_close(self):
        """JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: when the owning process exits and
        its last handle closes, every process in the job is terminated."""
        class BasicLimit(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BasicLimit), ('IoInfo', IoCounters),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        info = ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        setter = self.api.SetInformationJobObject
        setter.argtypes, setter.restype = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL
        if not setter(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):  # JobObjectExtendedLimitInformation
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self):
        if not self.handle:
            return
        if self.handle and not self.api.TerminateJobObject(self.handle, 130):
            raise ctypes.WinError(ctypes.get_last_error())
        # Termination is asynchronous. Do not return while descendants can
        # still hold log files open, even after the immediate child has exited.
        deadline = time.monotonic() + 3
        info = Accounting()
        while True:
            if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(info),
                                                     ctypes.sizeof(info), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.ActiveProcesses == 0:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError('Windows job still has active processes after termination')
            time.sleep(.01)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def start(command, prompt=None, **kwargs):
    """Start `command` inside a fresh Job. With `prompt` (bytes) the command
    reads it from stdin after the handshake byte; otherwise stdin is NUL."""
    job = Job()
    child = None
    try:
        # A pipe handshake prevents a fast shell from forking/exiting before
        # assignment. EOF on failed setup exits without executing the command.
        forward = ['--forward-stdin'] if prompt is not None else []
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), *forward, *command],
                                 stdin=subprocess.PIPE, **kwargs)
        job.assign(child)
        child._uncle_job = job
        child.stdin.write(b'G')
        if prompt is not None:
            try:
                child.stdin.write(prompt)
            except OSError:
                pass
        child.stdin.close()
        child.stdin = None
        return child
    except BaseException:
        if child is not None:
            if child.stdin is not None:
                child.stdin.close()
            child.kill()
            child.wait()
        job.terminate()
        job.close()
        raise


if __name__ == '__main__':
    import os
    # Unbuffered: the bytes after the handshake belong to the command.
    if os.read(0, 1) != b'G':
        sys.exit(125)
    if sys.argv[1:2] == ['--forward-stdin']:
        sys.exit(subprocess.call(sys.argv[2:], stdin=0))
    sys.exit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))
