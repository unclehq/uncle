#!/usr/bin/env python3
"""reviewer-prompt-kind: reviewer_prompt_kind helper, driver wiring, wrapper launch, hosted resolution."""
import os, re, stat, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts' / 'lib' / 'reviewer-prompt.sh'
STAGEGATE = ROOT / 'scripts' / 'stagegate.sh'
CHANGEWF = ROOT / 'scripts' / 'change-workflow.sh'
WRAPPER = ROOT / 'scripts' / 'reviewer-self-hosted.sh'


def bash(script, *args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(['bash', '-c', script, 'bash', *args], capture_output=True, text=True, env=e)


def kind(*cmd, root=ROOT):
    r = bash('set -u; . "$1"; shift; reviewer_prompt_kind "$@"', str(HELPER), *cmd,
             env={'UNCLE_RUNTIME_ROOT': str(root)})
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def snippet(path, extra):
    """Driver lines that compute prompt_kind: the helper call plus `extra` following lines."""
    lines = path.read_text().splitlines()
    i = next(n for n, l in enumerate(lines) if 'prompt_kind="$(reviewer_prompt_kind' in l)
    return '\n'.join(lines[i:i + 1 + extra]), lines[i:i + 1 + extra]


def driver_kind(path, extra, *cmd):
    code, _ = snippet(path, extra)
    r = bash('set -u; . "$1"; shift; client_cmd=("$@"); prompt_kind=argv\n' + code + '\necho "$prompt_kind"',
             str(HELPER), *cmd)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class HelperTable(unittest.TestCase):
    def test_table(self):
        for cmd, want in [
            ((), 'argv'), (('',), 'argv'), (('', ''), 'argv'),
            (('/x/self_hosted.py',), 'file'), (('/x/native_stage.py',), 'file'),
            (('python3', '/x/self_hosted.py'), 'file'), (('bash', 'native_stage.py', '--'), 'file'),
            (('sh', '/x/self_hosted.py'), 'file'),
            (('codex',), 'argv'), (('claude',), 'argv'), (('env', 'FOO=1', 'codex'), 'argv'),
            (('codex', 'self_hosted.py'), 'argv'),            # later look-alike stays argv
            (('python3', 'other.py', 'native_stage.py'), 'argv'),
            (('/tmp/elsewhere/reviewer-self-hosted.sh',), 'argv'),   # wrapper outside runtime scripts
            (('reviewer-self-hosted.sh',), 'argv'),                  # PATH-resolved name
            ((str(WRAPPER),), 'file'),
        ]:
            self.assertEqual(kind(*cmd), want, cmd)

    def test_divergence_python3_non_allowlisted(self):
        cmd = ('python3', '/x/custom_reviewer.py')
        self.assertEqual(kind(*cmd), 'argv')
        self.assertEqual(driver_kind(STAGEGATE, 3, *cmd), 'file')   # python3 clause OR'd
        self.assertEqual(driver_kind(CHANGEWF, 0, *cmd), 'argv')    # helper alone

    def test_wrapper_elsewhere_same_name_is_argv(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'reviewer-self-hosted.sh').write_text('#!/bin/sh\n')
            self.assertEqual(kind(str(Path(d) / 'reviewer-self-hosted.sh')), 'argv')


class CallSites(unittest.TestCase):
    def test_both_drivers_use_helper_and_old_patterns_gone(self):
        self.assertIn('reviewer_prompt_kind', STAGEGATE.read_text())
        t = CHANGEWF.read_text()
        self.assertIn('reviewer_prompt_kind', t)
        self.assertNotIn('*native_stage.py*|*self_hosted.py*) prompt_kind=file', t)
        self.assertNotIn('self_hosted.py|native_stage.py) prompt_kind=file', t)

    def test_empty_client_cmd_set_u(self):
        for path, extra in ((STAGEGATE, 3), (CHANGEWF, 0)):
            code, _ = snippet(path, extra)
            r = bash('set -u; . "$1"; client_cmd=(); prompt_kind=argv\n' + code + '\necho "$prompt_kind"', str(HELPER))
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'argv'), r.stderr)


class WrapperLaunch(unittest.TestCase):
    def run_case(self, path, extra):
        with tempfile.TemporaryDirectory() as d:
            rt = Path(d) / 'rt'
            (rt / 'scripts' / 'lib').mkdir(parents=True)
            rec = Path(d) / 'rec.txt'
            (rt / 'scripts' / 'lib' / 'self_hosted.py').write_text(
                'import sys\nopen(%r,"w").write("\\n".join(sys.argv[1:]))\n' % str(rec))
            wrapper = rt / 'scripts' / 'reviewer-self-hosted.sh'
            wrapper.write_text(WRAPPER.read_text())
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
            prompt = Path(d) / 'prompt.txt'
            prompt.write_text('x' * 200000)
            code, _ = snippet(path, extra)
            script = ('set -u; . "$1"; client_cmd=("$2"); prompt_kind=argv\n' + code + '\n'
                      'reviewer_prompt_guard r "$prompt_kind" "$3" || exit 9\n'
                      'if [ "$prompt_kind" = file ]; then args=(--prompt-file "$3"); else args=("$(cat "$3")"); fi\n'
                      '"${client_cmd[@]}" "${args[@]}"')
            r = bash(script, str(HELPER), str(wrapper), str(prompt), env={'UNCLE_RUNTIME_ROOT': str(rt)})
            self.assertEqual(r.returncode, 0, r.stderr)
            got = rec.read_text().split('\n')
            self.assertIn('--prompt-file', got)
            self.assertEqual(got[got.index('--prompt-file') + 1], str(prompt))
            self.assertTrue(all(len(a) < 120000 for a in got))

    def test_stagegate_block(self):
        self.run_case(STAGEGATE, 3)

    def test_changeworkflow_block(self):
        self.run_case(CHANGEWF, 0)


class Hosted(unittest.TestCase):
    def test_hosted_resolves_wrapper_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            r = bash('cd "$1"; . "$2"; stage_reviewer_cmd adversarial-review',
                     d, str(ROOT / 'scripts' / 'lib' / 'stage-config.sh'),
                     env={'UNCLE_HOSTED': '1', 'UNCLE_RUNTIME_ROOT': str(ROOT)})
            out = r.stdout.strip()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(out.endswith('reviewer-self-hosted.sh'), 'wrapper not resolved: %r %r' % (out, r.stderr))
            self.assertEqual(kind(out), 'file')


class GuardBoundary(unittest.TestCase):
    def test_argv_client_over_limit_refused_at_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            for size, rc in ((120000, 0), (120001, 1)):
                p = Path(d) / 'p'
                p.write_text('x' * size)
                r = bash('. "$1"; reviewer_prompt_guard r "$(reviewer_prompt_kind codex)" "$2"', str(HELPER), str(p))
                self.assertEqual(r.returncode, rc, r.stderr)
                if rc:
                    self.assertIn('over Linux', r.stderr)


if __name__ == '__main__':
    unittest.main()
