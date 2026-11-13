"""`uncle --noui` opens the preview tab the way the interactive screen does: the early page and the finished app.

Unit tests drive HeadlessPreview with a fake starter and a fake clock. The end-to-end tests run the real headless runner with a
fake driver and the real preview server; a recorder stands in for the browser, so no tab ever opens on the machine."""
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / 'lib'
sys.path.insert(0, str(LIB))
import headless_preview as hp  # noqa: E402
import uncle_headless as H  # noqa: E402


def project(family='app', state='IMPLEMENT', page=True, package=None):
    root = Path(tempfile.mkdtemp())
    (root / '.uncle' / 'workflow').mkdir(parents=True)
    if family is not None:
        (root / '.uncle' / 'workflow' / 'family').write_text(family + '\n')
    if state is not None:
        (root / '.uncle' / 'workflow' / 'state').write_text(state + '\n')
    if page:
        (root / 'index.html').write_text('<html><body>hi</body></html>\n')
    if package is not None:
        (root / 'package.json').write_text(json.dumps(package))
    return root


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class Recorder:
    def __init__(self, result=4242):
        self.calls, self.result = [], result

    def __call__(self, ttl=None):
        self.calls.append(ttl)
        return self.result


def make(root, env=None, start=None, wait=None):
    clock = Clock()
    return hp.HeadlessPreview(root, env=env or {}, start=start or Recorder(), clock=clock, wait=wait or (lambda: True)), clock


class EarlyPage(unittest.TestCase):
    def test_a_page_appearing_during_implementation_of_an_application_is_opened(self):
        root = project()
        start = Recorder()
        preview, _ = make(root, start=start)
        self.assertTrue(preview.poll())
        self.assertEqual(len(start.calls), 1)
        self.assertEqual(start.calls, [hp.EARLY_TTL_SECONDS])

    def test_it_opens_once_not_on_every_poll(self):
        root = project()
        start = Recorder()
        preview, clock = make(root, start=start)
        for _ in range(5):
            preview.poll()
            clock.advance(1)
        self.assertEqual(len(start.calls), 1)

    def test_each_stage_the_screen_watches_qualifies(self):
        for state in hp.EARLY_STATES:
            start = Recorder()
            preview, _ = make(project(state=state), start=start)
            self.assertTrue(preview.poll(), state)

    def test_stages_where_a_first_tab_would_surprise_someone_do_not(self):
        for state in ('TEST_REVIEW', 'MANUAL_CHECKLIST', 'EXECUTE_CHECKLIST', 'FINAL_AUDIT', 'COMPLETE',
                      'WAIT_PLAN_APPROVAL', 'WAIT_IMPLEMENT_APPROVAL', ''):
            start = Recorder()
            preview, _ = make(project(state=state or None), start=start)
            self.assertFalse(preview.poll(), state)
            self.assertEqual(start.calls, [], state)

    def test_a_change_request_never_gets_a_tab(self):
        start = Recorder()
        preview, _ = make(project(family='change'), start=start)
        self.assertFalse(preview.poll())
        self.assertEqual(start.calls, [])

    def test_no_recorded_family_means_no_tab(self):
        start = Recorder()
        preview, _ = make(project(family=None), start=start)
        self.assertFalse(preview.poll())
        self.assertEqual(start.calls, [])

    def test_nothing_to_show_yet_opens_nothing(self):
        start = Recorder()
        preview, _ = make(project(page=False), start=start)
        self.assertFalse(preview.poll())
        self.assertEqual(start.calls, [])

    def test_an_empty_page_is_not_a_page(self):
        root = project(page=False)
        (root / 'index.html').write_text('')
        start = Recorder()
        preview, _ = make(root, start=start)
        self.assertFalse(preview.poll())

    def test_a_server_the_driver_already_owns_is_never_duplicated(self):
        root = project()
        (root / '.uncle' / 'workflow' / 'preview-server.pid').write_text(str(os.getpid()))
        start = Recorder()
        preview, clock = make(root, start=start)
        self.assertFalse(preview.poll())
        self.assertTrue(preview.early_started)
        clock.advance(5)
        self.assertFalse(preview.poll())
        self.assertEqual(start.calls, [])

    def test_a_stale_pid_file_is_not_a_live_server(self):
        root = project()
        (root / '.uncle' / 'workflow' / 'preview-server.pid').write_text('999999')
        start = Recorder()
        preview, _ = make(root, start=start)
        self.assertTrue(preview.poll())

    def test_a_failed_start_is_retried_on_a_later_poll(self):
        start = Recorder(result=None)
        preview, clock = make(project(), start=start)
        self.assertFalse(preview.poll())
        clock.advance(1)
        start.result = 99
        self.assertTrue(preview.poll())
        self.assertEqual(len(start.calls), 2)

    def test_polls_inside_the_interval_do_nothing(self):
        root = project(page=False)
        start = Recorder()
        preview, clock = make(root, start=start)
        preview.poll()
        (root / 'index.html').write_text('<html></html>')
        clock.advance(0.1)
        self.assertFalse(preview.poll())            # still inside the poll interval
        clock.advance(1)
        self.assertTrue(preview.poll())

    def test_the_switches_turn_it_off(self):
        for env in ({'WORKFLOW_PREVIEW_OPEN_BROWSER': '0'}, {'WORKFLOW_PREVIEW_OPEN_BROWSER': 'off'}):
            start = Recorder()
            preview, _ = make(project(), env=env, start=start)
            self.assertFalse(preview.poll(), env)
            self.assertEqual(start.calls, [], env)


