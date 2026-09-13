import sys
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import shell_syntax as syntax

LOOP = 'for f in scripts/*.sh scripts/lib/*.sh scripts/tests/*.sh; do bash -n "$f"; done'

class Tests(unittest.TestCase):
    def test_windows_transport_reconstructs_command_in_bash(self):
        command = "printf '%s' 'A\rB'; printf '%s' \"\\\\tail\"; exit 7"
        bash = syntax.bash_executable()
        with patch.object(syntax.os, 'name', 'nt'), \
             patch.object(syntax, 'bash_executable', return_value=bash):
            argv = syntax.shell_command(command)
        self.assertNotIn('\r', argv[-1])
        result = subprocess.run(argv, capture_output=True)
        self.assertEqual(result.stdout, b'A\rB\\tail')
        self.assertEqual(result.returncode, 7)

    def test_command_file_preserves_control_characters_and_line_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = root / 'commands'
            commands.write_bytes(b"\r\nprintf 'A\rB' > embedded\r\nprintf last > last")
            for line in (2, 3):
                result = subprocess.run([sys.executable, syntax.__file__, '--command-file',
                                         str(commands), str(line), '2'], cwd=root, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'embedded').read_bytes(), b'A\rB')
            self.assertEqual((root / 'last').read_bytes(), b'last')

    def test_windows_dispatch_preserves_arguments_and_failure(self):
        command = "printf 'A\rB' > 'file with spaces'; exit 7"
        bash = r'C:\Program Files\Git\usr\bin\bash.exe'
        with patch.object(syntax.sys, 'argv', ['helper', '--command', command, '2']), \
             patch.object(syntax.os, 'name', 'nt'), \
             patch.object(syntax, 'syntax_command', return_value=None), \
             patch.object(syntax, 'bash_executable', return_value=bash), \
             patch.object(syntax.os, 'execv') as execv, \
             patch.object(syntax.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(syntax.main(), 7)
            run.assert_called_once_with(syntax.shell_command(command))
            self.assertNotIn('\r', run.call_args.args[0][-1])
            execv.assert_not_called()

    def test_only_known_read_only_loop_is_parallelized(self):
        self.assertIsNotNone(syntax.syntax_command(LOOP, 4))
        self.assertIsNotNone(syntax.syntax_command(LOOP.replace('; done', ' || exit 1; done'), 4))
        for command in (LOOP + '; echo done', LOOP.replace('bash -n', 'bash'), LOOP.replace('"$f"', '"$f"; touch changed')):
            self.assertIsNone(syntax.syntax_command(command, 4))

    def test_suite_loop_aggregates_failures_and_runs_remaining_suites(self):
        command = 'for t in scripts/tests/*-test.sh; do bash "$t"; done'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'scripts/tests'
            tests.mkdir(parents=True)
            (tests / 'a-test.sh').write_text('echo first >> order; exit 7\n')
            (tests / 'b-test.sh').write_text('echo second >> order; exit 0\n')
            # Exercise the dispatcher used by the sequential verification path.
            result = subprocess.run([sys.executable, syntax.__file__, '--command', command, '4'],
                                    cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(sorted((root / 'order').read_text().splitlines()), ['first', 'second'])
            self.assertIn('FAIL(7) scripts/tests/a-test.sh', result.stdout)
            self.assertIn('PASS scripts/tests/b-test.sh', result.stdout)
            (tests / 'a-test.sh').write_text('exit 0\n')
            result = subprocess.run(syntax.syntax_command(command, 4), cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            (tests / 'a-test.sh').unlink()
            (tests / 'b-test.sh').unlink()
            result = subprocess.run(syntax.syntax_command(command, 4), cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(syntax.syntax_command(command + '; echo extra', 4))

    def test_shell_suites_run_concurrently(self):
        command = 'for t in scripts/tests/*-test.sh; do bash "$t"; done'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'scripts/tests'
            tests.mkdir(parents=True)
            for name, peer in [('a','b'), ('b','a')]:
                (tests / (name + '-test.sh')).write_text(
                    f'touch {name}; for i in {{1..100}}; do '
                    f'if test -e {peer}; then exit 0; fi; sleep .02; done; exit 9\n')
            result = subprocess.run(syntax.syntax_command(command, 2), cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('up to 2 workers', result.stdout)

    def test_fast_suite_output_is_not_blocked_by_slow_earlier_suite(self):
        command = 'for t in scripts/tests/*-test.sh; do bash "$t"; done'
        with tempfile.TemporaryDirectory() as directory:
            tests = Path(directory) / 'scripts/tests'
            tests.mkdir(parents=True)
            (tests / 'a-slow-test.sh').write_text('sleep 1; echo slow\n')
            (tests / 'b-fast-test.sh').write_text('echo fast\n')
            result = subprocess.run(syntax.syntax_command(command, 2), cwd=directory, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(result.stdout.index('PASS scripts/tests/b-fast'),
                            result.stdout.index('PASS scripts/tests/a-slow'))

    def test_skipped_suites_are_neither_passes_nor_failures(self):
        command = 'for t in scripts/tests/*-test.sh; do bash "$t"; done'
        with tempfile.TemporaryDirectory() as directory:
            tests = Path(directory) / 'scripts/tests'
            tests.mkdir(parents=True)
            (tests / 'skip-test.sh').write_text('echo "optional tool missing"; exit 77\n')
            (tests / 'pass-test.sh').write_text('exit 0\n')
            result = subprocess.run(syntax.syntax_command(command, 2), cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SKIP scripts/tests/skip-test.sh', result.stdout)
            self.assertNotIn('PASS scripts/tests/skip-test.sh', result.stdout)
            self.assertIn('1 passed, 0 failed, 1 skipped', result.stdout)
            (tests / 'fail-test.sh').write_text('exit 1\n')
            result = subprocess.run(syntax.syntax_command(command, 2), cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('1 passed, 1 failed, 1 skipped', result.stdout)

    def test_checks_overlap_and_results_keep_file_order(self):
        barrier = threading.Barrier(3)
        def run(argv, **kwargs):
            barrier.wait(timeout=3)
            return subprocess.CompletedProcess(argv, int(argv[-1] == 'bad'), b'')
        with patch.object(syntax.subprocess, 'run', side_effect=run):
            results = syntax.check_files(['first', 'bad', 'last'], 3, 'bash')
        self.assertEqual([r[:2] for r in results], [('first', 0), ('bad', 1), ('last', 0)])

    def test_earlier_error_cannot_be_hidden_by_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('scripts', 'scripts/lib', 'scripts/tests'):
                (root / folder).mkdir(exist_ok=True)
                (root / folder / 'good.sh').write_text('true\n')
            (root / 'scripts/bad.sh').write_text('if then\n')
            result = subprocess.run(syntax.syntax_command(LOOP, 4), cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('FAIL bash -n scripts/bad.sh', result.stdout)
            self.assertIn('PASS bash -n scripts/tests/good.sh', result.stdout)

if __name__ == '__main__': unittest.main()
