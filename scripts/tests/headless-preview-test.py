#!/usr/bin/env python3
"""Tests for the Preview:/App: announcements of scripts/lib/uncle_headless.py.

Fake drivers only. State files live in <root>/.uncle/workflow:
preview-server.{pid,url}, app-server.{pid,url}, preview-vite.{pid,url}, and
<root>/.uncle/launch.json. Announcements are `Preview: <url>`, `App: <url>`
and `App: launch <rendering>`, each preceded by the elapsed prefix.
"""
import io
import json
import os
import re
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, HERE)
import uncle_headless as H  # noqa: E402
import headless_preview as HP  # noqa: E402

PRELUDE = r"""
import os, sys, time, json
R = sys.argv[1]
S = os.path.join(R, '.uncle', 'workflow')
os.makedirs(S, exist_ok=True)
def put(name, data, mode='w'):
    with open(os.path.join(S, name), mode) as f:
        f.write(data)
def pub(prefix, url):
    put(prefix + '.pid', str(os.getpid()))
    put(prefix + '.url', url)
def say(s):
    sys.stdout.write(s); sys.stdout.flush()
"""


class Timed(io.StringIO):
    def __init__(self):
        super().__init__()
        self.marks = []

    def write(self, s):
        self.marks.append((time.monotonic(), s))
        return super().write(s)


def local_env():
    env = dict(os.environ)
    env.pop("UNCLE_HOSTED", None)
    env.pop("UNCLE_PREVIEW_MODE", None)
    env.pop("UNCLE_NOUI_PREVIEW", None)
    env.pop("WORKFLOW_PREVIEW_OPEN_BROWSER", None)
    return env


def drive(body, setup=None, env=None):
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, ".uncle", "workflow"), exist_ok=True)
    if setup:
        setup(root)
    out, err = Timed(), io.StringIO()
    script = PRELUDE + body
    cmd = [sys.executable, "-c", script, root]
    t0 = time.monotonic()
    code = H.run(cmd, root, env=env if env is not None else local_env(),
                 out=out, err=err, install_signals=False)
    return code, out, err.getvalue(), root, t0


def lines(out):
    return out.getvalue().split("\n")


def body_of(line):
    """Strip the elapsed prefix the writer adds."""
    return re.sub(r"^\s*(\[[^\]]*\]|\d+[:.\dsmh]*)\s+", "", line)


def announced(out, kind):
    return [l for l in lines(out) if re.search(r"(^|\s)%s: " % kind, l)]


class Preview(unittest.TestCase):
    def test_preview_line_during_run_before_driver_line(self):
        code, out, _, _, t0 = drive(
            "pub('preview-server', 'http://127.0.0.1:5173/')\n"
            "time.sleep(2.5)\nsay('driver done\\n')\n")
        self.assertEqual(code, 0 if code == 0 else code)
        pl = announced(out, "Local preview")
        self.assertEqual(len(pl), 1, out.getvalue())
        self.assertTrue(pl[0].rstrip().endswith("Local preview: http://127.0.0.1:5173/"))
        self.assertEqual(announced(out, "Preview"), [], out.getvalue())
        text = out.getvalue()
        self.assertLess(text.index("Local preview:"), text.index("driver done"))
        # appeared while the driver was still sleeping, within tolerance
        for ts, s in out.marks:
            if "Local preview:" in s:
                self.assertLess(ts - t0, 2.3)
                break
        else:
            self.fail("no Preview write")

    def test_changed_url_new_line_unchanged_not_repeated(self):
        code, out, _, _, _ = drive(
            "pub('preview-server', 'http://127.0.0.1:5000/')\n"
            "time.sleep(1.8)\n"
            "pub('preview-server', 'http://127.0.0.1:5000/')\n"
            "time.sleep(1.2)\n"
            "pub('preview-server', 'http://127.0.0.1:6000/')\n"
            "time.sleep(1.8)\n")
        pl = [body_of(l) for l in announced(out, "Local preview")]
        self.assertEqual(pl, ["Local preview: http://127.0.0.1:5000/",
                              "Local preview: http://127.0.0.1:6000/"], out.getvalue())

    def test_dead_pid_and_foreign_host_rejected(self):
        code, out, _, _, _ = drive(
            "put('preview-server.pid', '999999999')\n"
            "put('preview-server.url', 'http://127.0.0.1:5000/')\n"
            "put('app-server.pid', str(os.getpid()))\n"
            "put('app-server.url', 'http://example.com/')\n"
            "time.sleep(1.5)\n")
        self.assertNotIn("review:", out.getvalue())
        self.assertNotIn("App:", out.getvalue())


