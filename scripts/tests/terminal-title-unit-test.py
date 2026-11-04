#!/usr/bin/env python3
"""Unit tests for scripts/lib/terminal_title.py (AC-1, AC-5, AC-7, AC-8 helper parts)."""
import importlib.util
import io
import os
import pty
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, '..', 'lib', 'terminal_title.py')
spec = importlib.util.spec_from_file_location('terminal_title_under_test', MODULE)
tt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tt)

OSC = '\033]2;%s\007'


class Tty(io.StringIO):
    def __init__(self, tty=True):
        super().__init__()
        self._tty = tty

    def isatty(self):
        return self._tty


def env(**kw):
    base = {'TERM': 'xterm', 'UNCLE_PROJECT_ROOT': '/work/myproj'}
    base.update(kw)
    return mock.patch.dict(os.environ, base, clear=True)


class Builder(unittest.TestCase):
    def test_no_issue(self):
        self.assertEqual(tt.build_title('proj'), 'proj · uncle')

    def test_issue(self):
        self.assertEqual(tt.build_title('proj', '152'), 'proj · uncle issue #152')

    def test_bad_issues_are_no_issue(self):
        for bad in ('', 'abc', '12a', '--x', '-1', ' 1', '1 ', '１２', None):
            self.assertEqual(tt.build_title('proj', bad), 'proj · uncle', repr(bad))

    def test_long_digits_never_truncated(self):
        digits = '9' * 200
        self.assertEqual(tt.build_title('p', digits), 'p · uncle issue #' + digits)

    def test_controls_stripped_before_cap(self):
        name = 'a\x1b]2;x\x07' + 'b' * 100
        out = tt.build_title(name)
        self.assertNotIn('\x1b', out)
        self.assertNotIn('\x07', out)
        self.assertTrue(out.endswith(' · uncle'))

    def test_cap_only_on_project(self):
        out = tt.build_title('x' * 100, '42')
        self.assertEqual(out, 'x' * 60 + ' · uncle issue #42')
        self.assertEqual(tt.build_title('y' * 100), 'y' * 60 + ' · uncle')

    def test_cap_counts_code_points(self):
        self.assertEqual(tt.build_title('é' * 70), 'é' * 60 + ' · uncle')

    def test_unicode_categories_dropped(self):
        s = 'a​b c d\x7fe\x85f'
        self.assertEqual(tt.sanitize(s), 'abcdef')

    def test_trim(self):
        self.assertEqual(tt.sanitize('  hi \t'), 'hi')

    def test_empty_or_all_control_is_bare_uncle(self):
        for name in ('', '\x1b\x07\n', '   ', None):
            self.assertEqual(tt.build_title(name), 'uncle')
            self.assertEqual(tt.build_title(name, '5'), 'uncle')


class ProjectName(unittest.TestCase):
    def test_absolute_root(self):
        with env(UNCLE_PROJECT_ROOT='/a/b/proj/'):
            self.assertEqual(tt.project_name(), 'proj')

    def test_relative_or_empty_root_uses_cwd(self):
        for root in ('rel/path', ''):
            with env(UNCLE_PROJECT_ROOT=root):
                self.assertEqual(tt.project_name(), tt.sanitize(os.path.basename(os.getcwd())))

    def test_unset_uses_cwd(self):
        with env():
            os.environ.pop('UNCLE_PROJECT_ROOT')
            self.assertEqual(tt.project_name(), tt.sanitize(os.path.basename(os.getcwd())))

    def test_root_slash_empty(self):
        with env(UNCLE_PROJECT_ROOT='/'):
            self.assertEqual(tt.project_name(), '')
            self.assertEqual(tt.build_title(tt.project_name(), '3'), 'uncle')

    def test_control_name(self):
        with env(UNCLE_PROJECT_ROOT='/a/\x1b\x07'):
            self.assertEqual(tt.project_name(), '')


class Guard(unittest.TestCase):
    def check(self, out_tty, err_tty, **kw):
        with env(**kw), mock.patch.object(sys, 'stdout', Tty(out_tty)), \
                mock.patch.object(sys, 'stderr', Tty(err_tty)):
            return tt.enabled()

    def test_both_ttys(self):
        self.assertTrue(self.check(True, True))

    def test_only_one_tty(self):
        self.assertFalse(self.check(True, False))
        self.assertFalse(self.check(False, True))
        self.assertFalse(self.check(False, False))

    def test_term(self):
        self.assertFalse(self.check(True, True, TERM='dumb'))
        self.assertFalse(self.check(True, True, TERM=''))

    def test_optout_only_exact_zero(self):
        self.assertFalse(self.check(True, True, UNCLE_TERMINAL_TITLE='0'))
        for v in ('', '1', 'false', 'no', '00', ' 0'):
            self.assertTrue(self.check(True, True, UNCLE_TERMINAL_TITLE=v), v)


