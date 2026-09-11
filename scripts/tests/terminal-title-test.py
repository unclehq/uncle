#!/usr/bin/env python3
"""AC-1/2: PTY identity and prompt ordering (T-1/5).
AC-3: exit, cancellation, viewers (T-2/4/6).
AC-4: two-stream capability guards (T-3).
AC-5: footer identity and baseline suites (T-5; BASELINE_REPORT.md §8).
Fixtures run copied drivers with local metadata and stub stages only.
"""
import os
import io
import signal
import sys
import time
import threading
from unittest.mock import Mock, patch
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('UNCLE_TEST_SOURCE_ROOT', Path(__file__).resolve().parents[2]))
HELPER = Path(__file__).resolve().parents[1]/'lib/terminal-title.sh'
sys.path.insert(0, str(ROOT))
from uncle_tui import UncleTUI, _direct_origin_issue
TITLE = b'\x1b]2;uncle issue #12\x07'
RESET = b'\x1b]2;uncle\x07'

class Titles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.install = self.base / 'install'
        shutil.copytree(ROOT / 'scripts', self.install / 'scripts')
        shutil.copytree(ROOT / 'prompts', self.install / 'prompts')
        self.project = self.base / 'project'
        self.project.mkdir()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        gh = self.bin / 'gh'
        gh.write_text('#!/bin/sh\nprintf \'%s\\n\' \'{"title":"Title","body":"Body","url":"https://github.com/o/r/issues/12"}\'\n')
        gh.chmod(0o755)
        for driver in ('stagegate.sh', 'change-workflow.sh'):
            p = self.install / 'scripts' / driver
            p.write_text('#!/bin/bash\necho STUB-STAGE\nexit "${TEST_EXIT:-0}"\n')
            p.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
                        UNCLE_PROJECT_ROOT=str(self.project), TERM='xterm')
        self.env.pop('UNCLE_TITLE_OWNER', None)
        # All stage invocations are local, including direct-origin resets.
        stage = self.bin/'stage'
        stage.write_text('#!/bin/sh\nexit 7\n'); stage.chmod(0o755)
        self.env['WORKFLOW_AGENT_CMD'] = str(stage)
        self.env['WORKFLOW_REVIEWER_CMD'] = str(stage)

    def shell(self, mode='--change', out_tty=True, err_tty=True, extra=None, issue='https://github.com/o/r/issues/12', answer=b'NO\n', direct=False, pipe=False):
        master, slave = pty.openpty()
        env = self.env.copy()
        env.update(extra or {})
        cmd = (['bash', str(self.install/'scripts/change-workflow.sh')] if direct else
               ['bash', str(self.install/'scripts/from-issue.sh'), issue] + ([mode] if mode else []))
        if pipe:
            cmd = ['bash', '-o', 'pipefail', '-c', '"$@" | cat', 'test'] + cmd
        p = subprocess.Popen(cmd, env=env,
                             stdin=subprocess.PIPE, stdout=slave if out_tty else subprocess.PIPE,
                             stderr=slave if err_tty else subprocess.PIPE)
        data = bytearray()
        done = threading.Event()
        def read():
            while not done.is_set() or select.select([master], [], [], .05)[0]:
                if select.select([master], [], [], .05)[0]:
                    data.extend(os.read(master, 65536))
        reader = threading.Thread(target=read); reader.start()
        try:
            out, err = p.communicate(answer, timeout=15)
        except BaseException:
            p.kill(); p.communicate()
            raise
        finally:
            done.set(); reader.join()
            os.close(slave); os.close(master)
        return p.returncode, bytes(data) + (out or b'') + (err or b'')

    def test_title_precedes_prompt_and_resets(self):
        code, data = self.shell()
        self.assertEqual(code, 0)
        self.assertEqual(data.count(TITLE), 1)
        self.assertEqual(data.count(RESET), 1)
        self.assertTrue(data.startswith(TITLE))
        self.assertTrue(data.rstrip().endswith(RESET))

    def test_stream_guards(self):
        for out, err in ((False, False), (False, True), (True, False)):
            with self.subTest(out=out, err=err):
                self.assertNotIn(b'\x1b]', self.shell(out_tty=out, err_tty=err)[1])
        self.assertNotIn(b'\x1b]', self.shell(extra={'UNCLE_TITLE_OWNER':'parent'})[1])
        for term in ('', 'dumb'):
            self.assertNotIn(b'\x1b]', self.shell(extra={'TERM':term})[1])

    def test_pipe_to_cat_is_silent(self):
        code, data = self.shell(pipe=True)
        self.assertEqual(code, 0)
        self.assertNotIn(b'\x1b]', data)

    def test_modes_status_and_numeric_identity(self):
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(['git', '-C', str(self.project), 'remote', 'add', 'origin',
                        'https://github.com/o/r.git'], check=True)
        for mode in ('', '--change', '--new'):
            for issue in ('12', 'https://github.com/o/r/issues/12'):
                for status in (0, 7):
                    with self.subTest(mode=mode, issue=issue, status=status):
                        code, data = self.shell(mode=mode, issue=issue, answer=b'RUN\n',
                                                extra={'TEST_EXIT':str(status)})
                        self.assertEqual(code, status, data)
                        self.assertEqual(data.count(TITLE), 1, data)
                        self.assertEqual(data.count(RESET), 1, data)
        for issue in ('bad', '１２', '12\n'):
            self.assertNotIn(b'\x1b]', self.shell(issue=issue)[1])

    def test_nested_owner_and_shell_write_error(self):
        driver = self.install/'scripts/stagegate.sh'
        driver.write_text('#!/bin/bash\n. "$(dirname "$0")/lib/terminal-title.sh"\n'
                          'uncle_title_begin 99\nuncle_title_end\necho child-done\n')
        code, data = self.shell(mode='--new')
        self.assertEqual(code, 0)
        self.assertEqual(data.count(TITLE), 1)
        self.assertEqual(data.count(RESET), 1)
        self.assertNotIn(b'issue #99', data)
        master, slave = pty.openpty()
        p = subprocess.run(['bash', '-c', '. "$1"; printf() { return 1; }; '
                            'uncle_title_begin 12; uncle_title_end; echo survived',
                            'test', str(HELPER)], env=self.env, stdout=slave, stderr=slave)
        data = os.read(master, 1024)
        os.close(slave); os.close(master)
        self.assertEqual(p.returncode, 0)
        self.assertIn(b'survived', data)

    def test_cleanup_allows_driver_exit_trap_to_release_lock(self):
        lock = self.project/'owned-lock'; lock.touch()
        proc = subprocess.Popen(['bash', '-c', 'set -e; ROOT="$1"; '
                                 '. "$ROOT/scripts/lib/terminal-title.sh"; '
                                 'trap \'sleep .3; rm "$2"\' EXIT; '
                                 'trap \'uncle_cancel 143\' TERM; echo ready; read answer',
                                 'test', str(self.install), str(lock)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.assertEqual(proc.stdout.readline(), b'ready\n')
        subprocess.run(['bash', str(HELPER), '--stop-tree', str(proc.pid), 'include-root'], check=True)
        proc.wait(timeout=5); proc.stdin.close(); proc.stdout.close()
        self.assertFalse(lock.exists())

    def test_sourcing_helper_never_dispatches_cleanup(self):
        unrelated = subprocess.Popen(['sleep', '30'])
        try:
            result = subprocess.run(['bash', '-c', '. "$1" --stop-tree "$2" include-root; '
                                     'echo survived', 'test', str(HELPER), str(unrelated.pid)],
                                    stdout=subprocess.PIPE, check=True)
            self.assertEqual(result.stdout, b'survived\n')
            self.assertIsNone(unrelated.poll())
        finally:
            if unrelated.poll() is None: unrelated.terminate()
            unrelated.wait()

    def test_shell_repeat_and_redirected_reset(self):
        master, slave = pty.openpty()
        log = self.project/'reset.log'
        proc = subprocess.run(['bash', '-c', '. "$1"; uncle_title_begin 12; '
                               'uncle_title_end; uncle_title_begin 13; '
                               'exec > "$2"; uncle_title_end', 'test', str(HELPER), str(log)],
                              env=self.env, stdout=slave, stderr=slave)
        data = os.read(master, 1024)
        os.close(slave); os.close(master)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(data, TITLE+RESET+TITLE.replace(b'12', b'13'))
        self.assertEqual(log.read_bytes(), b'')

    def real_driver(self):
        shutil.copy2(ROOT/'scripts/change-workflow.sh', self.install/'scripts/change-workflow.sh')
        state = self.project/'.uncle/workflow'
        state.mkdir(parents=True, exist_ok=True)
        (self.project/'CHANGE_REQUEST.md').write_text('Change title.\n')
        (state/'origin').write_text('o/r\t12\tgh\n')
        (state/'state').write_text('12:COMPLETE\n')
        return state

    def test_direct_effective_identity(self):
        state = self.real_driver()
        for env, expected in (({}, TITLE),
                              ({'STAGEGATE_ORIGIN_REPO':'x/y', 'STAGEGATE_ORIGIN_ISSUE':'456'},
                               TITLE.replace(b'12', b'456')),
                              ({'STAGEGATE_ORIGIN_ISSUE':'bad'}, b'')):
            (state/'origin').write_text('o/r\t12\tgh\n')
            (state/'state').write_text('12:COMPLETE\n')
            code, data = self.shell(direct=True, extra=env)
            self.assertEqual(data.count(expected) if expected else data.count(b'\x1b]'),
                             1 if expected else 0, data)
            self.assertFalse((state/'lock').exists())
        (state/'origin').write_text('\t12\n')
        self.assertNotIn(b'\x1b]', self.shell(direct=True)[1])

    def blocking_driver(self):
        state = self.real_driver()
        (state/'state').write_text('12:ANALYZE\n')
        (self.project/'CHANGE_REQUEST.md').write_text('Change the terminal title.\n')
        stage = self.bin/'stage'
        stage.write_text('#!/usr/bin/env python3\nimport os,subprocess,sys\n'
                         'open("stage-pid", "w").write(str(os.getpid()))\n'
                         'child = subprocess.Popen([sys.executable, "-c", '
                         '\'import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                         'open("descendant-pid", "w").write(str(os.getpid())); time.sleep(60)\'])\n'
                         'child.wait()\nsys.exit(7)\n')
        stage.chmod(0o755)
        self.env['WORKFLOW_AGENT_CMD'] = str(stage)
        self.env['WORKFLOW_AGENT_CMD_BASELINE'] = str(stage)
        return state

    def cleanup_stage(self):
        for name in ('descendant-pid', 'stage-pid'):
            path = self.project/name
            if path.exists():
                subprocess.run(['bash', str(HELPER), '--stop-tree', path.read_text(),
                                'include-root'], check=True)

    def await_stage(self, proc):
        until = time.monotonic()+12
        while not (self.project/'descendant-pid').exists() and time.monotonic() < until:
            if proc.poll() is not None:
                self.fail('driver exited before stub stage: %s' % proc.returncode)
            time.sleep(.05)
        self.assertTrue((self.project/'descendant-pid').exists())
        return int((self.project/'stage-pid').read_text())

    def test_shell_cancellation_reaps_descendants_before_reset(self):
        for direct, sig in ((False, signal.SIGINT), (False, signal.SIGTERM),
                            (True, signal.SIGINT), (True, signal.SIGTERM)):
            with self.subTest(direct=direct, signal=sig):
                state = self.blocking_driver()
                (self.project/'stage-pid').unlink(missing_ok=True)
                (self.project/'descendant-pid').unlink(missing_ok=True)
                master, slave = pty.openpty()
                cmd = (['bash', str(self.install/'scripts/change-workflow.sh')] if direct else
                       ['bash', str(self.install/'scripts/from-issue.sh'),
                        'https://github.com/o/r/issues/12', '--change'])
                proc = subprocess.Popen(cmd,
                                        stdin=subprocess.PIPE, stdout=slave, stderr=slave, env=self.env)
                self.addCleanup(lambda p=proc: p.poll() is None and p.kill())
                proc.stdin.write(b'RUN\n'); proc.stdin.flush()
                unrelated = subprocess.Popen(['sleep', '30'])
                data = bytearray(); done = threading.Event(); reset_lock = []
                def read():
                    while not done.is_set() or select.select([master], [], [], .05)[0]:
                        if select.select([master], [], [], .05)[0]:
                            chunk = os.read(master, 65536); data.extend(chunk)
                            if RESET in data and not reset_lock:
                                reset_lock.append((state/'lock').exists())
                reader = threading.Thread(target=read); reader.start()
                try:
                    stage = self.await_stage(proc)
                    cancelled = time.monotonic()
                    proc.send_signal(sig)
                    self.assertEqual(proc.wait(timeout=12), 128+sig)
                    self.assertGreaterEqual(time.monotonic()-cancelled, 1.9)
                    done.set(); reader.join()
                    self.assertEqual(reset_lock, [False])
                    self.assertEqual(data.count(TITLE), 1, data)
                    self.assertEqual(data.count(RESET), 1, data)
                    self.assertFalse((state/'lock').exists())
                    with self.assertRaises(ProcessLookupError): os.kill(stage, 0)
                    child = int((self.project/'descendant-pid').read_text())
                    with self.assertRaises(ProcessLookupError): os.kill(child, 0)
                    self.assertIsNone(unrelated.poll())
                finally:
                    self.cleanup_stage()
                    unrelated.terminate(); unrelated.wait()
                    if proc.poll() is None: proc.kill(); proc.wait()
                    done.set(); reader.join()
                    proc.stdin.close()
                    os.close(slave); os.close(master)

class Stream(io.StringIO):
    def __init__(self, tty=True):
        super().__init__(); self.tty = tty
    def isatty(self): return self.tty

class CursesTitles(unittest.TestCase):
    def setUp(self):
        self.ui = UncleTUI.__new__(UncleTUI)
        self.ui.workflow_idx = 1
        self.ui.issue = '12'
        self.ui.proc = None
        self.ui.title_active = False
        self.out = Stream()
        for name, value in (('stdout', self.out), ('stderr', Stream())):
            p = patch.object(sys, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'TERM':'xterm'}); p.start(); self.addCleanup(p.stop)

    def test_identity_streams_write_errors_and_repeat(self):
        ui = self.ui
        for issue in ('12', 'https://github.com/o/r/issues/12'):
            for mode in ('', '--change', '--new'):
                ui.issue, ui.issue_mode = issue, mode
                env = {}; ui._begin_title(env)
                self.assertIn('UNCLE_TITLE_OWNER', env)
                ui._end_title(); ui._end_title()
        self.assertEqual(self.out.getvalue().encode(), (TITLE+RESET)*6)
        for issue in ('', 'bad', '１２', '12\n'):
            ui.issue = issue; self.assertEqual(ui._title_issue({}), '')
        for a, b in ((True, False), (False, True), (False, False)):
            with patch.object(sys, 'stdout', Stream(a)) as out, patch.object(sys, 'stderr', Stream(b)):
                self.assertFalse(ui._write_title('uncle')); self.assertEqual(out.getvalue(), '')
        for term in ('', 'dumb'):
            with patch.dict(os.environ, {'TERM':term}): self.assertFalse(ui._write_title('uncle'))
        with patch.dict(os.environ, {}, clear=True): self.assertFalse(ui._write_title('uncle'))
        with patch.object(self.out, 'write', side_effect=OSError):
            self.assertFalse(ui._write_title('uncle'))

    def test_direct_origin_does_not_change_footer_resolver(self):
        with tempfile.TemporaryDirectory() as project, patch('uncle_tui._project_root', return_value=project):
            state = Path(project)/'.uncle/workflow'; state.mkdir(parents=True)
            (state/'origin').write_text('o/r\t123\n'); (state/'state').write_text('123:COMPLETE\n')
            self.ui.workflow_idx = 2
            env = {'STAGEGATE_ORIGIN_REPO':'x/y','STAGEGATE_ORIGIN_ISSUE':'456'}
            self.assertEqual(self.ui._title_issue(env), '456')
            self.assertEqual(_direct_origin_issue(), '123')
            self.assertEqual(self.ui._title_issue(dict(env, STAGEGATE_ORIGIN_ISSUE='bad')), '')
            self.assertEqual(self.ui._title_issue({}), '123')
            (state/'origin').write_text('\t123\n')
            self.assertEqual(self.ui._title_issue({}), '')

    def test_eof_does_not_reset_before_exit(self):
        self.ui._begin_title({})
        self.ui.proc = Mock(); self.ui.proc.poll.return_value = None
        self.ui._poll_workflow()
        self.assertNotIn(RESET.decode(), self.out.getvalue())
        self.ui.proc.poll.return_value = 7
        self.ui._poll_workflow(); self.ui._poll_workflow()
        self.assertEqual(self.out.getvalue().encode(), TITLE+RESET)

    def test_popen_error_resets_and_child_environment(self):
        ui = self.ui
        ui.stage_env = Mock(return_value={})
        ui._restore_session_totals = Mock()
        ui.cmd_for = Mock(return_value=['unused'])
        def failed_launch(*args, **kwargs):
            self.assertEqual(self.out.getvalue().encode(), TITLE)
            raise OSError('stub launch failure')
        with patch('uncle_tui.subprocess.Popen', side_effect=failed_launch) as launch:
            with self.assertRaises(OSError): ui.start_workflow()
        self.assertEqual(self.out.getvalue().encode(), TITLE+RESET)
        self.assertIn('UNCLE_TITLE_OWNER', launch.call_args.kwargs['env'])
        self.assertEqual(launch.call_args.kwargs['stdout'], subprocess.PIPE)
        Path(ui.status_path).unlink()

    def test_signal_finally_resets(self):
        ui = self.ui
        for sig, error in ((signal.SIGINT, KeyboardInterrupt), (signal.SIGTERM, SystemExit)):
            with self.subTest(signal=sig):
                ui._begin_title({})
                ui.proc = subprocess.Popen(['sleep', '30'])
                proc = ui.proc
                with patch.object(ui, '_run_loop', side_effect=lambda: signal.raise_signal(sig)):
                    with self.assertRaises(error) as raised: ui.run()
                if sig == signal.SIGTERM: self.assertEqual(raised.exception.code, 143)
                self.assertIsNotNone(proc.returncode)
        self.assertEqual(self.out.getvalue().encode(), (TITLE+RESET)*2)

    def test_quit_cleans_real_driver_tree(self):
        fixture = Titles(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        state = fixture.blocking_driver()
        self.addCleanup(fixture.cleanup_stage)
        ui = self.ui; ui._begin_title({})
        env = dict(fixture.env, UNCLE_TITLE_OWNER=str(os.getpid()))
        ui.proc = subprocess.Popen(['bash', str(fixture.install/'scripts/from-issue.sh'),
                                    'https://github.com/o/r/issues/12', '--change'], env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        proc = ui.proc
        proc.stdin.write(b'RUN\n'); proc.stdin.flush()
        stage = fixture.await_stage(proc)
        descendant = int((fixture.project/'descendant-pid').read_text())
        write = ui._write_title
        def reset(title):
            self.assertFalse((state/'lock').exists())
            with self.assertRaises(ProcessLookupError): os.kill(stage, 0)
            with self.assertRaises(ProcessLookupError): os.kill(descendant, 0)
            return write(title)
        with patch.object(ui, '_write_title', side_effect=reset): ui.stop_workflow()
        proc.stdin.close()
        self.assertIsNotNone(proc.returncode)
        self.assertEqual(self.out.getvalue().encode(), TITLE+RESET)

    def start_viewer_driver(self):
        fixture = Titles(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.blocking_driver()
        (fixture.bin/'stage').write_text('#!/usr/bin/env python3\nimport os,time\n'
                                        'open("descendant-pid", "w").write(str(os.getpid()))\n'
                                        'time.sleep(30)\n')
        self.addCleanup(fixture.cleanup_stage)
        proc = subprocess.Popen(['bash', str(fixture.install/'scripts/change-workflow.sh')],
                                env=dict(fixture.env, UNCLE_TITLE_OWNER=str(os.getpid())),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.ui.proc = proc
        self.addCleanup(self.ui.stop_workflow)
        deadline = time.monotonic()+5
        while not (fixture.project/'descendant-pid').exists() and time.monotonic() < deadline:
            self.assertIsNone(proc.poll()); time.sleep(.05)
        self.assertTrue((fixture.project/'descendant-pid').exists())
        timer = threading.Timer(.15, proc.terminate); timer.start()
        self.addCleanup(timer.join)
        return fixture.project/'.uncle/workflow/lock'

    def test_external_viewer_observes_exit_while_open(self):
        ui = self.ui; ui.stdscr = Mock(); ui._begin_title({})
        lock = self.start_viewer_driver()
        times = []
        write = ui._write_title
        def emit(title):
            times.append(time.monotonic()); return write(title)
        start = time.monotonic()
        with patch.object(ui, '_write_title', side_effect=emit), \
             patch('uncle_tui.curses.def_prog_mode'), patch('uncle_tui.curses.endwin'), \
             patch('uncle_tui.curses.reset_prog_mode'):
            ui._run_in_terminal('sleep 1.3')
        self.assertLess(times[0]-start, 1)
        self.assertFalse(lock.exists())
        self.assertGreater(time.monotonic()-start, 1.2)
        self.assertEqual(self.out.getvalue().encode(), TITLE+RESET)

    def test_internal_viewer_and_finally(self):
        ui = self.ui; ui.state = 'viewer'; ui.stdscr = Mock()
        ui.stdscr.getmaxyx.return_value = (24, 80)
        ui._reload_tick = 0
        ui._setup_colors = Mock(); ui.poll_status = Mock(return_value=False)
        ui.poll_session_stats = Mock(return_value=False); ui.draw = Mock()
        ui._begin_title({}); lock = self.start_viewer_driver()
        deadline = time.monotonic()+1
        def key():
            time.sleep(.08)
            if RESET.decode() in self.out.getvalue():
                self.assertLess(time.monotonic(), deadline)
                self.assertEqual(ui.state, 'viewer'); self.assertFalse(lock.exists())
                ui.state = 'quit'
            if time.monotonic() > deadline: raise AssertionError('viewer missed exit')
            return -1
        ui.stdscr.getch.side_effect = key
        with patch('uncle_tui.curses.curs_set'): ui.run()
        self.assertEqual(self.out.getvalue().encode(), TITLE+RESET)
        ui._begin_title({})
        with patch.object(ui, '_run_loop', side_effect=RuntimeError), self.assertRaises(RuntimeError):
            ui.run()
        self.assertEqual(self.out.getvalue().encode(), (TITLE+RESET)*2)

if __name__ == '__main__':
    unittest.main()
