#!/usr/bin/env python3
"""Current dependency guidance and local compatibility checks; no installs or network."""
import json
import importlib
import io
import os
from pathlib import Path
import re
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))


class DependencyGuidance(unittest.TestCase):
    def test_planning_and_implementation_preserve_installed_node(self):
        for name in ('project-plan.md', 'project-plan-investigate.md',
                     'project-plan-section-shared.md', 'requirements-plan.md',
                     'implement.md', 'module-interfaces.md'):
            with self.subTest(prompt=name):
                text = re.sub(r'\s+', ' ', (ROOT / 'prompts' / name).read_text()).lower()
                self.assertIn('current stable', text)
                self.assertRegex(text, r'install.time|at install')
                self.assertIn('playwright', text)
                self.assertIn('engines.node', text)
                self.assertRegex(text, r'installed node(?:\.js)? major')

    def test_template_tooling_resolves_current_stable_at_install(self):
        package = json.loads((ROOT / 'scripts/templates/vite-react/package.json').read_text())
        for name, floor in (('@playwright/test', (1, 50)), ('vite', (7, 0)),
                            ('vitest', (4, 0))):
            with self.subTest(package=name):
                value = package['devDependencies'][name]
                if value == 'latest':
                    continue
                self.assertRegex(value, r'^\^\d+\.\d+(?:\.\d+)?$')
                self.assertGreaterEqual(tuple(map(int, value[1:].split('.')[:2])), floor)


