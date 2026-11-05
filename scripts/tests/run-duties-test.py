import ast
import itertools
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'lib'))
import run_duties as rd


class Banner(unittest.TestCase):
    def test_literals(self):
        self.assertIn("Workflow complete.", rd.COMPLETION_BANNERS)
        self.assertIn("Change workflow complete.", rd.COMPLETION_BANNERS)
        self.assertEqual(rd.format_finished_line("READY", 0, "/p"),
                         "Finished build: verdict=READY skipped=0 path=/p")

    def test_collector(self):
        c = rd.BannerCollector()
        for line in ["x", "Total time: 1s", "Finished build: verdict=READY skipped=0 path=/p",
                     "Total time: 2s", "Change workflow complete."]:
            c.feed(line)
        self.assertTrue(c.completed)
        self.assertEqual(len(c.finished_lines), 2)
        self.assertEqual(rd.finished_build_lines([], "/z"),
                         ["Finished build: verdict=UNKNOWN skipped=0 path=/z"])


class Exit(unittest.TestCase):
    def test_precedence_table(self):
        for rc, done in itertools.product([0, 1, 2, 3, 7, 255, -2, -9, -15], [True, False]):
            got = rd.classify_exit(rc, done)
            if rc < 0:
                want = 128 - rc
            elif rc != 0:
                want = 1
            else:
                want = 0 if done else 3
            self.assertEqual(got, want, (rc, done))
        self.assertEqual(rd.classify_exit(0, True, signal_number=2), 130)

    def test_finish_decision(self):
        self.assertEqual(rd.finish_decision(True, True, 0), 'exit')
        self.assertEqual(rd.finish_decision(False, True, 0), 'dialog')
        self.assertEqual(rd.finish_decision(True, False, 0), 'dialog')


class Brief(unittest.TestCase):
    def test_wrap(self):
        doc = rd.startup_brief_document("build x", 'app', ['Summary', 'Goals'])
        self.assertIn("## Summary\nbuild x", doc)
        self.assertIn("## Goals\n" + rd.APP_BRIEF_FIELD_PLACEHOLDER, doc)
        got = []
        rd.write_startup_brief('/r', "## A\nb", 'app', ['Summary'], got.append)
        self.assertEqual(got, ["## A\nb"])


class DriverCommand(unittest.TestCase):
    def test_read_banner_matches_collector(self):
        # uncle_tui._read_banner delegates here (regression: the function was missing)
        self.assertEqual(rd.read_banner('Finished build: verdict=READY', False),
                         ('Finished build: verdict=READY', True, False))
        self.assertEqual(rd.read_banner('Total time: 5s', True), ('Total time: 5s', True, False))
        self.assertEqual(rd.read_banner('Total time: 5s', False), (None, False, False))
        done = rd.COMPLETION_BANNERS[0]
        self.assertEqual(rd.read_banner(done + '  ', False), (None, False, True))
        self.assertEqual(rd.read_banner('chatter', True), (None, True, False))

    def test_four_actions(self):
        r = '/r'
        s = lambda n: os.path.join(r, 'scripts', n)
        self.assertEqual(rd.build_driver_command('create_app', 'x', False, r), [s('stagegate.sh')])
        self.assertEqual(rd.build_driver_command('create_app', 'x', True, r),
                         [s('stagegate.sh'), '--attended'])
        self.assertEqual(rd.build_driver_command('github_issue', '12', False, r, '--new'),
                         [s('from-issue.sh'), '12', '--new'])
        self.assertEqual(rd.build_driver_command('change_request', 'x', False, r),
                         [s('change-workflow.sh')])
        # the TUI passes issue_mode=None for non-issue actions (regression: it was refused)
        self.assertEqual(rd.build_driver_command('create_app', 'x', False, r, None), [s('stagegate.sh')])

    def test_rejects_bad_actions(self):
        for bad in ['', None, 'bogus', '/bin/sh', '../x', 'create_app/../x',
                    'stagegate.sh', 'CREATE_APP', ' create_app', 5]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                rd.build_driver_command(bad, 'x', False, '/r')

    def test_rejects_bad_text_and_mode(self):
        with self.assertRaises(ValueError):
            rd.build_driver_command('github_issue', '  ', False, '/r')
        with self.assertRaises(ValueError):
            rd.build_driver_command('github_issue', '1', False, '/r', '--evil')

    def test_env_never_supplies_paths(self):
        old = os.environ.get('UNCLE_DRIVER')
        os.environ['UNCLE_DRIVER'] = '/evil'
        try:
            cmd = rd.build_driver_command('create_app', 'x', False, '/r')
        finally:
            if old is None:
                del os.environ['UNCLE_DRIVER']
            else:
                os.environ['UNCLE_DRIVER'] = old
        self.assertEqual(cmd, ['/r/scripts/stagegate.sh'])


class Worktree(unittest.TestCase):
    def test_skipped_when_locked_or_issue(self):
        def boom(*a, **k):
            raise AssertionError('must not run')
        self.assertIsNone(rd.prepare_worktree('/r', '/p', {'UNCLE_PROJECT_ROOT_LOCKED': '1'}, runner=boom))
        self.assertIsNone(rd.prepare_worktree('/r', '/p', {}, issue=True, runner=boom))

    def test_returns_last_line_dir(self):
        import tempfile
        import types
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout='noise\n' + d + '\n')
            self.assertEqual(rd.prepare_worktree('/r', '/p', {}, runner=run), d)
            bad = lambda *a, **k: types.SimpleNamespace(returncode=1, stdout=d)
            self.assertIsNone(rd.prepare_worktree('/r', '/p', {}, runner=bad))


class ChangeRequest(unittest.TestCase):
    def test_write_refuses_existing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rd.resolve_startup_text('a', lambda p: 'f', 'p'), 'f')
            self.assertEqual(rd.resolve_startup_text('a'), 'a')
            path = rd.write_change_request(d, 'hello')
            self.assertEqual(open(path).read(), 'hello')
            with self.assertRaises(FileExistsError):
                rd.write_change_request(d, 'again')


class NoDuplicateDefinitions(unittest.TestCase):
    def test_tui_defines_none(self):
        tree = ast.parse(open(os.path.join(ROOT, 'uncle_tui.py'), encoding='utf-8').read())
        banned = {'finish_decision', 'classify_exit', 'write_startup_brief',
                  'startup_brief_document', 'desktop_decision'}
        defined = {n.name for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertEqual(defined & banned, set())
        for lit in rd.COMPLETION_BANNERS:
            consts = [n.value for n in ast.walk(tree)
                      if isinstance(n, ast.Constant) and n.value == lit]
            self.assertEqual(consts, [], lit)


if __name__ == '__main__':
    unittest.main()
