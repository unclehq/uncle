"""Start checks inside a Windows job before allowing them to spawn descendants."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys


class Job:
    def __init__(self):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'TerminateJobObject': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self):
        if self.handle and not self.api.TerminateJobObject(self.handle, 130):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def start(command, **kwargs):
    job = Job()
    child = None
    try:
        # A pipe handshake prevents a fast shell from forking/exiting before
        # assignment. EOF on failed setup exits without executing the command.
        child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), *command],
                                 stdin=subprocess.PIPE, **kwargs)
        job.assign(child)
        child._uncle_job = job
        child.stdin.write(b'G')
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
    if sys.stdin.buffer.read(1) != b'G':
        sys.exit(125)
    sys.exit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))
