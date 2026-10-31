"""Compatibility findings stop checks before project test code can run."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import browser_install
import dependency_versions
import preflight


class Compatibility(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.old)
        env = patch.dict(os.environ, {
            'UNCLE_CONFIG': str(self.root / 'config'),
            'WORKFLOW_DEPENDENCY_VERSION_CHECK': '1',
            'WORKFLOW_PLAYWRIGHT_MIN_VERSION': '1.50',
            'WORKFLOW_INSTALL_LOCK': str(self.root / 'install.lock'),
        })
        env.start()
        self.addCleanup(env.stop)
        Path('package.json').write_text('{"devDependencies":{"@playwright/test":"latest"}}')
        self.package = Path('node_modules/@playwright/test/package.json')
        self.package.parent.mkdir(parents=True)
        self.package.write_text('{"version":"1.48.2"}')

    def test_serial_and_parallel_fail_before_command(self):
        command = 'touch should-not-run'
        Path('commands').write_text(command + '\n')
        Path('groups').write_text('')
        for script, args in (
            ('run_check.py', ['--shell-command', command, '--', 'sh', '-c', command]),
            ('parallel_checks.py', ['--commands', 'commands', '--groups', 'groups',
                                    '--out', 'results', '--log', 'log']),
        ):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, '-B', str(LIB / script), *args],
                                        capture_output=True, text=True, timeout=10)
                if script == 'run_check.py':
                    self.assertEqual(result.returncode, 126, result.stderr)
                    log = result.stdout
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(Path('results').read_text().startswith('126\t'))
                    log = Path('log').read_text()
                self.assertIn('DEPENDENCY_VERSION', log)
                self.assertIn('1.48.2', log)
                self.assertFalse(Path('should-not-run').exists())

    def test_preflight_finding_prevents_runtime_pass(self):
        Path('commands').write_text('node --test\n')
        with patch.object(preflight, 'probe') as probe:
            with self.assertRaisesRegex(ValueError, 'DEPENDENCY_VERSION'):
                preflight.run('commands', 'report')
        probe.assert_not_called()
        self.assertFalse(Path('report').exists())

    def test_install_can_replace_stale_version_then_checks_resolution(self):
        with browser_install.prepare('npm install', io.BytesIO(), {}):
            self.package.write_text('{"version":"1.64.1"}')
        with self.assertRaisesRegex(ValueError, '1.48.2'):
            with browser_install.prepare('npm install', io.BytesIO(), {}):
                self.package.write_text('{"version":"1.48.2"}')

    def test_combined_install_and_test_rejects_known_old_resolution(self):
        with self.assertRaisesRegex(ValueError, '1.48.2'):
            with browser_install.prepare('npm ci && npx playwright test', io.BytesIO(), {}):
                self.fail('known old Playwright must not reach tests')

    def test_combined_clean_install_checks_lock_before_current_install(self):
        self.package.write_text('{"version":"1.55.0"}')
        Path('package-lock.json').write_text(json.dumps({
            'packages': {'node_modules/@playwright/test': {'version': '1.48.2'}}}))
        dependency_versions.check(self.root)
        with self.assertRaisesRegex(ValueError, 'package-lock.json resolves @playwright/test 1.48.2'):
            with browser_install.prepare('npm ci && npx playwright test', io.BytesIO(), {}):
                self.fail('clean install must not downgrade Playwright before tests')

    def test_supported_engine_ranges(self):
        for expression, expected in [('>=22', True), ('^22 || ^26', True), ('~26.0', True),
                                     ('22 - 26', True), ('26.x', True), ('<=26', True),
                                     ('>26', False), ('^22', False), ('<26', False)]:
            with self.subTest(expression=expression):
                self.assertEqual(dependency_versions.accepts_node(expression, (26, 0, 0)), expected)

    def test_no_project_js_or_plan_mutation_for_node_finding(self):
        Path('package.json').write_text(json.dumps({'engines': {'node': '^22'}}))
        self.package.unlink()
        Path('approved-plan').write_text('immutable')
        with patch.object(dependency_versions.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, 'v26.0.0\n', '')) as run:
            with self.assertRaisesRegex(ValueError, 'excludes installed Node 26.0.0'):
                dependency_versions.check(self.root)
        self.assertEqual(run.call_args.args[0], ['node', '--version'])
        self.assertEqual(run.call_args.kwargs['timeout'], 5)
        self.assertEqual(Path('approved-plan').read_text(), 'immutable')


if __name__ == '__main__':
    unittest.main()
