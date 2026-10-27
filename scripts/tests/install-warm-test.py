#!/usr/bin/env python3
"""The final build's packages and browser are cached while the slow stages run, without touching the project."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import install_warm as warm

NOINIT_STYLE = ("1. Scaffold & tooling - write `package.json` (deps: react, react-dom; dev: vite, @vitejs/plugin-react, "
                "vitest, and @playwright/test pinned to an exact version; scripts per D-14), `vite.config.js`.")
TABLE_STYLE = ("| S-1 | Scaffold: deps react, react-dom, vite, @vitejs/plugin-react, vitest, @playwright/test; "
               "run `npm install` for lockfile; Vitest `include: ['tests/unit/**/*.test.js']` |")


class Extract(unittest.TestCase):
    def test_both_plan_phrasings_name_the_same_packages(self):
        expected = ['react', 'react-dom', 'vite', '@vitejs/plugin-react', 'vitest', '@playwright/test']
        self.assertEqual(warm.packages(NOINIT_STYLE), expected)
        self.assertEqual(warm.packages(TABLE_STYLE), expected)

    def test_install_commands_and_pinned_versions_are_read(self):
        names = warm.packages('Run `npm install -D eslint@9.1.0 prettier` and `npm i zod`.')
        self.assertEqual(names, ['eslint@9.1.0', 'prettier', 'zod'])

    def test_prose_files_and_flags_are_not_packages(self):
        self.assertEqual(warm.packages('the deps are fine; dependencies: none'), [])
        self.assertEqual(warm.packages('deps: src/main.jsx, vite.config.js, -D'), [])
        self.assertEqual(warm.packages('Install the app, then run the tests.'), [])

    def test_the_list_is_bounded(self):
        names = ', '.join('pkg%d' % n for n in range(100))
        self.assertLessEqual(len(warm.packages('deps: ' + names)), warm.LIMIT)

    def test_playwright_is_recognised_in_either_spelling(self):
        self.assertTrue(warm.wants_playwright(['react', '@playwright/test']))
        self.assertTrue(warm.wants_playwright(['playwright@1.48.2']))
        self.assertFalse(warm.wants_playwright(['react', 'vitest']))


class Warm(unittest.TestCase):
    def setUp(self):
        self.bin = tempfile.mkdtemp()
        self.log = Path(tempfile.mkdtemp()) / 'calls'
        for name in ('npm', 'npx'):
            path = Path(self.bin) / name
            path.write_text('#!/bin/sh\necho "%s $PWD $@" >> "%s"\nexit ${FAKE_STATUS:-0}\n' % (name, self.log))
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.old_path = os.environ['PATH']
        os.environ['PATH'] = self.bin + os.pathsep + self.old_path
        self.addCleanup(lambda: os.environ.__setitem__('PATH', self.old_path))
        self.state = tempfile.mkdtemp()

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_packages_install_into_a_temporary_directory_with_scripts_off(self):
        summary = warm.warm(['react', 'vite'], self.state)
        first = self.calls()[0]
        self.assertIn('npm', first)
        self.assertIn('--ignore-scripts', first)
        self.assertIn('--no-package-lock', first)
        self.assertIn('react vite', first)
        self.assertIn('uncle-warm-', first)
        self.assertIn('2 package(s) cached', summary)

    def test_the_browser_is_fetched_only_when_playwright_is_named(self):
        warm.warm(['react'], self.state)
        self.assertEqual(len(self.calls()), 1)
        summary = warm.warm(['react', '@playwright/test'], self.state)
        self.assertTrue(any(call.startswith('npx') and 'playwright install chromium' in call for call in self.calls()))
        self.assertIn('chromium ready', summary)

    def test_an_unchanged_package_set_is_not_fetched_twice(self):
        warm.warm(['react', 'vite'], self.state)
        count = len(self.calls())
        self.assertEqual(warm.warm(['vite', 'react'], self.state), 'already warmed')
        self.assertEqual(len(self.calls()), count)

    def test_a_failed_install_is_reported_and_not_remembered(self):
        os.environ['FAKE_STATUS'] = '1'
        self.addCleanup(lambda: os.environ.pop('FAKE_STATUS', None))
        self.assertIn('not fully cached', warm.warm(['react'], self.state))
        os.environ.pop('FAKE_STATUS')
        self.assertNotEqual(warm.warm(['react'], self.state), 'already warmed')

    def test_nothing_to_warm_runs_nothing(self):
        self.assertEqual(warm.warm([], self.state), 'nothing to warm')
        self.assertEqual(self.calls(), [])

    def test_the_project_is_never_touched(self):
        project = Path(tempfile.mkdtemp())
        before = sorted(project.iterdir())
        cwd = os.getcwd()
        os.chdir(project)
        try:
            warm.warm(['react'], self.state)
        finally:
            os.chdir(cwd)
        self.assertEqual(sorted(project.iterdir()), before)
        self.assertNotIn(str(project), self.calls()[0].split()[1])

    def test_the_command_never_fails_on_a_missing_plan(self):
        self.assertEqual(warm.main(['/nonexistent/plan.md']), 0)


class Driver(unittest.TestCase):
    def run_script(self, body):
        return subprocess.run(['bash', '-c', body], capture_output=True, text=True, timeout=60)

    def test_start_is_detached_off_by_switch_and_cancelled_with_the_run(self):
        tmp = tempfile.mkdtemp()
        stub = Path(tmp) / 'stub.py'
        stub.write_text('import sys,time\nopen(sys.argv[2] + "/ran", "w").write(sys.argv[1])\ntime.sleep(30)\n')
        plan = Path(tmp) / 'plan.md'
        plan.write_text('deps: react')
        body = f'''
        ROOT={ROOT}; STATE_DIR={tmp}/state; LOG_DIR={tmp}/log; INSTALL_WARM_PY={stub}
        . {ROOT}/scripts/lib/install-warm.sh
        WORKFLOW_INSTALL_WARM=0 install_warm_start {plan}; [ -z "$INSTALL_WARM_PID" ] && echo off-ok
        install_warm_start /nonexistent; [ -z "$INSTALL_WARM_PID" ] && echo missing-ok
        install_warm_start {plan}; sleep 1; [ -f {tmp}/state/ran ] && echo started-ok
        kill -0 $INSTALL_WARM_PID && echo alive
        pid=$INSTALL_WARM_PID; install_warm_cancel; kill -0 $pid 2>/dev/null && echo still-alive || echo cancelled-ok
        '''
        out = self.run_script(body).stdout
        for expected in ('off-ok', 'missing-ok', 'started-ok', 'alive', 'cancelled-ok'):
            self.assertIn(expected, out)

    def test_the_driver_starts_it_after_each_plan_and_cancels_it_on_exit(self):
        text = (ROOT / 'scripts' / 'stagegate.sh').read_text()
        self.assertIn('install_warm_start .uncle/docs/PROJECT_PLAN.md', text)
        self.assertIn('install_warm_start .uncle/docs/UPDATED_PROJECT_PLAN.md', text)
        self.assertIn('install_warm_cancel', text.split('on_exit() {', 1)[1].split('trap on_exit EXIT', 1)[0])


if __name__ == '__main__':
    unittest.main()
