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


NOINIT_PROSE = ("1. **Scaffold project** - Write package.json (React 18, Vite 5, Vitest, Playwright dependencies and scripts), run npm "
                "install to create package-lock.json, and write vite.config.js (webServer on vite preview, tests in tests/unit).\n"
                "10. **Mutation runner** - Scratch copies link node_modules read-only: the runner never runs npm install, and covers "
                "mutation, sets scratch directory and writes hashes.\n| R-1 | Vite with @vitejs/plugin-react and React 18 |")


class Prose(unittest.TestCase):
    def test_words_after_npm_install_in_a_sentence_are_not_packages(self):
        names = warm.packages(NOINIT_PROSE)
        self.assertEqual(sorted(names), sorted(['react', 'vite', 'vitest', '@playwright/test', '@vitejs/plugin-react']))
        for word in ('to', 'create', 'covers', 'mutation', 'scratch', 'webServer'):
            self.assertNotIn(word, names)

    def test_a_name_with_a_capital_is_not_an_npm_name(self):
        self.assertEqual(warm.clean('webServer'), '')


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

    def test_one_unknown_name_does_not_stop_the_known_ones_being_cached(self):
        # `npm install` of the whole list fails when any name is unknown; `npm view` says which, and the rest is installed.
        path = Path(self.bin) / 'npm'
        path.write_text('#!/bin/sh\necho "npm $@" >> "%s"\n'
                        'case "$1" in view) [ "$2" = react ] && exit 0 || exit 1;; esac\n'
                        'case "$*" in *nonsense*) exit 1;; esac\nexit 0\n' % self.log)
        summary = warm.warm(['react', 'nonsense'], self.state)
        self.assertIn('1 package(s) cached', summary)
        installs = [c for c in self.calls() if c.startswith('npm install')]
        self.assertEqual(len(installs), 2)
        self.assertIn('nonsense', installs[0])
        self.assertNotIn('nonsense', installs[1])

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


class Timeout(unittest.TestCase):
    """A timed-out command must not leave anything running behind it.

    `npm`/`npx` routinely fork a further process (the browser download `npx playwright
    install` launches is exactly this shape) that outlives a SIGKILL sent only to the
    direct child.  A survivor from this warm-up can hold Playwright's own installer lock in
    the shared, machine-wide cache, and a *later, real* `playwright install` -- the one an
    actual build depends on -- then blocks forever waiting for a lock that orphan never
    released.  warm.run() must kill the whole process tree it started, not just the pid it
    is directly tracking.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pidfile = self.tmp / 'grandchild.pid'
        # The direct child backgrounds a grandchild in its own process group (exactly how a
        # shell's `&` behaves) and then itself sleeps past the timeout, so the timeout fires
        # while the grandchild is still alive and only reachable through the child's group.
        script = self.tmp / 'spawn-and-hang.sh'
        script.write_text('#!/bin/sh\nsleep 30 &\necho $! > "%s"\nsleep 30\n' % self.pidfile)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.command = [str(script)]

    def grandchild_pid(self):
        for _ in range(50):
            if self.pidfile.exists() and self.pidfile.read_text().strip():
                return int(self.pidfile.read_text().strip())
            import time
            time.sleep(0.1)
        self.fail('grandchild never started')

    def grandchild_alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def test_timeout_kills_the_whole_process_tree_not_just_the_direct_child(self):
        status = warm.run(self.command, str(self.tmp), 1)
        self.assertEqual(status, 124)       # the timeout status (process_tree.wait_check), which run() hands back unchanged
        pid = self.grandchild_pid()
        import time
        deadline = time.time() + 5
        while time.time() < deadline and self.grandchild_alive(pid):
            time.sleep(0.1)
        self.assertFalse(self.grandchild_alive(pid),
                          'a grandchild of the timed-out command survived -- it can hold a shared '
                          'installer lock (e.g. Playwright\'s) forever, hanging a later, real install')
        self.addCleanup(lambda: os.kill(pid, 9) if self.grandchild_alive(pid) else None)


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


if __name__ == '__main__':
    unittest.main()
