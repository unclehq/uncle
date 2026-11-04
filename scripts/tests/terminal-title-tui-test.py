#!/usr/bin/env python3
"""pty tests: the TUI pushes the title stack once, pops once, project-only title first."""
import os
import pty
import select
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_tui(env_extra, stub="normal"):
    root = tempfile.mkdtemp(prefix="ttl-proj-")
    project = os.path.join(root, "demo-proj")
    os.mkdir(project)
    env = dict(os.environ, TERM="xterm", UNCLE_PROJECT_ROOT=project, UNCLE_TUI_TEST_MAIN=stub)
    env.pop("UNCLE_TERMINAL_TITLE", None)
    env.pop("UNCLE_TITLE_OWNER", None)
    env.update(env_extra)
    master, slave = pty.openpty()
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "uncle_tui.py")], stdin=slave,
                            stdout=slave, stderr=slave, env=env, cwd=project)
    os.close(slave)
    out = b""
    while True:
        ready, _, _ = select.select([master], [], [], 15)
        if not ready:
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
    return out.decode("utf-8", "replace")


class TuiTitleTest(unittest.TestCase):
    def test_push_then_title_then_restore_order(self):
        out = run_tui({})
        push = out.find("\x1b[22;2t")
        title = out.find("\x1b]2;demo-proj · uncle\x07")
        pop = out.rfind("\x1b[23;2t")
        self.assertEqual(out.count("\x1b[22;2t"), 1)
        self.assertEqual(out.count("\x1b[23;2t"), 1)
        self.assertTrue(0 <= push < title < pop, out)
        final = out.rfind("\x1b]2;demo-proj · uncle\x07")
        self.assertLess(final, pop)

    def test_opt_out_writes_nothing(self):
        out = run_tui({"UNCLE_TERMINAL_TITLE": "0"})
        self.assertNotIn("\x1b]2;", out)
        self.assertNotIn("\x1b[22;2t", out)
        self.assertNotIn("\x1b[23;2t", out)

    def test_pop_on_systemexit(self):
        out = run_tui({}, stub="systemexit")
        self.assertEqual(out.count("\x1b[22;2t"), 1)
        self.assertEqual(out.count("\x1b[23;2t"), 1)


if __name__ == "__main__":
    unittest.main()