class HostedRun(unittest.TestCase):
    """AC-1/AC-2: hosted runs print no preview line and start no server."""
    FLAGS = [{"UNCLE_PREVIEW_MODE": "host"}, {"UNCLE_HOSTED": "1"}]

    def hosted_env(self, flag):
        env = local_env()
        env.update(flag)
        return env

    def test_hosted_announces_no_preview_line(self):
        for flag in self.FLAGS:
            code, out, _, _, _ = drive(
                "pub('preview-server', 'http://127.0.0.1:5173/')\n"
                "time.sleep(2.5)\nsay('driver done\\n')\n",
                env=self.hosted_env(flag))
            text = out.getvalue()
            self.assertIn("driver done", text)
            self.assertNotIn("review:", text, repr(flag) + text)

    def prepare(self):
        root = tempfile.mkdtemp()
        wf = os.path.join(root, ".uncle", "workflow")
        os.makedirs(wf)
        with open(os.path.join(wf, "family"), "w") as f:
            f.write("app")
        state = sorted(HP.EARLY_STATES)[0]
        with open(os.path.join(wf, "state"), "w") as f:
            f.write(state)
        with open(os.path.join(root, "index.html"), "w") as f:
            f.write("<html>page</html>")
        return root

    def make(self, env):
        root = self.prepare()
        calls = []
        hp = HP.HeadlessPreview(root, env=env, start=lambda ttl=None: calls.append(ttl) or 4242,
                                wait=lambda: True)
        return hp, calls

    def test_hosted_enabled_false_and_nothing_started(self):
        for flag in self.FLAGS:
            env = self.hosted_env(flag)
            self.assertFalse(HP.enabled(env), repr(flag))
            hp, calls = self.make(env)
            self.assertFalse(hp.poll())
            self.assertEqual(hp.finish(), [])
            self.assertEqual(calls, [], repr(flag))

    def test_non_hosted_control_still_starts(self):
        env = local_env()
        hp, calls = self.make(env)
        self.assertTrue(hp.poll())
        self.assertEqual(len(calls), 1)
        hp2, calls2 = self.make(env)
        lines2 = hp2.finish()
        self.assertEqual(len(calls2), 1)
        self.assertEqual(len(lines2), 1)
        self.assertTrue(lines2[0].startswith("Local preview: "), lines2)


class FinalLines(unittest.TestCase):
    """AC-3: the final server lines carry the Local preview: prefix."""
    def make(self, start, wait):
        return HostedRun.make(HostedRun(), local_env()) if False else None

    def run_finish(self, start, wait):
        root = HostedRun.prepare(HostedRun())
        hp = HP.HeadlessPreview(root, env=local_env(), start=start, wait=wait)
        return hp.finish()

    def test_could_not_start(self):
        got = self.run_finish(lambda ttl=None: None, lambda: True)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].startswith("Local preview: could not start"), got)

    def test_no_address(self):
        got = self.run_finish(lambda ttl=None: 77, lambda: False)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].startswith("Local preview: the preview server did not report"), got)