class DependencyGuard(unittest.TestCase):
    def setUp(self):
        self.guard = importlib.import_module('dependency_versions')
        temporary = tempfile.TemporaryDirectory(prefix='uncle-version-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        node = self.bin / 'node'
        node.write_text('#!/bin/sh\ncase "$1" in\n--version|-v) printf "v26.0.0\\n" ;;\n*) exit 73 ;;\nesac\n')
        node.chmod(0o755)
        config = self.root / '.uncle/config'
        config.parent.mkdir()
        config.write_text('')
        self.config = config
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'PATH': str(self.bin), 'UNCLE_CONFIG': str(config),
                               'WORKFLOW_INSTALL_LOCK': str(self.root / 'install.lock')}, clear=True).start()

    def manifest(self, playwright='^1.55.0', engines=None):
        package = {'private': True, 'devDependencies': {'@playwright/test': playwright}}
        if engines is not None:
            package['engines'] = {'node': engines}
        (self.root / 'package.json').write_text(json.dumps(package))

    def installed(self, version):
        target = self.root / 'node_modules/@playwright/test/package.json'
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({'name': '@playwright/test', 'version': version}))

    def lockfile(self, version, name='package-lock.json', legacy=False):
        data = ({'lockfileVersion': 1, 'dependencies': {'@playwright/test': {'version': version}}}
                if legacy else {'lockfileVersion': 3, 'packages': {
                    'node_modules/@playwright/test': {'version': version}}})
        (self.root / name).write_text(json.dumps(data))

    def assert_playwright_finding(self, version='1.48.2', floor='1.50'):
        with self.assertRaises(ValueError) as caught:
            self.guard.check(self.root)
        message = str(caught.exception)
        self.assertIn('@playwright/test', message)
        self.assertIn(version, message)
        self.assertIn(floor, message)
        self.assertRegex(message.lower(), r'upgrade|update|current stable')
        return message

    def test_exact_old_manifest_pin_fails_before_install(self):
        self.manifest('1.48.2')
        self.assert_playwright_finding()

    def test_unresolved_current_range_is_not_an_old_resolved_version(self):
        for version in ('^1.55.0', 'latest', '^1.48.2'):
            with self.subTest(version=version):
                self.manifest(version)
                self.guard.check(self.root)

    def test_installed_old_version_cannot_hide_behind_current_manifest(self):
        self.manifest()
        self.installed('1.48.2')
        self.assert_playwright_finding()

    def test_lockfiles_cannot_hide_old_resolved_version(self):
        self.manifest()
        for name, legacy in (('package-lock.json', False), ('package-lock.json', True),
                             ('npm-shrinkwrap.json', False)):
            with self.subTest(name=name, legacy=legacy):
                self.lockfile('1.48.2', name, legacy)
                self.assert_playwright_finding()
                (self.root / name).unlink()

    def test_installed_version_is_authoritative_over_stale_lockfile(self):
        self.manifest()
        self.lockfile('1.48.2')
        self.installed('1.55.0')
        self.guard.check(self.root)

    def test_default_floor_is_inclusive_and_compares_major_minor_numerically(self):
        for version in ('1.50.0', '1.55.0', '1.100.0', '2.0.0'):
            with self.subTest(version=version):
                self.manifest(version)
                self.guard.check(self.root)
        self.manifest('1.9.99')
        self.assert_playwright_finding('1.9.99')

    def test_project_config_and_environment_floor_precedence(self):
        self.manifest('1.55.0')
        self.config.write_text('execution.playwright-min-version 1.60\n')
        self.assert_playwright_finding('1.55.0', '1.60')
        with patch.dict(os.environ, {'WORKFLOW_PLAYWRIGHT_MIN_VERSION': '1.54'}):
            self.guard.check(self.root)

    def test_guard_can_be_disabled_through_config_or_environment(self):
        self.manifest('1.48.2', '<26')
        self.config.write_text('execution.dependency-version-check false\n')
        self.guard.check(self.root)
        self.config.write_text('execution.dependency-version-check true\n')
        with patch.dict(os.environ, {'WORKFLOW_DEPENDENCY_VERSION_CHECK': '0'}):
            self.guard.check(self.root)

    def test_node_26_excluded_by_engines_reports_actionable_finding(self):
        for engines in ('22.x', '^22.0.0', '>=18 <26', '<=25', '18 - 22', '^20 || ^22'):
            with self.subTest(engines=engines):
                self.manifest(engines=engines)
                with self.assertRaises(ValueError) as caught:
                    self.guard.check(self.root)
                message = str(caught.exception)
                self.assertIn('engines.node', message)
                self.assertIn('26', message)
                self.assertIn(engines, message)
                self.assertRegex(message.lower(), r'accept|allow|update')

    def test_node_26_accepted_by_common_engine_ranges(self):
        for engines in ('>=18', '>=20.19.0 || >=22.12.0', '^26.0.0', '26.x',
                        '~26.0.0', '>=22 <27', '*', '22 - 26', '^22 || ^26'):
            with self.subTest(engines=engines):
                self.manifest(engines=engines)
                self.guard.check(self.root)

    def test_only_one_actionable_error_and_project_files_unchanged(self):
        self.manifest('1.48.2', '^22')
        plan = self.root / 'approved-plan.md'
        plan.write_text('Approved plan: preserve exactly.\n')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        message = self.assert_playwright_finding()
        self.assertEqual(len(message.splitlines()), 1)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_non_node_project_is_a_noop_without_node(self):
        (self.bin / 'node').unlink()
        self.guard.check(self.root)

    def test_browser_preparation_rejects_old_version_before_browser_probe(self):
        import browser_install
        self.manifest()
        self.installed('1.48.2')
        with patch.object(browser_install, 'command_needs', return_value=(False, True, self.root)), \
                patch.object(browser_install, 'ensure_browser') as browser:
            with self.assertRaisesRegex(ValueError, '@playwright/test'):
                with browser_install.prepare('npx playwright test', io.BytesIO(), dict(os.environ)):
                    self.fail('incompatible browser tests must never start')
            browser.assert_not_called()

    def test_serial_check_rejects_old_playwright_before_command_executes(self):
        self.manifest('1.48.2')
        marker = self.root / 'command-started'
        result = subprocess.run([
            sys.executable, '-I', str(ROOT / 'scripts/lib/run_check.py'),
            '--shell-command', 'npx playwright test', '--', sys.executable, '-c',
            'from pathlib import Path; Path("command-started").touch()'],
            cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 126, result.stdout + result.stderr)
        self.assertIn('@playwright/test', result.stdout)
        self.assertIn('1.48.2', result.stdout)
        self.assertFalse(marker.exists())

    def test_clean_install_and_test_cannot_hide_old_lock_behind_new_installed_version(self):
        import browser_install
        self.manifest('^1.48.2')
        self.lockfile('1.48.2')
        self.installed('1.55.0')
        with patch.object(browser_install, 'command_needs', return_value=(True, True, self.root)):
            with self.assertRaisesRegex(ValueError, '1.48.2'):
                with browser_install.prepare('npm ci && npx playwright test', io.BytesIO(), dict(os.environ)):
                    pass


if __name__ == '__main__':
    unittest.main()
