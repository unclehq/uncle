#!/usr/bin/env python3
"""Tests for scripts/lib/uncle_headless.py using fake drivers only."""
import io
import os
import re
import signal
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, HERE)
import uncle_headless as H  # noqa: E402
from pty_helper import with_pty_stdin  # noqa: E402

BANNER = H.COMPLETION_BANNERS[0]


def drive(script, **kw):
    out, err = io.StringIO(), io.StringIO()
    root = tempfile.mkdtemp()
    code = H.run([sys.executable, "-c", script], root, out=out, err=err,
                 install_signals=kw.pop("install_signals", False), **kw)
    return code, out.getvalue(), err.getvalue(), root


class Filter(unittest.TestCase):
    def run_filter(self, chunks):
        f = H.EscapeFilter()
        return "".join(f.feed(c) for c in chunks)

    def assert_clean(self, s):
        self.assertNotIn("\x1b", s)
        self.assertEqual(re.findall(r"[^\x20-\x7e\t\n\u00a0-\U0010ffff]", s), [])

    def test_sequences_removed(self):
        raw = (b"a\x1b[31mred\x1b[0m\x1b[2J\x1b[?1049hb\x1b]0;title\x07c"
               b"\x1bP1;2qdata\x1b\\d\x1b_apc\x1b\\e\x1bZf\xc2\x85g\x08h\x00i\x7fj\n")
        out = self.run_filter([raw])
        self.assertEqual(out, "aredbcdefghij\n")
        self.assert_clean(out)

    def test_split_chunks(self):
        raw = b"x\x1b[1;3" + b"1mY\x1b]0;ti" + b"tle\x1b" + b"\\Z\n"
        for i in range(1, len(raw)):
            out = self.run_filter([raw[:i], raw[i:]])
            self.assertEqual(out, "xYZ\n", i)

    def test_cr_becomes_newline(self):
        self.assertEqual(self.run_filter([b"a\rb\r\nc\n"]), "a\nb\nc\n")

    def test_tab_kept(self):
        self.assertEqual(self.run_filter([b"a\tb"]), "a\tb")

    def test_defect_injection_unfiltered_would_fail(self):
        # a pass-through "filter" must be rejected by our own cleanliness check
        with self.assertRaises(AssertionError):
            self.assert_clean("\x1b[31mred")


