#!/usr/bin/env python3
"""Platform contracts runnable both on Windows and on a developer's POSIX host."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import process_tree

class Portability(unittest.TestCase):
    def test_manifest_is_utf8_lf_and_forward_slashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'app').mkdir()
            (root/'app/test.sh').write_bytes(b'echo test\n')
            (root/'scopes').write_bytes(b'app\n')
            result = subprocess.run([sys.executable, str(ROOT/'scripts/lib/verification_manifest.py'), 'scopes'],
                                    cwd=root, capture_output=True, check=True)
            self.assertNotIn(b'\r', result.stdout)
            self.assertIn(b'\tapp/test.sh\n', result.stdout)
            self.assertNotIn(b'app\\test.sh', result.stdout)

    def test_windows_group_and_tree_kill(self):
        child = Mock(pid=123)
        child.poll.return_value = None
        with patch.object(process_tree, 'os', types.SimpleNamespace(name='nt')), \
             patch.object(process_tree.subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, create=True), \
             patch.object(process_tree.subprocess, 'run') as run:
            self.assertEqual(process_tree.group_options(), {'creationflags': 512})
            process_tree.kill_tree(child)
            self.assertEqual(run.call_args[0][0], ['taskkill.exe','/PID','123','/T','/F'])
            child.kill.assert_called_once()

    def test_windows_shell_fixture_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'runner with spaces'
            script.write_bytes(b'#!/usr/bin/env bash\necho test\n')
            fake_os = types.SimpleNamespace(name='nt', get_exec_path=lambda: [directory])
            with patch.object(process_tree, 'os', fake_os), patch.object(process_tree.shutil, 'which', return_value=str(script)), \
                 patch.object(process_tree, 'bash_executable', return_value='C:/Git/bin/bash.exe'):
                self.assertEqual(process_tree.launch_command(['runner with spaces', 'arg']),
                                 ['C:/Git/bin/bash.exe', script.as_posix(), 'arg'])

    def test_windows_bash_selection(self):
        with tempfile.TemporaryDirectory(prefix='git with spaces ') as directory:
            bash = Path(directory) / 'bash.exe'
            bash.touch()
            fake_os = types.SimpleNamespace(name='nt', environ={})
            with patch.object(process_tree, 'os', fake_os), \
                 patch.object(process_tree.shutil, 'which', return_value=str(bash)) as which:
                self.assertEqual(process_tree.bash_executable(), str(bash.absolute()))
                which.assert_called_with('bash')
                fake_os.environ['UNCLE_WINDOWS_BASH'] = str(bash)
                self.assertEqual(process_tree.bash_executable(), str(bash.absolute()))
                which.assert_called_with(str(bash))
                which.return_value = None
                with self.assertRaises(FileNotFoundError):
                    process_tree.bash_executable()

    def test_selected_bash_runs_in_working_directory(self):
        with tempfile.TemporaryDirectory(prefix='bash working directory ') as directory:
            result = subprocess.run([process_tree.bash_executable(), '-c', 'printf worked > marker; exit 7'],
                                    cwd=directory, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual((Path(directory)/'marker').read_bytes(), b'worked')

    def test_windows_lock_import_and_use(self):
        fake = types.SimpleNamespace(locking=Mock(), LK_LOCK=1)
        spec = importlib.util.spec_from_file_location('windows_totals', ROOT/'scripts/lib/session-totals.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'fcntl': None, 'msvcrt': fake}):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.update(directory)
            fake.locking.assert_called_once()
            self.assertEqual(fake.locking.call_args[0][1:], (1, 1))
            self.assertEqual((Path(directory)/'.session-totals.lock').read_bytes(), b'\0')
            self.assertNotIn(b'\r', (Path(directory)/'session-totals.json').read_bytes())

    def test_idle_timeout_stops_silent_native_child(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/lib/idle_run.py'), '--seconds','1','--',
                                 sys.executable,'-c','import time; time.sleep(30)'], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertIn(b'no output', result.stderr)

    def test_idle_output_and_exit_preserved(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/lib/idle_run.py'), '--seconds','2','--',
                                 sys.executable,'-c','import sys; print("hello", flush=True); sys.exit(7)'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout.replace(b'\r\n',b'\n'), b'hello\n')

    def test_python_file_writes_pin_newlines(self):
        # These are shell protocols, not host-native text documents.
        import ast
        for name in ('checklist_groups.py','compact-review.py','parallel_checks.py','waiver-popup.py'):
            tree = ast.parse((ROOT/'scripts/lib'/name).read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call): continue
                writes = any(isinstance(arg, ast.Constant) and arg.value == 'w' for arg in node.args)
                if writes:
                    self.assertIn('newline', [kw.arg for kw in node.keywords], name)

if __name__ == '__main__':
    unittest.main()
