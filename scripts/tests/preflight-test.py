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
        for command in ('custom-check --all', 'node a.js && node b.js', 'for f in *.sh; do bash "$f"; done'):
            with self.subTest(command=command), self.assertRaises(ValueError):
                preflight.prerequisites(command)

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

    def test_real_python_probe(self):
        self.assertIn('exited 0', preflight.probe('python3'))


if __name__ == '__main__':
    unittest.main()