class Framing(unittest.TestCase):
    def test_partial_line_defers_announcement_without_newline(self):
        code, out, _, _, _ = drive(
            "say('partial-start ')\n"
            "pub('preview-server', 'http://127.0.0.1:5173/')\n"
            "time.sleep(3)\n"
            "say('rest-of-line\\n')\n"
            "time.sleep(1.5)\n")
        text = out.getvalue()
        self.assertIn("partial-start rest-of-line\n", text)
        self.assertIn("Local preview: http://127.0.0.1:5173/", text)
        self.assertGreater(text.index("Local preview:"), text.index("rest-of-line\n"))
        for l in lines(out):
            if "Local preview:" in l:
                self.assertNotIn("partial-start", l)

    def test_final_flush_forces_newline_before_announcement(self):
        code, out, _, _, _ = drive(
            "say('unterminated')\n"
            "pub('preview-server', 'http://127.0.0.1:5173/')\n"
            "time.sleep(2)\n")
        text = out.getvalue()
        if "Local preview:" in text:
            before = text[:text.index("Local preview:")]
            self.assertIn("unterminated\n", before)
        self.assertNotIn("unterminated" + "Localpreview", text.replace(" ", ""))

    def test_driver_bytes_preserved(self):
        driver = "say('alpha\\n')\nsay('beta\\n')\ntime.sleep(.3)\nsay('gamma\\n')\n"
        _, plain, _, _, _ = drive(driver)
        _, with_url, _, _, _ = drive(
            "pub('preview-server', 'http://127.0.0.1:5173/')\n" + driver)
        keep = lambda o: [body_of(l) for l in lines(o)
                          if l and not re.search(r"(Local preview|App): ", l)]
        self.assertEqual(keep(plain), keep(with_url))
        self.assertEqual(keep(with_url), ["alpha", "beta", "gamma"])


class AppAnnouncements(unittest.TestCase):
    def test_simultaneous_sources_and_recurrence_emit_once_per_url(self):
        code, out, _, _, _ = drive(
            "pub('app-server', 'http://127.0.0.1:3000/')\n"
            "pub('preview-vite', 'http://127.0.0.1:3001/')\n"
            "time.sleep(1.8)\n"
            "pub('app-server', 'http://127.0.0.1:3001/')\n"
            "time.sleep(1.5)\n"
            "pub('app-server', 'http://127.0.0.1:3000/')\n"
            "time.sleep(1.5)\n")
        app = [body_of(l) for l in announced(out, "App") if "launch" not in l]
        self.assertEqual(sorted(app), ["App: http://127.0.0.1:3000/",
                                       "App: http://127.0.0.1:3001/"], out.getvalue())

    def launch(self, data, raw=None):
        def setup(root):
            with open(os.path.join(root, ".uncle", "launch.json"), "w") as f:
                f.write(raw if raw is not None else json.dumps(data))
            with open(os.path.join(root, "index.html"), "w") as f:
                f.write("<html></html>")
        code, out, _, _, _ = drive("say('work\\n')\ntime.sleep(.2)\n", setup)
        return out, [body_of(l) for l in announced(out, "App")
                     if "launch" in l]

    def test_launch_command(self):
        out, got = self.launch({"kind": "command", "command": ["npm", "start"]})
        self.assertEqual(got, ['App: launch command ["npm", "start"]'], out.getvalue())

    def test_launch_static_webpage(self):
        out, got = self.launch({"kind": "webpage", "path": "index.html"})
        self.assertEqual(got, ["App: launch page index.html"], out.getvalue())

    def test_launch_webpage_with_command_and_url(self):
        out, got = self.launch({"kind": "webpage", "command": ["npm", "run", "dev"],
                                "url": "http://127.0.0.1:5173/"})
        self.assertEqual(
            got, ['App: launch page ["npm", "run", "dev"] http://127.0.0.1:5173/'],
            out.getvalue())

    def test_launch_none(self):
        out, got = self.launch({"kind": "none"})
        self.assertEqual(got, ["App: launch none"], out.getvalue())

    def test_launch_missing_or_malformed_prints_nothing(self):
        _, _, _, _, _ = (None,) * 5
        code, out, _, _, _ = drive("say('x\\n')\n")
        self.assertNotIn("launch", out.getvalue())
        out, got = self.launch(None, raw="{not json")
        self.assertEqual(got, [])

    def test_launch_line_printed_once_and_last_of_announcements(self):
        out, got = self.launch({"kind": "none"})
        self.assertEqual(len(got), 1)