class Writers(unittest.TestCase):
    def setUp(self):
        tt._pushed = False
        self.out, self.err = Tty(), Tty()
        patches = [env(), mock.patch.object(sys, 'stdout', self.out),
                   mock.patch.object(sys, 'stderr', self.err)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_begin_pushes_once(self):
        self.assertTrue(tt.begin('7'))
        self.assertFalse(tt.begin('8'))
        self.assertEqual(self.out.getvalue(), tt.PUSH + OSC % 'myproj · uncle issue #7')
        self.assertEqual(self.err.getvalue(), '')

    def test_stream_selection(self):
        stream = Tty()
        tt.begin(None, stream=stream)
        self.assertEqual(stream.getvalue(), tt.PUSH + OSC % 'myproj · uncle')
        self.assertEqual(self.out.getvalue(), '')
        tt.end(stream=stream)
        self.assertEqual(stream.getvalue().count(tt.POP), 1)
        self.assertEqual(self.out.getvalue(), '')

    def test_end_title_then_pop_idempotent(self):
        tt.begin('7')
        self.out.truncate(0)
        self.out.seek(0)
        self.assertTrue(tt.end())
        self.assertEqual(self.out.getvalue(), OSC % 'myproj · uncle' + tt.POP)
        self.assertFalse(tt.end())
        self.assertEqual(self.out.getvalue(), OSC % 'myproj · uncle' + tt.POP)

    def test_end_without_begin_writes_nothing(self):
        self.assertFalse(tt.end())
        self.assertEqual(self.out.getvalue(), '')

    def test_guard_false_nothing_pushed(self):
        with env(UNCLE_TERMINAL_TITLE='0'):
            self.assertFalse(tt.begin('1'))
            self.assertFalse(tt.end())
        self.assertEqual(self.out.getvalue(), '')

    def test_end_rechecks_guard(self):
        tt.begin('1')
        before = self.out.getvalue()
        with env(UNCLE_TERMINAL_TITLE='0'):
            self.assertFalse(tt.end())
        self.assertEqual(self.out.getvalue(), before)
        self.assertNotIn(tt.POP, self.out.getvalue())

    def test_retitle_no_push_no_pop(self):
        tt.begin(None)
        self.out.truncate(0)
        self.out.seek(0)
        tt.retitle('9')
        self.assertEqual(self.out.getvalue(), OSC % 'myproj · uncle issue #9')

    def test_write_failure_silent(self):
        class Bad(Tty):
            def write(self, _):
                raise OSError('boom')
        self.assertFalse(tt.begin('1', stream=Bad()))
        self.assertFalse(tt._pushed)


class Cli(unittest.TestCase):
    def run_cli(self, args, tty=True, **kw):
        e = {'TERM': 'xterm', 'UNCLE_PROJECT_ROOT': '/work/myproj', 'PATH': os.environ['PATH']}
        e.update(kw)
        if tty:
            master, slave = pty.openpty()
            p = subprocess.run([sys.executable, '-B', MODULE] + args, env=e,
                               stdout=slave, stderr=slave, stdin=subprocess.DEVNULL)
            import select
            data = os.read(master, 65536).decode() if select.select([master], [], [], 0.2)[0] else ''
            os.close(slave)
            os.close(master)
            return p.returncode, data
        p = subprocess.run([sys.executable, '-B', MODULE] + args, env=e,
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_begin_end_retitle(self):
        rc, out = self.run_cli(['begin', '12'])
        self.assertEqual((rc, out), (0, tt.PUSH + OSC % 'myproj · uncle issue #12'))
        rc, out = self.run_cli(['retitle', '12'])
        self.assertEqual(out, OSC % 'myproj · uncle issue #12')
        rc, out = self.run_cli(['end'])
        self.assertEqual((rc, out), (0, OSC % 'myproj · uncle' + tt.POP))

    def test_non_tty_silent(self):
        for cmd in ('begin', 'retitle', 'end'):
            self.assertEqual(self.run_cli([cmd, '1'], tty=False), (0, ''))

    def test_optout_silent(self):
        self.assertEqual(self.run_cli(['begin', '1'], UNCLE_TERMINAL_TITLE='0'), (0, ''))

    def test_argv_hardening(self):
        for arg in ('abc', '', '--x', '-h', '12a', '/etc/passwd'):
            rc, out = self.run_cli(['begin', arg])
            self.assertEqual(rc, 0)
            self.assertEqual(out, tt.PUSH + OSC % 'myproj · uncle', repr(arg))
        rc, out = self.run_cli(['begin', '9' * 100])
        self.assertTrue(out.endswith('#' + '9' * 100 + '\007'))

    def test_extra_args_do_not_change_root(self):
        rc, out = self.run_cli(['begin', '5', '/other/root'])
        self.assertEqual(out, tt.PUSH + OSC % 'myproj · uncle issue #5')

    def test_unknown_command_exit_zero(self):
        self.assertEqual(self.run_cli(['bogus']), (0, ''))
        self.assertEqual(self.run_cli([]), (0, ''))


if __name__ == '__main__':
    unittest.main()
