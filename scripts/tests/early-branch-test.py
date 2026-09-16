"""Early PR-head branch creation (Issue 60, T-1..T-7).

`change_pr_engine start` runs from scripts/change-workflow.sh before the first
stage. Fixtures are disposable repositories with an inherited signing
configuration that points at a failing fake signer, so any accidental commit
or tag signing fails loudly and is recorded.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib/change-pr.sh'
DRIVER = ROOT / 'scripts/change-workflow.sh'
SOURCE = LIB.read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
REAL_GIT = shutil.which('git')
COLLISION = 'Intended branch already exists with different content.'
MUTATING = ('commit', 'commit-tree', 'push', 'tag', 'checkout', 'switch', 'reset', 'remote add')
# `symbolic-ref --short HEAD` reads the current branch; `symbolic-ref HEAD <ref>`
# moves it. Matching the bare verb counted every read of the branch name as a
# mutation, so it is classified by whether a target argument is present.


def mutates(line):
    if line.startswith('symbolic-ref '):
        return len([a for a in line.split()[1:] if not a.startswith('-')]) > 1
    return line.startswith(MUTATING)

GIT_SHIM = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GIT_CALLS"
exec "$REAL_GIT" "$@"
'''

# Records every invocation and fails without prompting (AGENTS.md).
SIGNER = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SIGNER_CALLS"
exit 1
'''

GH_FAKE = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_CALLS"
exit 1
'''

# Stub first stage: records what the stage sees, then fails so the driver stops.
AGENT_STUB = '''#!/usr/bin/env bash
{ git for-each-ref --format='%(refname) %(objectname)'; git rev-parse HEAD; } > "$MARKER"
exit 7
'''


def isolated_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('UNCLE_', 'STAGEGATE_', 'WORKFLOW_', 'GIT_', 'GPG_'))}
    env.update(GIT_CONFIG_NOSYSTEM='1', **extra)
    return env


class EarlyBranchFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.bare = self.root / 'remote.git'
        self.marker = self.root / 'marker'
        for name, text in (('git', GIT_SHIM), ('fake-signer', SIGNER), ('gh', GH_FAKE), ('agent', AGENT_STUB)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        # Inherited configuration that would sign every commit and tag.
        (self.root / 'gitconfig').write_text(
            '[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n[gpg]\n\tprogram = '
            + str(self.bin / 'fake-signer') + '\n')
        self.env = isolated_env(PATH=str(self.bin) + os.pathsep + os.environ['PATH'], REAL_GIT=REAL_GIT,
                                GIT_CONFIG_GLOBAL=str(self.root / 'gitconfig'),
                                GIT_CALLS=str(self.root / 'git.log'), SIGNER_CALLS=str(self.root / 'signer.log'),
                                GH_CALLS=str(self.root / 'gh.log'), MARKER=str(self.marker),
                                UNCLE_LIB_DIR=str(ROOT / 'scripts/lib'))
        subprocess.run([REAL_GIT, 'init', '--bare', '-q', str(self.bare)], check=True, env=self.env)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.repo / '.gitignore').write_text('.uncle/workflow/\n')
        (self.repo / 'source.txt').write_text('before\n')
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\nEarly branch demo\n')
        self.git('add', '.')
        self.git('commit', '--no-gpg-sign', '-qm', 'initial')
        self.git('tag', '--no-sign', '-a', '-m', 'fixture', 'v0')
        self.original = self.git('rev-parse', 'HEAD')
        self.state = self.repo / '.uncle/workflow'
        self.state.mkdir(parents=True)
        (self.state / 'state').write_text('1:ANALYZE\n')

    def with_remote(self, default=True):
        self.git('remote', 'add', 'origin', str(self.bare))
        self.git('push', '-q', 'origin', 'main')
        if default:
            self.git('remote', 'set-head', 'origin', 'main')

    def git(self, *args, cwd=None, ok=False):
        result = subprocess.run([REAL_GIT, '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', *args],
                                cwd=cwd or self.repo, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode and not ok:
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
        return result.stdout.decode().strip()

    def start(self):
        return subprocess.run(['bash', '-c', '. "$1"; change_pr_engine start', 'test', str(LIB)], cwd=self.repo,
                              env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def driver(self, state='1:ANALYZE'):
        (self.state / 'state').write_text(state + '\n')
        env = dict(self.env, UNCLE_PROJECT_ROOT=str(self.repo), WORKFLOW_CLOSE_ISSUE='0',
                   WORKFLOW_AGENT_CMD=str(self.bin / 'agent'))
        return subprocess.run(['bash', str(DRIVER)], cwd=self.repo, env=env, stdin=subprocess.DEVNULL, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)

    def journal_path(self):
        return self.state / 'pr/journal.json'

    def journal(self):
        return json.loads(self.journal_path().read_text())

    def refs(self):
        return self.git('for-each-ref', '--format=%(refname) %(objectname)')

    def snapshot(self):
        # Everything `start` must leave alone: HEAD, index, files, refs, remote, history.
        return (self.git('rev-parse', '--verify', '-q', 'HEAD', ok=True), self.git('branch', '--show-current'), self.git('ls-files', '-s'),
                self.git('status', '--porcelain'), self.git('rev-list', '--count', '--all'),
                self.git('for-each-ref', cwd=self.bare) if self.bare.exists() else '',
                self.git('remote', '-v'))

    def git_log(self):
        path = self.root / 'git.log'
        return path.read_text().splitlines() if path.exists() else []

    def signer_calls(self):
        path = self.root / 'signer.log'
        return path.read_text().splitlines() if path.exists() else []

    def assert_no_mutation(self, log):
        self.assertFalse([l for l in log if mutates(l)], log)

    def seen(self):
        return self.marker.read_text().splitlines()


class StartTests(EarlyBranchFixture):
    def test_t1_default_branch_ref_exists_before_first_stage(self):
        self.with_remote()
        result = self.driver()
        self.assertEqual(result.returncode, 7, result.stdout)
        j = self.journal()
        # The run starts on its own branch, so original_branch names that; the
        # branch the checkout came from is kept separately, and is what a repair
        # and a deferred naming both fall back to.
        self.assertEqual((j['version'], j['phase'], j['early_ref'], j['original_head']),
                         (2, 'started', True, self.original))
        self.assertEqual(j['original_branch'], j['head_branch'])
        self.assertEqual(j['base_checkout_branch'], 'main')
        self.assertEqual(j['head_branch'], 'uncle/early-branch-demo-' + j['owner'][:12])
        self.assertIn('Branch: ' + j['head_branch'], result.stdout)
        # The stub stage saw the ref at the starting HEAD, on the starting branch.
        seen = self.seen()
        self.assertIn('refs/heads/' + j['head_branch'] + ' ' + self.original, seen)
        self.assertEqual(seen[-1], self.original)
        self.assertLess(result.stdout.index('Branch: '), result.stdout.index('Launching agent'))
        # The first stage runs on the run's branch, not the default one.
        self.assertEqual(self.git('branch', '--show-current'), j['head_branch'])
        self.assertEqual(self.git('rev-parse', 'main'), self.original)
        driver = DRIVER.read_text()
        self.assertLess(driver.index('change_pr_engine start || exit 1'), driver.index('\nwhile true; do\n'))

    def test_t1_unknown_default_defers_without_guessing(self):
        self.with_remote(default=False)
        before = self.refs()
        result = self.driver()
        self.assertEqual(result.returncode, 7, result.stdout)
        j = self.journal()
        self.assertEqual((j['phase'], j['early_ref'], j['head_branch']), ('started', False, ''))
        self.assertEqual(self.refs(), before)
        self.assertNotIn('Branch: ', result.stdout)

    def test_t2_rerun_is_idempotent(self):
        self.with_remote()
        self.assertEqual(self.start().returncode, 0)
        journal = self.journal_path().read_bytes()
        state = self.snapshot()
        refs = self.refs()
        self.assertEqual(self.git('rev-list', '--count', '--all'), '1')
        (self.root / 'git.log').unlink(missing_ok=True)
        for _ in range(2):
            result = self.start()
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(self.journal_path().read_bytes(), journal)
            self.assertEqual(self.snapshot(), state)
            self.assertEqual(self.refs(), refs)
        self.assert_no_mutation(self.git_log())
        self.assertEqual(self.signer_calls(), [])

    def test_t3_non_default_current_branch_is_the_head(self):
        self.with_remote()
        self.git('checkout', '-qb', 'feature')
        before = self.refs()
        result = self.driver()
        self.assertEqual(result.returncode, 7, result.stdout)
        j = self.journal()
        self.assertEqual((j['head_branch'], j['early_ref'], j['original_branch']), ('feature', True, 'feature'))
        self.assertEqual(self.refs(), before)
        self.assertIn('refs/heads/feature ' + self.original, self.seen())
        self.assertEqual(self.git('branch', '--show-current'), 'feature')

    def test_t4_divergent_candidate_ref_is_never_overwritten(self):
        self.with_remote()
        self.assertEqual(self.start().returncode, 0)
        j = self.journal()
        other = self.git('commit-tree', '--no-gpg-sign', self.git('rev-parse', 'HEAD^{tree}'), '-p', self.original,
                         '-m', 'someone else')
        self.git('update-ref', 'refs/heads/' + j['head_branch'], other, self.original)
        journal = self.journal_path().read_bytes()
        state = self.snapshot()
        (self.root / 'git.log').unlink(missing_ok=True)
        result = self.start()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Branch setup failed: ' + COLLISION, result.stdout)
        self.assertNotIn('PR pending', result.stdout)
        self.assertEqual(self.git('rev-parse', 'refs/heads/' + j['head_branch']), other)
        self.assertEqual(self.journal_path().read_bytes(), journal)
        # Moving the candidate ref drags HEAD with it, because HEAD is now a
        # symbolic ref to that branch. The run refuses the collision *and*
        # leaves the checkout back where the operator had it, on the commit
        # they were on -- not on someone else's commit.
        self.assertEqual(self.git('branch', '--show-current'), 'main')
        self.assertEqual(self.git('rev-parse', '--verify', 'HEAD'), self.original)
        files, index = state[2], state[3]
        self.assertEqual((self.git('ls-files', '-s'), self.git('status', '--porcelain')), (files, index))
        self.assertEqual(self.git('rev-list', '--count', '--all'), state[4])
        # The only write is the repair itself: HEAD back onto the operator's
        # branch. Nothing was committed, pushed, or checked out.
        self.assertEqual([l for l in self.git_log() if mutates(l)],
                         ['symbolic-ref HEAD refs/heads/main'])
        # The driver stops before the first stage.
        result = self.driver()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('Branch setup failed: ' + COLLISION, result.stdout)
        self.assertFalse(self.marker.exists())
        self.assertNotIn('Launching agent', result.stdout)

    def test_t4_fresh_start_collision_leaves_no_journal(self):
        self.with_remote()
        other = self.git('commit-tree', '--no-gpg-sign', self.git('rev-parse', 'HEAD^{tree}'), '-p', self.original,
                         '-m', 'someone else')
        self.git('update-ref', 'refs/heads/uncle/early-branch-demo-bbbbbbbbbbbb', other, '0' * 40)
        state = self.snapshot()
        ns = {}
        exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], ns)
        ns['uuid'] = Mock(uuid4=Mock(return_value=Mock(hex='b' * 32)))
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.repo)
        with self.assertRaisesRegex(ns['StartError'], COLLISION.replace('.', r'\.')):
            ns['start']()
        os.chdir(cwd)
        self.assertFalse(self.journal_path().exists())
        self.assertEqual(self.git('rev-parse', 'refs/heads/uncle/early-branch-demo-bbbbbbbbbbbb'), other)
        self.assertEqual(self.snapshot(), state)

    def test_t5_unavailable_contexts_skip_without_journal_or_ref(self):
        cases = {'no-remote': lambda: None,
                 'detached': lambda: (self.with_remote(), self.git('checkout', '-q', '--detach')),
                 'unborn': lambda: None}
        for name, arrange in cases.items():
            with self.subTest(name):
                self.setUp()
                if name == 'unborn':
                    shutil.rmtree(self.repo / '.git')
                    self.git('init', '-q', '-b', 'main')
                    self.git('remote', 'add', 'origin', str(self.bare))
                arrange()
                state = self.snapshot()
                refs = self.refs()
                (self.root / 'git.log').unlink(missing_ok=True)
                result = self.start()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout, '')
                self.assertFalse(self.journal_path().exists())
                self.assertEqual(self.refs(), refs)
                self.assertEqual(self.snapshot(), state)
                self.assert_no_mutation(self.git_log())
        # No-remote build through the driver: today's path, no branch step.
        self.setUp()
        result = self.driver('1:COMPLETE')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('no PR was created', result.stdout)
        self.assertFalse(self.journal_path().exists())
        self.assertEqual(self.refs(), 'refs/heads/main ' + self.original + '\nrefs/tags/v0 '
                         + self.git('rev-parse', 'refs/tags/v0'))

    def test_t6_signer_is_never_invoked(self):
        self.with_remote()
        self.assertEqual(self.signer_calls(), [])
        self.assertEqual(self.git('config', '--get', 'commit.gpgsign'), 'false')
        self.assertEqual(self.git('config', '--get', 'tag.gpgsign'), 'false')
        self.assertEqual(self.git('config', '--global', '--get', 'commit.gpgsign'), 'true')
        self.assertEqual(self.start().returncode, 0)
        self.assertEqual(self.driver().returncode, 7)
        self.assertEqual(self.signer_calls(), [])
        # Positive control: the inherited configuration does reach the fake signer.
        scratch = self.root / 'scratch'
        scratch.mkdir()
        subprocess.run([REAL_GIT, 'init', '-q', str(scratch)], check=True, env=self.env)
        (scratch / 'f').write_text('x\n')
        subprocess.run([REAL_GIT, 'add', 'f'], cwd=scratch, check=True, env=self.env)
        signed = subprocess.run([REAL_GIT, '-c', 'user.name=F', '-c', 'user.email=f@example.test', 'commit', '-qm', 'x'],
                                cwd=scratch, env=self.env, capture_output=True)
        self.assertNotEqual(signed.returncode, 0)
        self.assertEqual(len(self.signer_calls()), 1)

    def test_t7_start_uses_only_reads_and_one_ref_update(self):
        self.with_remote()
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stdout)
        log = self.git_log()
        self.assertFalse((self.root / 'gh.log').exists())
        # Two writes, both on refs and neither on a file: the ref is created at
        # the starting commit, then HEAD is pointed at it so no stage writes to
        # the default branch. Pointing HEAD at a ref that already holds the
        # current commit changes no file and no index entry.
        head_branch = self.journal()['head_branch']
        writes = [l for l in log if l.startswith(('update-ref ', 'symbolic-ref HEAD '))]
        self.assertEqual(writes, [
            'update-ref refs/heads/' + head_branch + ' ' + self.original + ' ' + '0' * 40,
            'symbolic-ref HEAD refs/heads/' + head_branch])
        # An issue-bound start needs no working gh: the label lookup fails and
        # the plain prefix is used.
        self.journal_path().unlink()
        # HEAD lives on that branch now, so step off it before deleting it --
        # otherwise this simulates a broken checkout rather than a fresh run.
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main')
        self.git('update-ref', '-d', writes[0].split()[1], self.original)
        (self.state / 'origin').write_text('owner/repo\t7\tgh\n')
        result = self.start()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.journal()['head_branch'].startswith('uncle/early-branch-demo-'))
        self.assertTrue((self.root / 'gh.log').read_text().startswith('issue view 7'))


class ResolveEarlyIdentityTests(unittest.TestCase):
    """D-6: resolve() reuses the started identity and rejects a changed classification."""

    def setUp(self):
        self.ns = {}
        exec(SOURCE[:SOURCE.rindex('\ntry:\n    main()')], self.ns)
        self.ns.update(save=Mock(), check_remotes=Mock(), remote_identity=lambda r: 'owner/repo',
                       branch_name=Mock(side_effect=AssertionError('name must not be recomputed')),
                       ask=Mock(side_effect=AssertionError('ask must not be called')))
        self.ns['git'] = lambda *a, **k: 'origin' if a == ('remote',) else ''
        self.ns['gh'] = lambda *a: json.dumps({'nameWithOwner': a[2], 'defaultBranchRef': {'name': 'main'}})

    def journal(self, original, head):
        return dict(origin='', owner='a' * 32, original_head='old', original_branch=original, head_branch=head,
                    early_ref=True)

    def test_started_identity_is_reused(self):
        for original, head in (('main', 'uncle/demo-aaaaaaaaaaaa'), ('feature', 'feature')):
            j = self.journal(original, head)
            self.ns['resolve'](j)
            self.assertEqual((j['head_branch'], j['base_branch']), (head, 'main'))

    def test_changed_classification_is_rejected(self):
        for original, head in (('main', 'main'), ('feature', 'uncle/demo-aaaaaaaaaaaa')):
            j = self.journal(original, head)
            with self.assertRaisesRegex(ValueError, 'Early branch identity conflicts'):
                self.ns['resolve'](j)
            self.assertNotIn('base_repo', j)

    def test_deferred_journal_computes_name_as_before(self):
        self.ns['branch_name'] = lambda j: 'uncle/computed-aaaaaaaaaaaa'
        j = dict(origin='', owner='a' * 32, original_head='old', original_branch='main', early_ref=False)
        self.ns['resolve'](j)
        self.assertEqual(j['head_branch'], 'uncle/computed-aaaaaaaaaaaa')


if __name__ == '__main__':
    unittest.main()
