import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/lib'))
import parallel_diff
from process_tree import bash_executable
spec = importlib.util.spec_from_file_location('suites', ROOT/'scripts/tests/windows-regressions.py')
suites = importlib.util.module_from_spec(spec); spec.loader.exec_module(suites)

class Tests(unittest.TestCase):
    def test_suite_failures_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = [(name, [sys.executable, '-c', f'print({name!r}); raise SystemExit({status})'])
                        for name, status in [('first', 0), ('bad', 7), ('last', 0)]]
            results = suites.run_suites(commands, directory, 3)
            self.assertEqual([(n, s) for n,s,_ in results], [('first',0), ('bad',7), ('last',0)])
            self.assertIn('bad', results[1][2].read_text())

    def test_suites_actually_overlap(self):
        barrier = threading.Barrier(3)
        class Child:
            def wait(self):
                barrier.wait(timeout=3)
                return 0
            def poll(self):
                return 0
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(suites, 'start_check', side_effect=lambda *a, **k: Child()), \
             patch.object(suites, 'finish_check'):
            results = suites.run_suites([(str(i), ['fake']) for i in range(3)], directory, 3)
            self.assertEqual([s for _,s,_ in results], [0,0,0])

    def test_diff_matches_serial_and_preserves_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root)
            git('init', '-q'); git('config','commit.gpgsign','false')
            (root/'tracked').write_text('old\n')
            git('add','tracked')
            git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','--no-gpg-sign','-qm','fixture')
            (root/'tracked').write_text('new\n'); (root/'new file').write_text('added\n')
            index = (root/'.git/index').read_bytes()
            expected = git('diff','HEAD','--','tracked')
            expected += subprocess.run(['git','diff','--no-index','--',os.devnull,'new file'],cwd=root,capture_output=True).stdout
            result = subprocess.run([sys.executable, str(ROOT/'scripts/lib/parallel_diff.py')],cwd=root,input=b'tracked\nnew file\n',capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,expected)
            self.assertEqual((root/'.git/index').read_bytes(),index)

    def test_sequential_green_run_uses_parallel_syntax_checker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('scripts','scripts/lib','scripts/tests'):
                (root/name).mkdir(exist_ok=True)
                (root/name/'good.sh').write_text('true\n')
            (root/'scripts/bad.sh').write_text('if then\n')
            (root/'commands').write_text('for f in scripts/*.sh scripts/lib/*.sh scripts/tests/*.sh; do bash -n "$f"; done\n')
            result = subprocess.run([bash_executable(),'-c','. "$1"; green_run commands results log', 'test',str(ROOT/'scripts/lib/green-check.sh')],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue((root/'results').read_text().startswith('1\t'))
            self.assertIn('FAIL bash -n scripts/bad.sh',(root/'log').read_text())

if __name__ == '__main__': unittest.main()
