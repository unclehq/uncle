"""The build check after a wave: answered in a throwaway copy, never touching the project, with the lines that say what broke."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
import wave_build_check as check  # noqa: E402

FAKE_NPM = """#!/usr/bin/env bash
# stands in for npm: `npm run build` writes dist/ in its cwd, then fails, hangs or passes as told
echo "building in $PWD" >> "$FAKE_LOG"
echo "TOP: $(ls -A . | tr '\\n' ' ')" >> "$FAKE_LOG"
ls node_modules >> "$FAKE_LOG" 2>&1 || echo "no node_modules here" >> "$FAKE_LOG"
mkdir -p dist; echo built > dist/out.js
case "${FAKE_MODE:-pass}" in
  fail) printf 'vite v8 building...\\nerror during build:\\nError: Rolldown failed to resolve import "react-dom/client" from "src/main.jsx".\\n   at noise\\n' >&2; exit 1 ;;
  hang) sleep 30 ;;
  quiet) echo "boom" >&2; exit 2 ;;
esac
"""


def project(scripts=True, modules=True):
    folder = Path(tempfile.mkdtemp())
    (folder / 'package.json').write_text(json.dumps({'scripts': {'build': 'vite build'}} if scripts else {'name': 'x'}))
    (folder / 'src').mkdir()
    (folder / 'src' / 'main.jsx').write_text('x')
    if modules:
        (folder / 'node_modules' / 'react').mkdir(parents=True)
    (folder / 'dist').mkdir()
    (folder / 'dist' / 'stale.js').write_text('old')
    (folder / '.uncle').mkdir()
    (folder / '.uncle' / 'state').write_text('secret')
    return folder


def run(folder, mode='pass', timeout=20):
    bindir = Path(tempfile.mkdtemp())
    npm = bindir / 'npm'
    npm.write_text(FAKE_NPM)
    npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
    log = bindir / 'log'
    log.write_text('')
    out = bindir / 'out.json'
    env = dict(os.environ, PATH='%s:%s' % (bindir, os.environ['PATH']), FAKE_MODE=mode, FAKE_LOG=str(log))
    done = subprocess.run([sys.executable, str(ROOT / 'scripts/lib/wave_build_check.py'), str(folder), str(out), str(timeout)],
                          env=env, capture_output=True, text=True, timeout=60)
    return done, (json.loads(out.read_text()) if out.exists() else None), log.read_text()


class WaveBuildCheck(unittest.TestCase):
    def test_a_passing_build_exits_zero_and_reports_ok(self):
        done, report, _ = run(project())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(report['ok'])
        self.assertEqual(report['excerpt'], '')

    def test_a_failing_build_exits_one_with_the_lines_that_say_what_broke(self):
        done, report, _ = run(project(), 'fail')
        self.assertEqual(done.returncode, 1)
        self.assertFalse(report['ok'])
        self.assertIn('failed to resolve import "react-dom/client"', report['excerpt'])

    def test_the_excerpt_prefers_error_lines_to_noise(self):
        found = check.excerpt('a\nb\nerror during build:\nc\nCould not resolve x\nd')
        self.assertEqual(found.splitlines(), ['error during build:', 'Could not resolve x'])

    def test_with_no_error_words_the_excerpt_is_the_tail(self):
        found = check.excerpt('\n'.join('line %d' % n for n in range(30)))
        self.assertEqual(found.splitlines()[-1], 'line 29')
        self.assertEqual(len(found.splitlines()), 10)

    def test_the_excerpt_is_capped(self):
        self.assertLessEqual(len(check.excerpt('error ' + 'x' * 5000)), 1500)

    def test_colour_codes_are_stripped(self):
        self.assertEqual(check.excerpt('\x1b[31merror\x1b[0m: bad'), 'error: bad')

    def test_a_build_that_hangs_is_cut_off_and_reported_as_a_failure(self):
        done, report, _ = run(project(), 'hang', timeout=1)
        self.assertEqual(done.returncode, 1)
        self.assertIn('timed out', report['excerpt'])

    def test_a_failure_with_no_error_words_still_says_something(self):
        done, report, _ = run(project(), 'quiet')
        self.assertEqual(done.returncode, 1)
        self.assertIn('boom', report['excerpt'])


class ProjectIsLeftAlone(unittest.TestCase):
    def test_the_build_runs_in_a_copy_and_leaves_the_project_untouched(self):
        folder = project()
        before = sorted(str(p.relative_to(folder)) for p in folder.rglob('*') if 'node_modules' not in p.parts)
        done, report, log = run(folder)
        after = sorted(str(p.relative_to(folder)) for p in folder.rglob('*') if 'node_modules' not in p.parts)
        self.assertEqual(before, after)
        self.assertEqual((folder / 'dist' / 'stale.js').read_text(), 'old')
        self.assertNotIn(str(folder) + '\n', log)                       # it did not build in the project itself

    def top(self, log):
        return next(line for line in log.splitlines() if line.startswith('TOP:')).split()[1:]

    def test_the_driver_state_directory_is_not_copied(self):
        _, _, log = run(project())
        self.assertNotIn('.uncle', self.top(log))
        self.assertIn('src', self.top(log))                                # the project's own files are

    def test_installed_dependencies_are_linked_in(self):
        _, _, log = run(project())
        self.assertIn('react', log)
        self.assertNotIn('no node_modules here', log)

    def test_a_project_with_nothing_installed_gets_no_link(self):
        _, _, log = run(project(modules=False))
        self.assertIn('no node_modules here', log)

    def test_stale_build_output_is_not_carried_into_the_copy(self):
        _, _, log = run(project())
        self.assertNotIn('dist', self.top(log))


class Probe(unittest.TestCase):
    def probe(self, folder):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/lib/wave_build_check.py'), '--probe', str(folder)],
                              capture_output=True, text=True).returncode

    def test_a_project_with_a_build_script_has_something_to_build(self):
        self.assertEqual(self.probe(project()), 0)

    def test_a_project_without_one_does_not(self):
        self.assertEqual(self.probe(project(scripts=False)), 3)

    def test_a_probe_runs_nothing_and_writes_nothing(self):
        folder = project(); before = sorted(str(p) for p in folder.rglob('*') if 'node_modules' not in p.parts)
        self.probe(folder)
        self.assertEqual(before, sorted(str(p) for p in folder.rglob('*') if 'node_modules' not in p.parts))


class NothingToBuild(unittest.TestCase):
    def test_no_build_script_exits_three_and_writes_nothing(self):
        done, report, log = run(project(scripts=False))
        self.assertEqual(done.returncode, 3)
        self.assertIsNone(report)
        self.assertEqual(log, '')

    def test_no_package_json_exits_three(self):
        folder = project()
        (folder / 'package.json').unlink()
        done, report, _ = run(folder)
        self.assertEqual(done.returncode, 3)

    def test_a_broken_package_json_exits_three(self):
        folder = project()
        (folder / 'package.json').write_text('{not json')
        done, report, _ = run(folder)
        self.assertEqual(done.returncode, 3)


if __name__ == '__main__':
    unittest.main()