class ExitCodes(unittest.TestCase):
    def test_precedence_table(self):
        c = H.classify_exit
        for rc, sig, done, want in [
            (0, 0, True, 0), (0, 0, False, 3), (2, 0, True, 1), (3, 0, False, 1),
            (7, 0, True, 1), (255, 0, False, 1), (-15, 15, False, 143),
            (-2, 2, True, 130), (0, 15, True, 143), (5, 2, False, 130),
            (-9, 0, False, 137), (-15, 0, False, 143),
        ]:
            self.assertEqual(c(rc, sig, done), want, (rc, sig, done))

    def test_gate_named_on_stderr(self):
        code, out, err, _ = drive("print('Human gate: PROJECT_PLAN.md awaiting approval')")
        self.assertEqual(code, 3)
        self.assertIn("PROJECT_PLAN.md awaiting approval", err)
        code, out, err, _ = drive("print('nothing special')")
        self.assertNotIn("stopped at:", err)

    def test_fake_drivers(self):
        code, out, err, _ = drive("print(%r)" % BANNER)
        self.assertEqual(code, 0)
        code, out, err, _ = drive("print('stopped at gate')")
        self.assertEqual(code, 3)
        self.assertIn("exit 3", err)
        for n in (2, 3, 7, 255):
            code, out, err, _ = drive("import sys; print(%r); sys.exit(%d)" % (BANNER, n))
            self.assertEqual(code, 1, n)
            self.assertIn("status %d" % n, err)
        code, *_ = drive("import os,signal; os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(code, 143)
        code, *_ = drive("import os,signal; os.kill(os.getpid(), signal.SIGKILL)")
        self.assertEqual(code, 137)


class Output(unittest.TestCase):
    def test_no_escapes_and_prefix_once(self):
        code, out, err, _ = drive(
            "import sys,time\n"
            "sys.stdout.write('one\\x1b[31m red\\x1b[0m\\rtwo\\n'); sys.stdout.flush()\n"
            "sys.stdout.write('\\x1b[2'); sys.stdout.flush(); time.sleep(.1)\n"
            "sys.stdout.write('Jthree\\n')\n")
        self.assertNotIn("\x1b", out)
        lines = [l for l in out.splitlines() if l]
        self.assertTrue(all(re.match(r"\[\+\d\d:\d\d:\d\d\] ", l) for l in lines), lines)
        for l in lines:
            self.assertEqual(len(re.findall(r"\[\+\d\d:\d\d:\d\d\]", l)), 1, l)
        self.assertIn("one red", out)
        self.assertIn("three", out)

    def test_partial_line_flushed(self):
        code, out, err, _ = drive(
            "import sys; sys.stdout.write('Proceed? '); sys.stdout.flush()")
        self.assertIn("Proceed? ", out)

    def test_finished_lines_summary(self):
        code, out, err, _ = drive(
            "print('Finished build: verdict=READY skipped=0 path=/x'); print('Total time: 1s'); print(%r)" % BANNER)
        self.assertEqual(code, 0)
        tail = out.strip().splitlines()[-2:]
        self.assertEqual(tail, ["Finished build: verdict=READY skipped=0 path=/x", "Total time: 1s"])

    def test_redaction(self):
        os.environ["UNCLE_TEST_SIGNING_KEY"] = "s3cr3t-key-material"
        try:
            code, out, err, _ = drive("print('key is s3cr3t-key-material')", env=dict(os.environ))
        finally:
            del os.environ["UNCLE_TEST_SIGNING_KEY"]
        self.assertNotIn("s3cr3t-key-material", out)
        self.assertIn("[REDACTED]", out)

    def test_no_color_set(self):
        code, out, err, _ = drive("import os; print('NC=' + os.environ.get('NO_COLOR',''))")
        self.assertIn("NC=1", out)


SECRET = "s3cr3t-key-material"


def drive_env(script, **kw):
    os.environ["UNCLE_TEST_SIGNING_KEY"] = SECRET
    try:
        return drive(script, env=dict(os.environ), **kw)
    finally:
        del os.environ["UNCLE_TEST_SIGNING_KEY"]


class Stderr(unittest.TestCase):
    """AC-1..3: driver stderr is surfaced on stderr, not on stdout."""

    def test_stderr_goes_to_err_not_out(self):
        code, out, err, _ = drive(
            "import sys; sys.stderr.write('boom-on-stderr\\n'); print(%r)" % BANNER)
        self.assertIn("boom-on-stderr", err)
        self.assertNotIn("boom-on-stderr", out)
        self.assertEqual(code, 0)

    def test_banner_like_stderr_text_stays_off_stdout(self):
        code, out, err, _ = drive(
            "import sys; sys.stderr.write(%r + '\\n')" % BANNER)
        self.assertIn(BANNER, err)
        self.assertNotIn(BANNER, out)

    def test_stdout_gate_with_stderr_noise(self):
        code, out, err, _ = drive(
            "import sys\nsys.stderr.write('noise\\n'); sys.stderr.flush()\n"
            "print('Human gate: PROJECT_PLAN.md awaiting approval')")
        self.assertEqual(code, 3)
        self.assertIn("PROJECT_PLAN.md awaiting approval", err)
        self.assertNotIn("noise", out)

    def test_gate_like_stderr_does_not_trigger_gate(self):
        code, out, err, _ = drive(
            "import sys\nsys.stderr.write('Human gate: X.md awaiting approval\\n')\n"
            "print(%r)" % BANNER)
        self.assertEqual(code, 0)
        self.assertNotIn("stopped at:", err)
        self.assertIn("Human gate: X.md awaiting approval", err)
        self.assertNotIn("Human gate", out)

    def test_failure_text_once_plus_status_line(self):
        code, out, err, _ = drive(
            "import sys; sys.stderr.write('driver-error-xyz\\n'); sys.exit(7)")
        self.assertEqual(code, 1)
        self.assertEqual(err.count("driver-error-xyz"), 1, err)
        self.assertIn("status 7", err)
        self.assertNotIn("driver-error-xyz", out)
        self.assertNotIn("status 7", out)

    def test_late_stderr_drained_before_status_line(self):
        code, out, err, _ = drive(
            "import sys,time\nsys.stderr.write('late-err\\n'); sys.stderr.flush()\nsys.exit(4)")
        self.assertIn("late-err", err)
        self.assertLess(err.index("late-err"), err.index("status 4"))

    def test_stderr_redacted(self):
        code, out, err, _ = drive_env(
            "import sys; sys.stderr.write('k=%s\\n'); print(%r)" % (SECRET, BANNER))
        self.assertNotIn(SECRET, err)
        self.assertIn("[REDACTED]", err)

    def test_secret_split_across_chunks_redacted(self):
        code, out, err, _ = drive_env(
            "import sys,time\nsys.stderr.write('k=s3cr3t-'); sys.stderr.flush()\n"
            "time.sleep(.05)\nsys.stderr.write('key-material\\n'); sys.stderr.flush()\n"
            "print(%r)" % BANNER)
        self.assertNotIn(SECRET, err)
        self.assertNotIn("s3cr3t-", err)
        self.assertIn("[REDACTED]", err)

    def test_partial_last_line_redacted_at_eof(self):
        code, out, err, _ = drive_env(
            "import sys; sys.stderr.write('tail %s'); sys.stderr.flush(); print(%r)" % (SECRET, BANNER))
        self.assertNotIn(SECRET, err)
        self.assertIn("tail", err)

    def test_invalid_utf8_becomes_replacement(self):
        code, out, err, _ = drive(
            "import sys; sys.stderr.buffer.write(b'bad\\xff\\xfeok\\n'); sys.stderr.flush()")
        self.assertIn("�", err)
        self.assertIn("ok", err)

    def test_escapes_filtered_on_stderr(self):
        code, out, err, _ = drive(
            "import sys; sys.stderr.write('a\\x1b[31mred\\x1b[0m\\n')")
        self.assertNotIn("\x1b", err)
        self.assertIn("ared", err)

    def test_stderr_escape_state_does_not_leak_to_stdout(self):
        code, out, err, _ = drive(
            "import sys,time\nsys.stderr.write('x\\x1b[3'); sys.stderr.flush(); time.sleep(.05)\n"
            "print('stdout-visible'); sys.stdout.flush(); time.sleep(.05)\n"
            "sys.stderr.write('1mdone\\n')")
        self.assertIn("stdout-visible", out)
        self.assertNotIn("\x1b", out + err)
        self.assertNotIn("1mdone", out + err)
        self.assertIn("done", err)
        self.assertNotIn("done", out)
        self.assertIn("x", err)

    def test_overlong_line_is_capped(self):
        code, out, err, _ = drive(
            "import sys; sys.stderr.write('A'*30000 + '\\n'); sys.exit(2)")
        longest = max((len(l) for l in err.splitlines()), default=0)
        self.assertGreater(longest, 1000)
        self.assertLessEqual(longest, 8192 + 64, longest)
        self.assertIn("…[truncated]", err)
        self.assertEqual(err.count("…[truncated]"), 1)

    def test_overlong_line_retained_text_has_no_secret(self):
        code, out, err, _ = drive_env(
            "import sys; sys.stderr.write('A'*9000 + '%s' + 'B'*20000 + '\\n'); sys.exit(2)" % SECRET)
        self.assertNotIn(SECRET, err)
        self.assertNotIn("s3cr3t", err)
        self.assertIn("…[truncated]", err)

    def test_each_stderr_line_once_then_one_status_line(self):
        code, out, err, _ = drive(
            "import sys\nfor i in range(3): sys.stderr.write('uniq-%d\\n' % i)\n"
            "sys.stderr.flush(); sys.exit(5)")
        for i in range(3):
            self.assertEqual(err.count("uniq-%d" % i), 1, err)
        self.assertEqual(err.count("driver exited with status 5"), 1, err)
        self.assertGreater(err.index("driver exited with status 5"), err.index("uniq-2"))
        self.assertEqual(out.count("uniq-"), 0)

    def test_stderr_only_driver(self):
        code, out, err, _ = drive(
            "import sys,time\nsys.stdout.close()\ntime.sleep(.2)\n"
            "sys.stderr.write('only-err\\n'); sys.exit(6)")
        self.assertEqual(code, 1)
        self.assertEqual(err.count("only-err"), 1, err)
        self.assertEqual(err.count("status 6"), 1, err)
        self.assertNotIn("only-err", out)

    def test_stdout_only_driver(self):
        code, out, err, _ = drive(
            "import sys,time\nsys.stderr.close()\ntime.sleep(.2)\nprint('only-out'); sys.exit(6)")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("only-out"), 1, out)
        self.assertEqual(err.count("status 6"), 1, err)
        self.assertNotIn("only-out", err)

    def test_stdout_before_stderr_both_drained(self):
        code, out, err, _ = drive(
            "import sys\nprint('first-out', flush=True)\n"
            "sys.stderr.write('second-err\\n'); sys.stderr.flush(); sys.exit(3)")
        self.assertEqual(out.count("first-out"), 1, out)
        self.assertEqual(err.count("second-err"), 1, err)
        self.assertLess(err.index("second-err"), err.index("status 3"))

    def test_signal_drains_pending_stderr(self):
        for sig, want in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            out, err = io.StringIO(), io.StringIO()
            timer = threading.Timer(0.8, os.kill, (os.getpid(), sig))
            timer.start()
            try:
                code = H.run([sys.executable, "-c",
                              "import sys,time\nsys.stderr.write('pending-err\\n'); sys.stderr.flush()\n"
                              "time.sleep(60)"], tempfile.mkdtemp(), out=out, err=err,
                             grace=2.0, install_signals=True)
            finally:
                timer.cancel()
            e = err.getvalue()
            self.assertEqual(code, want)
            self.assertEqual(e.count("pending-err"), 1, e)
            self.assertLessEqual(e.count("driver exited with status"), 1, e)
            self.assertNotIn("pending-err", out.getvalue())

    def test_defect_injection_merged_stderr_is_detected(self):
        # Real defect: driver stderr merged into stdout. Run the product code
        # with that defect and require the separation assertion to fail.
        orig = H.subprocess.Popen

        class Merged(orig):
            def __init__(self, *a, **k):
                k["stderr"] = H.subprocess.STDOUT
                super().__init__(*a, **k)
                self.stderr = open(os.devnull, "rb", buffering=0)
        H.subprocess.Popen = Merged
        try:
            code, out, err, _ = drive("import sys; sys.stderr.write('boom-on-stderr\\n')")
        finally:
            H.subprocess.Popen = orig
        with self.assertRaises(AssertionError):
            self.assertIn("boom-on-stderr", err)
        with self.assertRaises(AssertionError):
            self.assertNotIn("boom-on-stderr", out)

    def test_defect_injection_no_redaction_is_detected(self):
        orig = H.redact
        H.redact = lambda text, env: text
        try:
            code, out, err, _ = drive_env(
                "import sys,time\nsys.stderr.write('k=s3cr3t-'); sys.stderr.flush()\n"
                "time.sleep(.05)\nsys.stderr.write('key-material\\n'); sys.stderr.flush()\n"
                "sys.stderr.write('tail %s'); sys.stderr.flush()" % SECRET)
        finally:
            H.redact = orig
        with self.assertRaises(AssertionError):
            self.assertNotIn(SECRET, err)

    def test_stderr_prompt_flushed_without_splitting_stdout_partial(self):
        code, out, err, _ = drive(
            "import sys,time\nsys.stdout.write('OUT-PARTIAL '); sys.stdout.flush()\n"
            "time.sleep(.05)\nsys.stderr.write('ERR-PROMPT? '); sys.stderr.flush()\n"
            "time.sleep(1.5)\nsys.stdout.write('end\\n')")
        self.assertIn("ERR-PROMPT?", err)
        self.assertIn("OUT-PARTIAL end", out)

    def test_defect_injection_naive_chunk_redaction_leaks(self):
        # a redactor that works per raw chunk misses a split secret; the
        # assertions used above must be able to detect that.
        chunks = ["k=s3cr3t-", "key-material\n"]
        env = {"UNCLE_TEST_SIGNING_KEY": SECRET}
        naive = "".join(H.redact(c, env) for c in chunks)
        with self.assertRaises(AssertionError):
            self.assertNotIn(SECRET, naive)
        self.assertNotIn(SECRET, H.redact("".join(chunks), env))
        # and a stdout/stderr mix-up must be detected by the separation check
        with self.assertRaises(AssertionError):
            self.assertNotIn("boom", "[+00:00:00] boom")


