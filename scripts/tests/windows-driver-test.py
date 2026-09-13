import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/lib'))
spec = importlib.util.spec_from_file_location('driver_windows', ROOT/'scripts/lib/windows_driver.py')
driver = importlib.util.module_from_spec(spec)
if os.name == 'nt':
    spec.loader.exec_module(driver)
else:
    with patch.dict(sys.modules, {'msvcrt': Mock(LK_NBLCK=2, LK_UNLCK=0)}):
        spec.loader.exec_module(driver)


def membership_child_code():
    probe = ('import json; from pathlib import Path; from windows_driver import child_valid; '
             'assert child_valid(json.loads(Path(".uncle/workflow/driver.lock").read_text()))')
    return ('import subprocess,sys,time; from pathlib import Path; '
            f'subprocess.run([sys.executable, "-c", {probe!r}], check=True); '
            'Path("started").touch(); time.sleep(20)')


class DriverTests(unittest.TestCase):
    def test_membership_child_program_is_executable(self):
        # Exercise both generated Python programs even on non-Windows hosts.
        calls = []
        def run_probe(command, **kwargs):
            self.assertTrue(kwargs['check'])
            compile(command[2], '<membership probe>', 'exec')
            calls.append(command)
        with patch('subprocess.run', side_effect=run_probe), \
             patch('pathlib.Path.touch') as started, patch('time.sleep'):
            exec(compile(membership_child_code(), '<membership child>', 'exec'), {})
        self.assertEqual(len(calls), 1)
        started.assert_called_once()

    def test_no_posix_import_required_for_plan_helper(self):
        source = (ROOT/'scripts/lib/plan-executability.py').read_text()
        original = __import__
        def importing(name, *args, **kwargs):
            if name == 'fcntl': raise ImportError('not available on Windows')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=importing):
            exec(compile(source, 'plan-executability.py', 'exec'), {'__name__': 'import_check'})

    def test_windows_supervisor_preserves_stdin_and_cleans_job(self):
        kernel = Mock()
        child = Mock(pid=123, _handle=456)
        child.wait.return_value = 0
        child.poll.return_value = 0
        with tempfile.TemporaryDirectory() as d, patch.object(driver, 'api', return_value=kernel), \
             patch.object(driver.subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, create=True), \
             patch.object(driver.subprocess, 'Popen', return_value=child) as start, \
             patch.object(driver.signal, 'signal'), patch.object(driver, 'wait_job') as wait, \
             patch.object(driver.msvcrt, 'locking') as lock:
            self.assertEqual(driver.lock_run([sys.executable, '-c', 'pass'], Path(d)), 0)
            options = start.call_args.kwargs
            self.assertNotIn('stdin', options)
            self.assertNotIn('pass_fds', options)
            self.assertNotIn('process_group', options)
            self.assertEqual(options['creationflags'], 512)
            owner = json.loads((Path(d)/'driver.lock').read_text())
            self.assertEqual(owner['job'], options['env']['UNCLE_DRIVER_JOB'])
            kernel.AssignProcessToJobObject.assert_called_once()
            kernel.TerminateJobObject.assert_called_once()
            wait.assert_called_once()
            self.assertEqual(lock.call_count, 2)

    def test_windows_lock_contention_does_not_launch(self):
        with tempfile.TemporaryDirectory() as d, patch.object(driver.msvcrt, 'locking', side_effect=OSError), \
             patch.object(driver.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(ValueError, 'another workflow'):
                driver.lock_run(['bash', 'build.sh'], Path(d))
            start.assert_not_called()

    def test_inherited_marker_cannot_bypass_driver_ownership(self):
        with patch.dict(os.environ, {'UNCLE_DRIVER_JOB': 'job'}), \
             patch.object(driver, 'parent_pid', return_value=999), \
             patch.object(driver, 'api') as kernel:
            self.assertFalse(driver.child_valid({'job': 'job', 'pid': 123}))
            kernel.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'requires native Windows Job Objects')
    def test_native_windows_lock_and_child_membership(self):
        with tempfile.TemporaryDirectory() as d:
            code = membership_child_code()
            command = [sys.executable, str(ROOT/'scripts/lib/plan-executability.py'), 'lock-run', sys.executable, '-c', code]
            env = dict(os.environ, PYTHONPATH=str(ROOT/'scripts/lib'))
            owner = subprocess.Popen(command, cwd=d, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not (Path(d)/'started').exists() and owner.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                if not (Path(d)/'started').exists():
                    owner.kill()
                    _, stderr = owner.communicate(timeout=10)
                    self.fail(f'Windows child did not start (exit {owner.returncode}):\n'
                              + stderr.decode(errors='replace'))
                contender = subprocess.run(command, cwd=d, env=env, capture_output=True, timeout=10)
                self.assertNotEqual(contender.returncode, 0)
                self.assertIn(b'another workflow', contender.stderr)
            finally:
                owner.kill(); owner.wait(); owner.stderr.close()

if __name__ == '__main__': unittest.main()