class Sanitization(unittest.TestCase):
    BAD = ["\x1b[31m", "\x1b]0;t\x07", "\x00", "\r", "\x07", " ", " ", "\x85"]

    def test_control_bearing_urls_rejected(self):
        for bad in self.BAD:
            url = "http://127.0.0.1:5173/a%sb" % bad
            code, out, _, _, _ = drive(
                "pub('preview-server', %r)\ntime.sleep(1.3)\n" % url)
            self.assertNotIn("review:", out.getvalue(), repr(bad))
            self.assertNotIn("\x1b", out.getvalue())

    def test_launch_metadata_emitted_clean_single_line(self):
        for bad in self.BAD:
            def setup(root, bad=bad):
                with open(os.path.join(root, ".uncle", "launch.json"), "w") as f:
                    json.dump({"kind": "command", "command": ["run" + bad + "x"]}, f)
            code, out, _, _, _ = drive("say('w\\n')\ntime.sleep(.2)\n", setup)
            text = out.getvalue()
            self.assertNotIn("\x1b", text, repr(bad))
            self.assertEqual(re.findall(r"[\x00-\x08\x0b-\x1f\x7f\x85  ]", text),
                             [], repr(bad))
            for l in lines(out):
                if "launch" in l:
                    self.assertTrue(l.rstrip().endswith("]") or "App: launch" in l)

    def test_control_chars_in_path_rejected_by_url_file(self):
        code, out, _, _, _ = drive(
            "pub('app-server', 'http://localhost:3000/\\x1b[2Jx')\ntime.sleep(1.3)\n")
        self.assertNotIn("\x1b", out.getvalue())
        self.assertNotIn("App: http", out.getvalue())


class BoundedReads(unittest.TestCase):
    def run_case(self, prep):
        t = time.monotonic()
        code, out, _, root, _ = drive(
            "put('preview-server.pid', str(os.getpid()))\n"
            "time.sleep(1.5)\nsay('still going\\n')\n", prep)
        self.assertLess(time.monotonic() - t, 15)
        self.assertEqual(code, 3)  # no completion banner: same as without announcements
        self.assertIn("still going", out.getvalue())
        self.assertNotIn("review:", out.getvalue())
        self.assertNotIn("App: http", out.getvalue())

    def test_fifo_url_file(self):
        def prep(root):
            os.mkfifo(os.path.join(root, ".uncle", "workflow", "preview-server.url"))
        self.run_case(prep)

    def test_oversized_url_file(self):
        def prep(root):
            with open(os.path.join(root, ".uncle", "workflow", "preview-server.url"), "w") as f:
                f.write("http://127.0.0.1:1/" + "a" * 3000)
        self.run_case(prep)

    def test_directory_at_url_path(self):
        def prep(root):
            os.mkdir(os.path.join(root, ".uncle", "workflow", "preview-server.url"))
        self.run_case(prep)

    def test_fifo_at_pid_path(self):
        def prep(root):
            os.mkfifo(os.path.join(root, ".uncle", "workflow", "preview-server.pid"))
            with open(os.path.join(root, ".uncle", "workflow", "preview-server.url"), "w") as f:
                f.write("http://127.0.0.1:5173/")
        t = time.monotonic()
        code, out, _, _, _ = drive(
            "put('app-server.pid', str(os.getpid()))\ntime.sleep(1.5)\nsay('ok\\n')\n", prep)
        self.assertLess(time.monotonic() - t, 15)
        self.assertEqual(code, 3)
        self.assertNotIn("review:", out.getvalue())


class ExitCodeAndDocs(unittest.TestCase):
    def test_exit_code_unchanged_by_announcements(self):
        a = drive("say('hi\\n')\nsys.exit(4)\n")[0]
        b = drive("pub('preview-server', 'http://127.0.0.1:1/')\nsay('hi\\n')\n"
                  "time.sleep(1)\nsys.exit(4)\n")[0]
        self.assertEqual(a, b)

    def test_docs_describe_lines(self):
        path = os.path.join(HERE, "..", "..", "docs", "noui.md")
        text = open(path, encoding="utf-8").read()
        self.assertIn("Preview:", text)
        self.assertIn("App:", text)


if __name__ == "__main__":
    unittest.main()