class Attended(unittest.TestCase):
    def test_non_tty_refused(self):
        for opener in (lambda: os.open(os.devnull, os.O_RDONLY),
                       lambda: os.pipe()[0],
                       lambda: os.open(__file__, os.O_RDONLY)):
            fd = opener()
            out, err = io.StringIO(), io.StringIO()
            code = H.run([sys.executable, "-c", "print(1)"], tempfile.mkdtemp(),
                         attended=True, out=out, err=err, stdin_fd=fd, install_signals=False)
            os.close(fd)
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("terminal", err.getvalue())
        out, err = io.StringIO(), io.StringIO()
        code = H.run([sys.executable, "-c", "print(1)"], tempfile.mkdtemp(), attended=True,
                     out=out, err=err, stdin_fd=987, install_signals=False)
        self.assertEqual(code, 2)

    def test_pty_forwards_answers_and_eof(self):
        script = ("import sys\nsys.stdout.write('Q? '); sys.stdout.flush()\n"
                  "a=sys.stdin.readline(); print('got', repr(a))\n"
                  "b=sys.stdin.readline(); print('empty', repr(b))\n"
                  "c=sys.stdin.readline(); print('long', len(c))\n"
                  "d=sys.stdin.read(); print('eof', repr(d))\n"
                  "print(%r)" % BANNER)
        # a canonical-mode tty queue holds ~1024 bytes (MAX_INPUT); more would block the write
        long_line = b"x" * 800 + b"\n"

        def go(slave):
            out, err = io.StringIO(), io.StringIO()
            root = tempfile.mkdtemp()
            res = {}
            t = threading.Thread(target=lambda: res.setdefault("c", H.run(
                [sys.executable, "-c", script], root, attended=True, out=out, err=err,
                stdin_fd=slave, install_signals=False)))
            t.start()
            return t, res, out, err, root

        master_holder = {}
        master, slave = __import__("pty").openpty()
        try:
            os.write(master, b"yes\n\n")
            os.write(master, long_line)
            os.write(master, b"\x04")  # EOF (Ctrl-D) at line start
            t, res, out, err, root = go(slave)
            t.join(15)
            self.assertFalse(t.is_alive())
        finally:
            os.close(master)
            os.close(slave)
        text = out.getvalue()
        self.assertIn("got 'yes\\n'", text)
        self.assertIn("empty '\\n'", text)
        self.assertIn("long 801", text)
        self.assertIn("eof ''", text)
        self.assertEqual(res.get("c"), 0)
        import json
        rec = json.load(open(os.path.join(root, ".uncle", "workflow", "desktop-launch.json")))
        self.assertEqual(rec.get("reason"), "noui")
        self.assertEqual(rec.get("decision"), "skipped")


