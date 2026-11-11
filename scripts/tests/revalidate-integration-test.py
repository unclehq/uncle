"""Integration: resume the real change driver under UNCLE_REVALIDATE_RESUME with
model/test commands stubbed on PATH; only run-marked stages may execute."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / 'scripts' / 'change-workflow.sh'
UNCLE = ROOT / 'uncle'


def project(tmp):
    proj = Path(tmp) / 'proj'
    (proj / '.uncle' / 'workflow').mkdir(parents=True)
    (proj / '.uncle' / 'docs').mkdir()
    g = ['git', '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false',
         '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']
    subprocess.run(g + ['init', '-q', '-b', 'main'], cwd=proj, check=True)
    subprocess.run(g + ['config', 'commit.gpgsign', 'false'], cwd=proj, check=True)
    (proj / 'app.txt').write_text('x\n')
    subprocess.run(g + ['add', 'app.txt'], cwd=proj, check=True)
    subprocess.run(g + ['commit', '-q', '--no-gpg-sign', '-m', 'init'], cwd=proj, check=True)
    bindir = Path(tmp) / 'bin'
    bindir.mkdir()
    log = Path(tmp) / 'calls.log'
    for name in ('claude', 'codex'):
        p = bindir / name
        p.write_text('#!/bin/sh\necho "%s $*" >> "%s"\nexit 1\n' % (name, log))
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return proj, bindir, log


def drive(proj, bindir, state, plan):
    (proj / '.uncle' / 'workflow' / 'state').write_text(state + '\n')
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('UNCLE_', 'WORKFLOW_'))}
    env.update(PATH='%s:%s' % (bindir, os.environ['PATH']),
               UNCLE_REVALIDATE_RESUME=json.dumps(plan), UNCLE_NOUI='1',
               UNCLE_PROJECT_ROOT=str(proj), UNCLE_RUN_POLICY='off', WORKFLOW_CLOSE_ISSUE='0')
    return subprocess.run(['bash', str(DRIVER), '--unattended'], cwd=proj, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)


class ResumeDriver(unittest.TestCase):
    def test_no_run_marked_stage_executes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, bindir, log = project(tmp)
            plan = [{'stage': 'PLAN', 'action': 'reuse'},
                    {'stage': 'ADVERSARIAL_REVIEW', 'action': 'skip'},
                    {'stage': 'IMPLEMENT', 'action': 'reuse'}]
            r = drive(proj, bindir, 'PLAN', plan)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(log.exists(), 'a model command ran for reused/skipped stages')

    def test_needs_review_stage_stops_with_75(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, bindir, log = project(tmp)
            plan = [{'stage': 'PLAN', 'action': 'needs-review'}]
            r = drive(proj, bindir, 'PLAN', plan)
            self.assertEqual(r.returncode, 75, r.stdout + r.stderr)
            self.assertFalse(log.exists())

    def test_reopened_gate_stops_with_75_and_writes_no_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, bindir, log = project(tmp)
            r = drive(proj, bindir, 'WAIT_PLAN_APPROVAL', [{'stage': 'PLAN', 'action': 'reuse'}])
            self.assertEqual(r.returncode, 75, r.stdout + r.stderr)
            self.assertFalse(list(proj.glob('.uncle/**/approvals/*.sha256')))
            self.assertFalse(log.exists())


class FlagRules(unittest.TestCase):
    def uncle(self, *args):
        return subprocess.run(['bash', str(UNCLE), *args], capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, UNCLE_NOUI='1'))

    def test_dry_run_alone_rejected(self):
        self.assertNotEqual(self.uncle('--dry-run').returncode, 0)

    def test_revalidate_with_other_startup_mode_rejected(self):
        self.assertNotEqual(self.uncle('--revalidate', '--issue', '1').returncode, 0)
        self.assertNotEqual(self.uncle('--revalidate', '--application').returncode, 0)


if __name__ == '__main__':
    unittest.main()
