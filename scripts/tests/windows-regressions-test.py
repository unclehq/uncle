"""Nested regression failures must be visible outside collapsed CI groups."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

path = Path(__file__).with_name('windows-regressions.py')
spec = importlib.util.spec_from_file_location('windows_regressions', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Reporting(unittest.TestCase):
    def test_nested_failure_names_are_deduplicated(self):
        text = 'PASS scripts/tests/good-test.sh\nFAIL(1) scripts/tests/bad-test.sh\r\nFAIL(2) scripts/tests/bad-test.sh\n'
        self.assertEqual(module.failed_shell_suites(text), ['scripts/tests/bad-test.sh'])
        self.assertEqual(module.failed_shell_suites('Traceback: launcher failed'), [])

    def test_failure_is_named_and_logs_are_retained(self):
        def run(suites, directory):
            result = []
            for name, _ in suites:
                log = Path(directory) / (name + '.log')
                failed = name == 'shell-regressions'
                log.write_text('FAIL(1) scripts/tests/bad-test.sh\n' if failed else 'OK\n')
                result.append((name, int(failed), log))
            return result
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            buffer = io.BytesIO()
            output = types.SimpleNamespace(buffer=buffer, write=lambda text: buffer.write(text.encode()), flush=lambda: None)
            try:
                with patch.object(module, 'ROOT', Path(directory)), patch.object(module, 'run_suites', side_effect=run), \
                        patch.object(module, 'bash_executable', return_value='bash'), \
                        patch.dict(os.environ, GITHUB_STEP_SUMMARY=str(Path(directory)/'summary')), contextlib.redirect_stdout(output):
                    self.assertTrue(module.main())
            finally:
                os.chdir(previous)
            text = buffer.getvalue().decode()
            self.assertIn('Failed suites: scripts/tests/bad-test.sh', text)
            self.assertIn('::error::Regression suite failed: scripts/tests/bad-test.sh', text)
            self.assertIn('bad-test.sh', (Path(directory)/'summary').read_text())
            self.assertTrue((Path(directory)/'.uncle/workflow/regression-logs/shell-regressions.log').exists())


if __name__ == '__main__': unittest.main()
