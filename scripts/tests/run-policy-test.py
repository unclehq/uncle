"""Tests for run-policy kind handling in launchers (AC-3, AC-7)."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import run_duties  # noqa: E402


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, *a, **kw):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _git_repo(d):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "i"]):
        subprocess.run(["git", "-c", "commit.gpgsign=false"] + args, cwd=d, env=env, check=True)


class PrepareWorktreeKind(unittest.TestCase):
    def test_app_kind_returns_none_and_runs_nothing(self):
        for kind in ("app", "create_app", "run_app", "stagegate.sh"):
            rec = Recorder()
            with tempfile.TemporaryDirectory() as d:
                got = run_duties.prepare_worktree(ROOT, d, environ={}, kind=kind, runner=rec)
            self.assertIsNone(got, kind)
            self.assertEqual(rec.calls, [], kind)

    def test_none_empty_unknown_kind_keep_today_behavior(self):
        for kind in (None, "", "unknown", "APP", "stagegate.sh "):
            rec = Recorder()
            with tempfile.TemporaryDirectory() as d:
                run_duties.prepare_worktree(ROOT, d, environ={}, kind=kind, runner=rec)
            self.assertTrue(rec.calls, "kind %r must still invoke worktree creation" % (kind,))

    def test_change_kind_still_invokes_creation(self):
        rec = Recorder()
        with tempfile.TemporaryDirectory() as d:
            run_duties.prepare_worktree(ROOT, d, environ={}, kind="change_request", runner=rec)
        self.assertTrue(rec.calls)

    def test_default_call_without_kind_unchanged(self):
        rec = Recorder()
        with tempfile.TemporaryDirectory() as d:
            run_duties.prepare_worktree(ROOT, d, environ={}, runner=rec)
        self.assertTrue(rec.calls)

    def test_locked_root_still_skips(self):
        rec = Recorder()
        got = run_duties.prepare_worktree(ROOT, "/tmp", environ={"UNCLE_PROJECT_ROOT_LOCKED": "1"},
                                          kind="change_request", runner=rec)
        self.assertIsNone(got)
        self.assertEqual(rec.calls, [])


class LauncherDelegation(unittest.TestCase):
    def _read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_tui_passes_kind(self):
        src = self._read("uncle_tui.py")
        self.assertIn("create_app", src)
        self.assertIn("kind", src)

    def test_headless_uses_startup_action_as_kind(self):
        src = self._read("scripts/lib/uncle_headless.py")
        self.assertIn("UNCLE_STARTUP_ACTION", src)
        self.assertIn("kind", src)

    def test_shell_launcher_passes_driver_basename(self):
        self.assertIn("##*/", self._read("uncle"))

    def test_launchers_do_not_duplicate_policy_decisions(self):
        for rel in ("uncle_tui.py", "scripts/lib/uncle_headless.py", "scripts/lib/run_duties.py"):
            self.assertNotIn("check-ref-format", self._read(rel), rel)


if __name__ == "__main__":
    unittest.main()
