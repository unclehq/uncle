import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import preflight


class Preflight(unittest.TestCase):
    def test_dependencies_are_deduplicated_without_executing_commands(self):
        self.assertEqual(preflight.prerequisites('npm install\nnode --test tests/a.mjs\nnode --test tests/b.mjs\nmkdir -p output'), ['node', 'npm'])
        self.assertEqual(preflight.prerequisites('PLAYWRIGHT_BROWSERS_PATH=.pw-browsers node --test a.mjs'), ['node'])

    def test_unknown_or_compound_commands_require_diagnosis(self):
        for command in ('custom-check --all', 'for f in *.sh; do bash "$f"; done'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                preflight.prerequisites(command)

    def test_compound_commands_and_redirections(self):
        commands = """mkdir -p evidence && shasum -a 256 index.html > evidence/hashes
bash tests/static.sh > evidence/static.log 2>&1
PLAYWRIGHT_BROWSERS_PATH=.pw-browsers npx playwright test --reporter=list,json
shasum -a 256 -c evidence/hashes && test -s evidence/static.log
node a.js | node b.js; python3 checks.py || printf failure
"""
        self.assertEqual(preflight.prerequisites(commands), ['bash', 'node', 'npx', 'python3', 'shasum'])

    def test_hidden_commands_and_malformed_syntax_fall_back(self):
        for command in ('node $(touch sentinel)', 'echo `touch sentinel`',
                        'node a.js &', 'node a.js &&', 'node a.js >',
                        'node a.js <<EOF', 'bash -c "custom-tool"',
                        'node a.js && PATH=/tmp node b.js', 'node a.js && custom-tool'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                preflight.prerequisites(command)

    def test_commands_are_not_executed_or_redirected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands, report = root/'commands', root/'report'
            sentinel = root/'must-not-exist'
            commands.write_text(f'mkdir -p "{sentinel}" && shasum -a 256 missing > "{sentinel}"')
            with patch.object(preflight, 'probe', return_value='shasum runtime started') as probe:
                preflight.run(commands, report)
                probe.assert_called_once_with('shasum')
            self.assertFalse(sentinel.exists())
            self.assertLess(report.stat().st_size, 1500)

    def test_report_created_only_when_all_probes_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = Path(directory) / 'commands'
            report = Path(directory) / 'report'
            commands.write_text('node --test missing-file.mjs')
            with patch.object(preflight, 'probe', side_effect=ValueError('missing runtime')):
                with self.assertRaises(ValueError):
                    preflight.run(commands, report)
            self.assertFalse(report.exists())
            with patch.object(preflight, 'probe', return_value='node --version exited 0'):
                preflight.run(commands, report)
            self.assertIn('PF-RUNTIME', report.read_text())
            self.assertIn('no application acceptance claims', report.read_text())

    def test_posix_shell_probe(self):
        self.assertEqual(preflight.prerequisites('sh tests/static.sh > output.log 2>&1'), ['sh'])
        with self.assertRaises(ValueError):
            preflight.prerequisites('sh -c "custom-tool"')
        self.assertIn('fixed startup probe exited 0', preflight.probe('sh'))

    def test_tee_pipeline_probe_does_not_write_plan_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / 'must-not-exist'
            commands, report = root / 'commands', root / 'report'
            commands.write_text(f'python3 missing.py 2>&1 | tee "{sentinel}"')
            self.assertEqual(preflight.prerequisites(commands.read_text()), ['python3', 'tee'])
            preflight.run(commands, report)
            self.assertFalse(sentinel.exists())
            self.assertIn('tee fixed startup probe exited 0', report.read_text())

    def test_missing_tee_still_requires_diagnosis(self):
        with patch.object(preflight.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Missing runtime: tee'):
                preflight.probe('tee')

    def test_real_python_probe(self):
        self.assertIn('exited 0', preflight.probe('python3'))


if __name__ == '__main__':
    unittest.main()