class FinishedApp(unittest.TestCase):
    def test_a_finished_application_is_served_and_opened_with_a_lifetime(self):
        start = Recorder(result=4242)
        preview, _ = make(project(state='COMPLETE'), start=start)
        lines = preview.finish()
        self.assertEqual(start.calls, [hp.DEFAULT_TTL_SECONDS])
        self.assertEqual(len(lines), 1)
        self.assertIn('pid 4242', lines[0])
        self.assertIn('kill 4242', lines[0])
        self.assertIn('60 minutes', lines[0])

    def test_the_lifetime_is_not_configurable(self):
        start = Recorder()
        preview, _ = make(project(), env={'UNCLE_NOUI_PREVIEW_SECONDS': '600'}, start=start)
        preview.finish()
        self.assertEqual(start.calls, [hp.DEFAULT_TTL_SECONDS])

    def test_a_change_request_is_not_opened_when_it_finishes(self):
        start = Recorder()
        preview, _ = make(project(family='change'), start=start)
        self.assertEqual(preview.finish(), [])
        self.assertEqual(start.calls, [])

    def test_a_desktop_application_is_launched_not_browsed(self):
        start = Recorder()
        root = project(package={'name': 'x', 'dependencies': {'electron': '^30'}, 'scripts': {'start': 'electron .'}})
        preview, _ = make(root, start=start)
        self.assertEqual(preview.finish(), [])
        self.assertEqual(start.calls, [])

    def test_nothing_to_show_opens_nothing(self):
        start = Recorder()
        preview, _ = make(project(page=False), start=start)
        self.assertEqual(preview.finish(), [])
        self.assertEqual(start.calls, [])

    def test_a_server_already_running_is_left_alone(self):
        root = project()
        (root / '.uncle' / 'workflow' / 'preview-server.pid').write_text(str(os.getpid()))
        start = Recorder()
        preview, _ = make(root, start=start)
        self.assertEqual(preview.finish(), [])
        self.assertEqual(start.calls, [])

    def test_a_start_that_fails_says_so_instead_of_staying_silent(self):
        preview, _ = make(project(), start=Recorder(result=None))
        self.assertIn('could not start a preview server', preview.finish()[0])

    def test_a_server_that_never_reports_an_address_points_at_its_log(self):
        preview, _ = make(project(), wait=lambda: False)
        self.assertIn('preview-server.log', preview.finish()[0])

    def test_the_switches_turn_it_off(self):
        start = Recorder()
        preview, _ = make(project(), env={'WORKFLOW_PREVIEW_OPEN_BROWSER': '0'}, start=start)
        self.assertEqual(preview.finish(), [])
        self.assertEqual(start.calls, [])


DRIVER = r"""
import os, sys, time
root = sys.argv[1]
wf = os.path.join(root, '.uncle', 'workflow')
os.makedirs(wf, exist_ok=True)
mode = sys.argv[2]
open(os.path.join(wf, 'family'), 'w').write(sys.argv[3] + '\n')
open(os.path.join(wf, 'state'), 'w').write('IMPLEMENT\n')
if mode != 'nopage':
    open(os.path.join(root, 'index.html'), 'w').write('<html><body>the page</body></html>\n')
time.sleep(float(sys.argv[4]))
# The real driver's exit trap stops whatever preview server is recorded in its state directory.
if len(sys.argv) > 5 and sys.argv[5] == 'stop':
    import subprocess
    subprocess.run([sys.executable, sys.argv[6], 'stop', wf])
if mode == 'complete':
    open(os.path.join(wf, 'state'), 'w').write('COMPLETE\n')
    print('Workflow complete.')
sys.stdout.flush()
"""


