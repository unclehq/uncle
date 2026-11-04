#!/usr/bin/env python3
"""Shell (bash under a pty) tests for terminal title behaviour: AC-4, AC-6, grep guard."""
import os
import pathlib
import pty
import re
import select
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "lib" / "terminal-title.sh"
BASH = "/bin/bash"
PUSH = b"\x1b[22;2t"
POP = b"\x1b[23;2t"
TITLE_RE = re.compile(rb"\x1b\]2;(.*?)(?:\x07|\x1b\\)", re.S)


def run_bash(script, env_extra=None, tty=True, path=None):
    """Run script in bash with stdout/stderr on a pty; return (bytes, rc)."""
    env = {"PATH": path if path is not None else os.environ["PATH"],
           "HOME": os.environ.get("HOME", "/tmp"), "TERM": "xterm-256color",
           "UNCLE_PROJECT_ROOT": "/tmp/shellproj"}
    env.update(env_extra or {})
    env = {k: v for k, v in env.items() if v is not None}
    full = 'source "%s"\n%s' % (LIB, script)
    if tty:
        master, slave = pty.openpty()
        proc = subprocess.Popen([BASH, "-c", full], env=env, stdin=slave,
                                stdout=slave, stderr=slave, cwd=str(ROOT))
        os.close(slave)
        out = b""
        while True:
            r, _, _ = select.select([master], [], [], 15)
            if not r:
                proc.kill()
                break
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        proc.wait()
        os.close(master)
        return out, proc.returncode
    p = subprocess.run([BASH, "-c", full], env=env, capture_output=True, cwd=str(ROOT))
    return p.stdout + p.stderr, p.returncode


def titles(b):
    return [t.decode() for t in TITLE_RE.findall(b)]


class ShellTitleTest(unittest.TestCase):
    def test_begin_end_with_issue(self):
        out, rc = run_bash("uncle_title_begin 12\nuncle_title_end")
        self.assertEqual(rc, 0)
        self.assertEqual(out.count(PUSH), 1)
        self.assertEqual(out.count(POP), 1)
        ts = titles(out)
        self.assertEqual(ts[0], "shellproj · uncle issue #12")
        self.assertEqual(ts[-1], "shellproj · uncle")
        self.assertLess(out.index(PUSH), out.index(b"issue #12"))
        # restore title written before the pop
        self.assertLess(out.rindex(b"shellproj \xc2\xb7 uncle"), out.index(POP))

    def test_begin_without_issue(self):
        out, _ = run_bash("uncle_title_begin\nuncle_title_end")
        self.assertEqual(titles(out)[0], "shellproj · uncle")
        self.assertEqual(out.count(PUSH), 1)

    def test_non_numeric_issue_ignored(self):
        for bad in ("12a", "--x", ""):
            out, _ = run_bash('uncle_title_begin "%s"\nuncle_title_end' % bad)
            self.assertEqual(titles(out)[0], "shellproj · uncle", bad)
            self.assertNotIn(b"#", out)

    def test_owner_set_writes_zero_bytes(self):
        owner = str(os.getpid())  # live ancestor of the bash child
        for script in ("uncle_title_begin 12\nuncle_title_end",
                       "uncle_title_begin\nuncle_title_end"):
            out, rc = run_bash(script, {"UNCLE_TITLE_OWNER": owner})
            self.assertEqual(rc, 0)
            self.assertEqual(out, b"")

    def test_forged_owner_ignored(self):
        for forged in ("999999999", "abc", "-1"):
            out, _ = run_bash("uncle_title_begin 3\nuncle_title_end",
                              {"UNCLE_TITLE_OWNER": forged})
            self.assertEqual(out.count(PUSH), 1, forged)
            self.assertEqual(out.count(POP), 1, forged)

    def test_end_without_begin_writes_nothing(self):
        out, _ = run_bash("uncle_title_end\nuncle_title_end")
        self.assertEqual(out, b"")

    def test_double_begin_double_end_balanced(self):
        out, _ = run_bash("uncle_title_begin 1\nuncle_title_begin 2\n"
                          "uncle_title_end\nuncle_title_end")
        self.assertEqual(out.count(PUSH), 1)
        self.assertEqual(out.count(POP), 1)

    def test_exit_trap_ends(self):
        out, rc = run_bash("trap uncle_title_end EXIT\nuncle_title_begin 7\nexit 3")
        self.assertEqual(rc, 3)
        self.assertEqual(out.count(POP), 1)

    def test_not_a_tty_writes_nothing(self):
        out, rc = run_bash("uncle_title_begin 5\nuncle_title_end", tty=False)
        self.assertEqual(rc, 0)
        self.assertNotIn(b"\x1b", out)

    def test_opt_out_exact_zero(self):
        out, _ = run_bash("uncle_title_begin 5\nuncle_title_end",
                          {"UNCLE_TERMINAL_TITLE": "0"})
        self.assertEqual(out, b"")
        out, _ = run_bash("uncle_title_begin 5\nuncle_title_end",
                          {"UNCLE_TERMINAL_TITLE": "false"})
        self.assertEqual(out.count(PUSH), 1)

    def test_term_dumb_or_unset(self):
        for term in ("dumb", None):
            out, _ = run_bash("uncle_title_begin 5\nuncle_title_end", {"TERM": term})
            self.assertEqual(out, b"", term)

    def test_missing_python3_silent_exit_zero(self):
        out, rc = run_bash("uncle_title_begin 5\nuncle_title_end\necho rc=$?",
                           path="/nonexistent-dir")
        self.assertNotIn(b"\x1b", out)
        self.assertIn(b"rc=0", out)


class GrepGuardTest(unittest.TestCase):
    def _files(self):
        fs = [ROOT / "uncle", ROOT / "uncle_tui.py"]
        fs += sorted((ROOT / "scripts").glob("*.sh"))
        fs += sorted((ROOT / "scripts" / "lib").glob("*.sh"))
        return [f for f in fs if f.is_file()]

    def test_no_stray_osc_title_literals(self):
        bad = [str(f) for f in self._files() if "]2;" in f.read_text(errors="replace")]
        self.assertEqual(bad, [], "OSC 2 literal outside terminal_title.py")

    def test_drivers_use_title_helper(self):
        for name in ("uncle", "scripts/from-issue.sh", "scripts/change-workflow.sh",
                     "scripts/stagegate.sh"):
            text = (ROOT / name).read_text(errors="replace")
            self.assertIn("uncle_title_begin", text, name)
            self.assertIn("terminal-title.sh", text, name)


if __name__ == "__main__":
    unittest.main()