class DriverFromEnv(unittest.TestCase):
    """The launcher exports create_app/github_issue/change_request."""

    def _argv(self, action, text, runtime="/rt"):
        root = tempfile.mkdtemp()
        env = {"UNCLE_STARTUP_ACTION": action, "UNCLE_STARTUP_TEXT": text, "UNCLE_RUNTIME_ROOT": runtime}
        old = dict(os.environ)
        os.environ.update(env)
        try:
            err = io.StringIO()
            return H._driver_from_env(root, err), err.getvalue(), root
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_actions_map_to_the_tui_drivers(self):
        for action, script, tail in (("create_app", "stagegate.sh", []),
                                     ("github_issue", "from-issue.sh", ["12"]),
                                     ("change_request", "change-workflow.sh", [])):
            argv, err, root = self._argv(action, tail[0] if tail else "do a thing")
            self.assertEqual(argv, ["/rt/scripts/" + script] + tail, err)

    def test_seeds_inputs_in_project_root(self):
        _, _, root = self._argv("create_app", "a tiny app")
        self.assertTrue(os.path.isfile(os.path.join(root, ".uncle", "docs", "REQUIREMENTS.md")))
        _, _, root = self._argv("change_request", "fix it")
        with open(os.path.join(root, ".uncle", "docs", "CHANGE_REQUEST.md")) as fh:
            self.assertEqual(fh.read(), "fix it")

    def test_old_and_unknown_actions_refused(self):
        for bad in ("application", "", "../x"):
            argv, err, _ = self._argv(bad, "x")
            self.assertIsNone(argv)
            self.assertIn("UNCLE_STARTUP_ACTION", err)