class EndToEnd(unittest.TestCase):
    """The real headless runner, a fake driver, the real preview server, a recorder for the browser."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'proj'
        self.root.mkdir()
        self.opened = Path(self.tmp.name) / 'opened.txt'
        recorder = Path(self.tmp.name) / 'rec.sh'
        recorder.write_text('#!/bin/sh\necho "$1" >> "%s"\nexit 0\n' % self.opened)
        recorder.chmod(recorder.stat().st_mode | stat.S_IEXEC)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ('WORKFLOW_PREVIEW_OPEN_BROWSER', 'UNCLE_PREVIEW_TTL_SECONDS')}
        self.env.update(BROWSER=str(recorder), UNCLE_SKIP_UPGRADE='1')
        self.addCleanup(self.stop_servers)

    def stop_servers(self):
        state = self.root / '.uncle' / 'workflow'
        try:
            os.kill(int((state / 'preview-server.pid').read_text()), signal.SIGTERM)
        except (OSError, ValueError):
            pass

    def run_driver(self, mode, family='app', seconds=0.3, stop=True):
        out, err = io.StringIO(), io.StringIO()
        extra = ['stop', str(LIB / 'preview_server.py')] if stop else []
        code = H.run([sys.executable, '-c', DRIVER, str(self.root), mode, family, str(seconds), *extra], str(self.root),
                     env=self.env, out=out, err=err, install_signals=False)
        return code, out.getvalue(), err.getvalue()

    def opened_urls(self):
        try:
            return [u for u in self.opened.read_text().split() if u]
        except OSError:
            return []

    def test_a_completed_application_build_opens_the_finished_app(self):
        code, out, err = self.run_driver('complete')
        self.assertEqual(code, 0, out + err)
        urls = self.opened_urls()
        self.assertTrue(urls, 'the recorder (the browser) was never given a URL\n' + out + err)
        self.assertRegex(urls[-1], r'^http://127\.0\.0\.1:\d+/')
        self.assertRegex(out, r'Local preview: http://127\.0\.0\.1:\d+/')
        self.assertRegex(out, r'Local preview: the server \(pid \d+\) keeps running for 60 minutes; stop it earlier with: kill \d+')

    def test_the_server_it_leaves_running_serves_the_page(self):
        code, out, _ = self.run_driver('complete')
        self.assertEqual(code, 0)
        self.assertTrue((self.root / '.uncle' / 'workflow' / 'preview-server.pid').exists())
        url = self.opened_urls()[-1]
        from urllib.request import urlopen
        self.assertIn('the page', urlopen(url, timeout=5).read().decode())

    def test_an_early_page_opens_while_the_driver_is_still_running(self):
        code, out, err = self.run_driver('incomplete', seconds=2.5)
        urls = self.opened_urls()
        self.assertEqual(len(urls), 1, 'expected exactly one tab\n%s\n%s' % (out, err))

    def test_a_driver_that_did_not_complete_opens_no_finished_app(self):
        code, out, _ = self.run_driver('nopage', seconds=0.3)
        self.assertEqual(self.opened_urls(), [])
        self.assertNotIn('keeps running', out)

    def test_an_early_server_left_by_a_driver_that_did_not_stop_it_is_not_duplicated_at_the_end(self):
        code, out, _ = self.run_driver('complete', seconds=1.5, stop=False)
        self.assertEqual(len(self.opened_urls()), 1)
        self.assertNotIn('keeps running', out)

    def test_a_change_request_run_opens_nothing(self):
        code, out, _ = self.run_driver('complete', family='change')
        self.assertEqual(code, 0)
        self.assertEqual(self.opened_urls(), [])

    def test_with_the_switch_off_nothing_opens(self):
        self.env['WORKFLOW_PREVIEW_OPEN_BROWSER'] = '0'
        code, out, _ = self.run_driver('complete')
        self.assertEqual(code, 0)
        self.assertEqual(self.opened_urls(), [])

    def test_a_failed_driver_opens_no_finished_app(self):
        out, err = io.StringIO(), io.StringIO()
        script = DRIVER + "\nsys.exit(1)\n"
        code = H.run([sys.executable, '-c', script, str(self.root), 'complete', 'app', '0.2', 'stop', str(LIB / 'preview_server.py')],
                     str(self.root), env=self.env, out=out, err=err, install_signals=False)
        self.assertNotEqual(code, 0)
        self.assertNotIn('keeps running', out.getvalue())     # an early page may have opened; the finished app must not


if __name__ == '__main__':
    unittest.main()
