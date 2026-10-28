#!/usr/bin/env python3
"""A clean install that needs a lockfile is changed to the install that creates it, only when there is none."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / 'lib'
sys.path.insert(0, str(LIB))
import install_command as ic


class Adapt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_npm_ci_becomes_npm_install_when_there_is_no_lockfile(self):
        line, why = ic.adapt('npm ls --depth=0 >/dev/null 2>&1 || npm ci', self.root)
        self.assertEqual(line, 'npm ls --depth=0 >/dev/null 2>&1 || npm install')
        self.assertIn('package-lock.json', why)

    def test_it_is_left_alone_when_a_lockfile_exists(self):
        (self.root / 'package-lock.json').write_text('{}')
        self.assertEqual(ic.adapt('npm ci', self.root), ('npm ci', ''))
        (self.root / 'package-lock.json').unlink()
        (self.root / 'npm-shrinkwrap.json').write_text('{}')
        self.assertEqual(ic.adapt('npm ci', self.root), ('npm ci', ''))

    def test_other_commands_and_lookalikes_are_untouched(self):
        for command in ('npx vitest run', 'npm install', 'npm run circle', 'echo npm cinema', 'node tools/ci.js'):
            self.assertEqual(ic.adapt(command, self.root), (command, ''))

    def test_frozen_lockfile_flags_are_dropped_only_without_their_lockfile(self):
        self.assertEqual(ic.adapt('yarn install --frozen-lockfile', self.root)[0], 'yarn install')
        self.assertEqual(ic.adapt('pnpm install --frozen-lockfile', self.root)[0], 'pnpm install')
        (self.root / 'yarn.lock').write_text('')
        self.assertEqual(ic.adapt('yarn install --frozen-lockfile', self.root)[1], '')

    def test_the_commands_file_keeps_its_lines_and_says_what_changed(self):
        commands = self.root / 'commands'
        commands.write_text('npm ls --depth=0 >/dev/null 2>&1 || npm ci\nnpx vite build\nnpx vitest run')
        notes = ic.normalize(commands, self.root)
        self.assertEqual(len(notes), 1)
        self.assertEqual(commands.read_text().split('\n'),
                         ['npm ls --depth=0 >/dev/null 2>&1 || npm install', 'npx vite build', 'npx vitest run'])

    def test_a_file_with_nothing_to_change_is_not_rewritten(self):
        commands = self.root / 'commands'
        commands.write_text('npx vitest run\n')
        self.assertEqual(ic.normalize(commands, self.root), [])
        self.assertEqual(commands.read_text(), 'npx vitest run\n')

    def test_the_cli_prints_the_change(self):
        commands = self.root / 'commands'
        commands.write_text('npm ci\n')
        done = subprocess.run([sys.executable, str(LIB / 'install_command.py'), 'normalize', str(commands), str(self.root)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertIn('Install command adapted: npm ci -> npm install', done.stdout)


class Unprotect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def paths(self, *lines):
        path = self.root / 'verification.paths'
        path.write_text('\n'.join(lines) + '\n')
        return path

    def test_a_lockfile_that_does_not_exist_yet_is_not_protected(self):
        path = self.paths('tests/a.test.js', 'package.json', 'package-lock.json', 'vite.config.js')
        self.assertEqual(ic.unprotect(path, self.root), ['package-lock.json'])
        self.assertEqual(path.read_text(), 'tests/a.test.js\npackage.json\nvite.config.js\n')

    def test_a_lockfile_that_exists_stays_protected(self):
        (self.root / 'package-lock.json').write_text('{}')
        path = self.paths('package.json', 'package-lock.json')
        self.assertEqual(ic.unprotect(path, self.root), [])
        self.assertEqual(path.read_text(), 'package.json\npackage-lock.json\n')

    def test_only_generated_lockfiles_are_dropped_not_other_missing_files(self):
        path = self.paths('tests/new.test.js', 'src/app.js', 'yarn.lock', 'sub/pnpm-lock.yaml')
        self.assertEqual(ic.unprotect(path, self.root), ['yarn.lock', 'sub/pnpm-lock.yaml'])
        self.assertEqual(path.read_text(), 'tests/new.test.js\nsrc/app.js\n')

    def test_the_cli_says_what_it_dropped(self):
        path = self.paths('package-lock.json', 'package.json')
        done = subprocess.run([sys.executable, str(LIB / 'install_command.py'), 'unprotect', str(path), str(self.root)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)
        self.assertIn('Protected path dropped: package-lock.json', done.stdout)


class Playwright(unittest.TestCase):
    def test_the_browser_download_checks_the_local_cli_first(self):
        line, why = ic.adapt('npx playwright install chromium', '.')
        self.assertEqual(line, 'npx --no-install playwright install chromium || npx playwright install chromium')
        self.assertIn('--no-install', why)

    def test_it_is_idempotent_and_leaves_chained_commands_alone(self):
        once, _ = ic.adapt('npx playwright install chromium', '.')
        self.assertEqual(ic.adapt(once, '.'), (once, ''))
        chained = 'npm ci && npx playwright install chromium'
        self.assertEqual(ic.adapt(chained, '.')[0].count('--no-install'), 0)


if __name__ == '__main__':
    unittest.main()