class Signals(unittest.TestCase):
    def _alive_group(self, pgid):
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False

    def test_sigterm_ignored_driver_is_killed(self):
        script = ("import signal,time,os\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                  "print('ready', os.getpgid(0), flush=True)\ntime.sleep(60)")
        out, err = io.StringIO(), io.StringIO()
        res = {}
        old = signal.getsignal(signal.SIGTERM)

        def target():
            res["c"] = H.run([sys.executable, "-c", script], tempfile.mkdtemp(),
                             out=out, err=err, grace=1.0, install_signals=True)
        # signal handlers can only be installed from the main thread: run inline
        # with a timer that sends the signals to ourselves.
        t0 = time.monotonic()
        timers = [threading.Timer(0.8, os.kill, (os.getpid(), signal.SIGTERM)),
                  threading.Timer(1.0, os.kill, (os.getpid(), signal.SIGTERM)),
                  threading.Timer(1.2, os.kill, (os.getpid(), signal.SIGINT))]
        for t in timers:
            t.start()
        target()
        for t in timers:
            t.cancel()
        self.assertEqual(res["c"], 143)  # first signal sets the exit code
        # a second signal kills the group at once: well before 0.8s + 1.0s grace
        self.assertLess(time.monotonic() - t0, 1.7)
        pg = int(re.search(r"ready (\d+)", out.getvalue()).group(1))
        self.assertFalse(self._alive_group(pg))
        self.assertIs(signal.getsignal(signal.SIGTERM), old)

    def test_second_signal_kills_immediately(self):
        script = ("import signal,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                  "print('ready', flush=True)\ntime.sleep(60)")
        out, err = io.StringIO(), io.StringIO()
        t0 = time.monotonic()
        timers = [threading.Timer(0.8, os.kill, (os.getpid(), signal.SIGINT)),
                  threading.Timer(1.2, os.kill, (os.getpid(), signal.SIGINT))]
        for t in timers:
            t.start()
        code = H.run([sys.executable, "-c", script], tempfile.mkdtemp(), out=out, err=err,
                     grace=30.0, install_signals=True)
        for t in timers:
            t.cancel()
        self.assertEqual(code, 130)
        self.assertLess(time.monotonic() - t0, 5)  # grace is 30s: only escalation explains this

    def test_signal_before_spawn_spawns_nothing(self):
        marker = os.path.join(tempfile.mkdtemp(), "spawned")
        orig = H.signal.signal

        def fake_signal(s, h):
            r = orig(s, h)
            if s == signal.SIGTERM and callable(h):
                h(signal.SIGTERM, None)  # deliver right after installation
            return r
        H.signal.signal = fake_signal
        try:
            code = H.run([sys.executable, "-c", "open(%r,'w')" % marker], tempfile.mkdtemp(),
                         out=io.StringIO(), err=io.StringIO(), install_signals=True)
        finally:
            H.signal.signal = orig
        self.assertEqual(code, 143)
        self.assertFalse(os.path.exists(marker))

    def test_no_surviving_descendants(self):
        script = ("import subprocess,sys\n"
                  "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\n"
                  "print('child', p.pid, flush=True)")
        code, out, err, _ = drive(script)
        pid = int(re.search(r"child (\d+)", out).group(1))
        time.sleep(0.2)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
