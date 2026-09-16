"""Automatic handoff commit when signing is off (Issue 54, CHANGE_PLAN.md T-5..T-12).

Disposable repositories with a git shim that logs every engine call and a
fake gh. Fixture git never signs: global and system config are isolated,
the repository sets commit.gpgsign=false, and any signer git could reach is
a trap script that records the call and fails.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'scripts/lib/change-pr.sh'
SOURCE = LIB.read_text().split("<<'PY'", 1)[1].split('\n', 1)[1].split('\nPY\n', 1)[0]
REAL_GIT = shutil.which('git')
ANSWERS = '\nSummary text\nManual steps\ny\n'
SIGNING_PROMPT = 'Commit signing needs your help.'

GIT_SHIM = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GIT_CALLS"
if [[ "$1" == remote && "${2:-}" == get-url ]]; then
    "$REAL_GIT" "$@" | while IFS= read -r url; do
        case "$url" in
            "$BASE_BARE") echo 'https://github.com/owner/repo.git' ;;
            *) printf '%s\\n' "$url" ;;
        esac
    done
    exit 0
fi
if [[ "$1" == commit && "${FAIL_COMMIT_TREE:-}" == signing ]]; then
    echo 'error: gpg failed to sign the data:' >&2
    echo 'gpg: signing failed: No pinentry' >&2
    exit 128
fi
if [[ "$1" == commit && "${FAIL_COMMIT_TREE:-}" == object ]]; then
    echo 'fatal: not a valid object name deadbeef' >&2
    exit 128
fi
if [[ "$1" == commit && "${CRASH_AFTER_COMMIT_TREE:-}" == 1 ]]; then
    "$REAL_GIT" "$@" > /dev/null
    kill -9 "$PPID"
    exit 1
fi
exec "$REAL_GIT" "$@"
'''

GH_FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
with open(os.environ['GH_CALLS'], 'a') as f: f.write(json.dumps(args) + '\\n')
server = pathlib.Path(os.environ['SERVER'])
if args[:2] == ['auth', 'status']: sys.exit(0)
if args[:2] == ['repo', 'view']:
    print(json.dumps({'nameWithOwner': args[2], 'defaultBranchRef': {'name': 'main'}}))
elif args[0] == 'api':
    print(json.dumps({'fork': False, 'owner': {'type': 'User'}}))
elif args[:2] == ['pr', 'list']:
    print(json.dumps(json.loads(server.read_text()) if server.exists() else []))
elif args[:2] == ['pr', 'view']:
    print(json.dumps(json.loads(server.read_text())[0]))
elif args[:2] == ['pr', 'create']:
    branch = subprocess.check_output(['git', 'branch', '--show-current']).decode().strip()
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    server.with_suffix('.body').write_text(pathlib.Path(args[args.index('--body-file') + 1]).read_text())
    server.write_text(json.dumps([dict(number=7, url='https://github.com/owner/repo/pull/7',
        headRefName=branch, headRefOid=sha, headRepository={'name': 'repo'},
        headRepositoryOwner={'login': 'owner'}, baseRefName='main')]))
    print('https://github.com/owner/repo/pull/7')
else:
    sys.exit(1)
'''

SIGNER = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SIGNER_CALLS"
exit 1
'''


def isolated_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('UNCLE_', 'STAGEGATE_', 'WORKFLOW_', 'GIT_', 'GPG_', 'SSH_'))}
    env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', **extra)
    return env


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pr-auto-commit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.bare = self.root / 'remote.git'
        self.signer = self.bin / 'signer'
        self.env = isolated_env(PATH=str(self.bin) + os.pathsep + os.environ['PATH'], REAL_GIT=REAL_GIT,
                                SERVER=str(self.root / 'server.json'), GH_CALLS=str(self.root / 'gh.jsonl'),
                                GIT_CALLS=str(self.root / 'git.log'), BASE_BARE=str(self.bare),
                                SIGNER_CALLS=str(self.root / 'signer.log'), HOME=str(self.root / 'home'))
        (self.root / 'home').mkdir()
        for name, text in (('git', GIT_SHIM), ('gh', GH_FAKE), ('signer', SIGNER)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        subprocess.run([REAL_GIT, 'init', '--bare', '-q', str(self.bare)], check=True, env=self.env)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        self.git('config', 'gpg.program', str(self.signer))
        (self.repo / '.gitignore').write_text('.uncle/workflow/\n')
        (self.repo / 'source.txt').write_text('before\n')
        (self.repo / 'CHANGE_REQUEST.md').write_text('## Summary\n\nAutomatic commit request\n')
        self.git('add', '.')
        self.git('commit', '--no-gpg-sign', '-qm', 'initial')
        self.original = self.git('rev-parse', 'HEAD')
        self.git('remote', 'add', 'origin', str(self.bare))
        self.git('push', '-q', 'origin', 'main')
        self.state = self.repo / '.uncle/workflow'
        self.state.mkdir(parents=True)
        (self.repo / 'source.txt').write_text('audited\n')

    def git(self, *args):
        return subprocess.check_output([REAL_GIT, '-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false', *args],
                                       cwd=self.repo, env=self.env, stderr=subprocess.PIPE).decode().strip()

    def engine(self, action, text='', **env):
        return subprocess.run(['bash', '-c', '. "$1"; change_pr_engine "$2"', 'test', str(LIB), action],
                              cwd=self.repo, env=dict(self.env, UNCLE_LIB_DIR=str(ROOT / 'scripts/lib'), **env),
                              input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)

    def effective_gpgsign(self):
        # The value the engine reads: no `-c` overrides, same environment.
        read = subprocess.run([REAL_GIT, 'config', '--bool', '--get', 'commit.gpgsign'], cwd=self.repo, env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return read.returncode, read.stdout.strip()

    def freeze(self):
        self.ok(self.engine('freeze'))
        (self.repo / 'FINAL_AUDIT.md').write_text('READY\n')
        sha = hashlib.sha256((self.repo / 'FINAL_AUDIT.md').read_bytes()).hexdigest()
        (self.state / 'audit-verdict').write_text('-\tREADY\t' + sha + '\n')
        self.ok(self.engine('bind'))

    def handoff(self, text=ANSWERS, **env):
        return self.engine('handoff', text, **env)

    def journal(self):
        return json.loads((self.state / 'pr/journal.json').read_text())

    def gh_calls(self):
        path = self.root / 'gh.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def creates(self):
        return [a for a in self.gh_calls() if a[:2] == ['pr', 'create']]

    def git_log(self):
        path = self.root / 'git.log'
        return path.read_text().splitlines() if path.exists() else []

    def commits(self):
        return [line for line in self.git_log() if line.split(' ')[0] in ('commit', 'commit-tree')]

    def assert_signer_untouched(self):
        self.assertFalse((self.root / 'signer.log').exists(), 'the fixture signer was invoked')

    def assert_created_automatically(self, result, commit_trees=1):
        self.ok(result)
        self.assertNotIn('needs your help', result.stdout)
        j = self.journal()
        self.assertEqual(j['phase'], 'created')
        self.assertFalse(j['requires_signature'])
        self.assertNotIn('manual_signing', j)
        self.assertNotIn('manual_signed_head', j)
        self.assertEqual(len(self.creates()), 1)
        self.assertEqual([line.split(' ')[0] for line in self.commits()], ['commit'] * commit_trees)
        self.assertEqual(self.commits()[-1], 'commit --no-gpg-sign -m %s' % j['title'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), j['intended_head'])
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}'), j['commit_tree'])
        self.assertEqual(self.git('rev-list', '--parents', '-n', '1', 'HEAD').split(), [j['intended_head'], self.original])
        self.assertEqual(self.git('cat-file', 'commit', 'HEAD').count('gpgsig'), 0)
        self.assert_signer_untouched()
        return j

    def assert_signing_prompt(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(SIGNING_PROMPT, result.stdout)
        self.assertIn('No answer received', result.stdout)
        self.assertNotIn('Commit needs your help.', result.stdout)
        j = self.journal()
        self.assertEqual((j['phase'], j['intended_head'], j['requires_signature'], j['manual_signing']),
                         ('prepared', '', True, True))
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual(self.creates(), [])
        self.assert_signer_untouched()
        return j


class SourceTests(unittest.TestCase):
    """T-5: AC-4, I-1, I-2 over the engine text."""

    def blocks(self):
        parts = re.split(r'(?m)^(?=def |class |[A-Z_]+ = )', SOURCE)
        return {part.split('(')[0].split(' =')[0].replace('def ', '').strip(): part for part in parts}

    def test_no_sign_flags_outside_the_manual_command(self):
        blocks = self.blocks()
        self.assertIn('manual_signed_commit', blocks)
        self.assertIn('automatic_commit', blocks)
        rest = ''.join(text for name, text in blocks.items() if name != 'manual_signed_commit')
        for flag in ("'-S'", "'-S ", '--gpg-sign', '-S '):
            self.assertNotIn(flag, rest, flag)
        self.assertIn("['git', 'commit', '--no-gpg-sign', '-m', j['title']]",
                      blocks['automatic_commit'])

    def test_only_git_config_call_is_a_read(self):
        calls = [m.group(0) for m in re.finditer(r"\[?'git',\s*'config'[^\]\)]*|git\('config'[^\)]*", SOURCE)]
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("'--get'", calls[0])
        for write in ('--unset', '--add', '--replace-all', '--edit', "'config', 'commit", "'config', 'gpg", "'config', 'user"):
            self.assertNotIn(write, calls[0])
        self.assertNotIn('gpg.program', SOURCE)
        self.assertNotIn('user.signingkey', SOURCE)


class AutomaticCommitTests(Fixture):
    def test_t6_unset_and_local_false_commit_without_prompt(self):
        # AC-1, I-6: unset first, then an explicit local false in a second fixture.
        self.git('config', '--unset', 'commit.gpgsign')
        self.assertEqual(self.effective_gpgsign(), (1, ''))
        self.freeze()
        result = self.handoff()
        j = self.assert_created_automatically(result)
        log = self.git_log()
        self.assertLess(log.index('symbolic-ref HEAD refs/heads/' + j['head_branch']),
                        log.index(self.commits()[0]))
        pushed = subprocess.check_output([REAL_GIT, 'rev-parse', j['head_branch']], cwd=self.bare, env=self.env)
        self.assertEqual(pushed.decode().strip(), j['intended_head'])
        for text in ('PR title [default:', 'Work summary:', 'Manual verification steps:',
                     'Commit and publish exactly this audited diff and create the PR? [y/n]:', 'PR: https://github.com/owner/repo/pull/7'):
            self.assertIn(text, result.stdout)

    def test_t6_local_false_commits_without_prompt(self):
        self.assertEqual(self.effective_gpgsign(), (0, 'false'))
        self.freeze()
        self.assert_created_automatically(self.handoff())

    def test_t6_consent_precedes_the_commit(self):
        # B-9 / I-5: declining publication leaves no commit and no commit-tree call.
        self.freeze()
        result = self.handoff('\nSummary text\nManual steps\nn\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Publication declined', result.stdout)
        self.assertEqual(self.commits(), [])
        self.assertEqual(self.journal()['phase'], 'bound')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)

    def test_t8_global_true_is_overridden_by_local_false_and_signer_never_runs(self):
        # AC-4: git's effective value is local false; the trap signer in the global file stays idle.
        inherited = self.root / 'inherited-gitconfig'
        inherited.write_text('[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n[gpg]\n\tprogram = ' + str(self.signer) + '\n')
        self.env['GIT_CONFIG_GLOBAL'] = str(inherited)
        self.freeze()
        self.assert_created_automatically(self.handoff())
        self.assertEqual(self.effective_gpgsign(), (0, 'false'))

    def test_t10_second_handoff_reuses_the_commit(self):
        # AC-7: intended_head set skips prepare_commit; one commit, one PR.
        self.freeze()
        first = self.assert_created_automatically(self.handoff())
        again = self.handoff('')
        self.assert_created_automatically(again)
        self.assertIn('PR: https://github.com/owner/repo/pull/7', again.stdout)
        self.assertEqual(self.journal()['intended_head'], first['intended_head'])
        self.assertEqual(len(self.commits()), 1)

    def test_t12_crash_after_commit_tree_recovers_on_rerun(self):
        # I-3: killed between commit-tree and save; the rerun re-enters prepare_commit.
        self.freeze()
        crashed = self.handoff(CRASH_AFTER_COMMIT_TREE='1')
        self.assertNotEqual(crashed.returncode, 0)
        j = self.journal()
        self.assertEqual((j['phase'], j['intended_head']), ('prepared', ''))
        self.assertNotIn('manual_signing', j)
        self.assertEqual(len(self.commits()), 1)
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual(self.creates(), [])
        self.assert_created_automatically(self.handoff(''), commit_trees=1)


class SigningOnTests(Fixture):
    """T-7: every configuration level git merges routes to the person."""

    def assert_person_signs(self, **env):
        self.freeze()
        self.assert_signing_prompt(self.handoff(**env))
        self.assertEqual(self.commits(), [])
        resumed = self.handoff('', **env).stdout
        self.assertIn('git commit -S ', resumed.split('then run:\n', 1)[1].split('\nReturn here', 1)[0])
        self.assertEqual(self.commits(), [])
        self.assertNotIn('signing_fallback', self.journal())

    def test_local_true(self):
        self.git('config', 'commit.gpgsign', 'true')
        self.assert_person_signs()

    def test_global_true(self):
        self.git('config', '--unset', 'commit.gpgsign')
        inherited = self.root / 'inherited-gitconfig'
        inherited.write_text('[commit]\n\tgpgsign = true\n')
        self.env['GIT_CONFIG_GLOBAL'] = str(inherited)
        self.assert_person_signs()

    def test_include_path(self):
        (self.root / 'signing.inc').write_text('[commit]\n\tgpgsign = true\n')
        self.git('config', '--unset', 'commit.gpgsign')
        self.git('config', 'include.path', str(self.root / 'signing.inc'))
        self.assertEqual(self.effective_gpgsign(), (0, 'true'))
        self.assert_person_signs()

    def test_include_if_gitdir(self):
        (self.root / 'signing.inc').write_text('[commit]\n\tgpgsign = true\n')
        self.git('config', '--unset', 'commit.gpgsign')
        self.git('config', 'includeIf.gitdir:' + self.repo.resolve().as_posix() + '/.path', str(self.root / 'signing.inc'))
        self.assertEqual(self.effective_gpgsign(), (0, 'true'))
        self.assert_person_signs()

    def test_worktree_config(self):
        self.git('config', 'extensions.worktreeConfig', 'true')
        self.git('config', '--worktree', 'commit.gpgsign', 'true')
        self.assertEqual(self.effective_gpgsign(), (0, 'true'))
        self.assert_person_signs()

    def test_environment_config(self):
        self.assert_person_signs(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='commit.gpgsign', GIT_CONFIG_VALUE_0='true')


class FailureTests(Fixture):
    def test_t9_signing_error_from_commit_tree_falls_back_to_person(self):
        # AC-3: git reports a signing failure although the reading was off.
        self.freeze()
        result = self.handoff(FAIL_COMMIT_TREE='signing')
        j = self.assert_signing_prompt(result)
        self.assertEqual(j['signing_fallback'], 'error: gpg failed to sign the data:')
        self.assertIn('Automatic commit failed; git requires a signature: error: gpg failed to sign the data:\n', result.stdout)
        self.assertLess(result.stdout.index('Automatic commit failed'), result.stdout.index(SIGNING_PROMPT))
        self.assertEqual(len(self.commits()), 1)
        # The person signs on the resumed handoff; the engine verifies rather than commits.
        command = self.handoff('').stdout.split('then run:\n', 1)[1].split('\nReturn here', 1)[0]
        self.assertIn('git commit -S ', command)
        self.assertEqual(len(self.commits()), 1)

    def test_other_commit_tree_failure_is_pending_not_a_prompt(self):
        # AC-6: no prompt, no journal change beyond the prepared phase, no commit.
        self.freeze()
        result = self.handoff(FAIL_COMMIT_TREE='object')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PR pending: Automatic commit failed:', result.stdout)
        self.assertIn('fatal: not a valid object name deadbeef', result.stdout)
        self.assertNotIn('needs your help', result.stdout)
        j = self.journal()
        self.assertEqual((j['phase'], j['intended_head']), ('prepared', ''))
        self.assertNotIn('manual_signing', j)
        self.assertNotIn('signing_fallback', j)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.original)
        self.assertEqual(self.creates(), [])
        # A clean rerun succeeds without any manual step.
        self.assert_created_automatically(self.handoff(''), commit_trees=2)

    def test_t11_invalid_boolean_is_uncertain_and_routes_to_person(self):
        # AC-5 with real git: exit 128 from `git config --bool`.
        self.git('config', 'commit.gpgsign', 'maybe')
        self.freeze()
        result = self.handoff()
        self.assert_signing_prompt(result)
        self.assertIn("Cannot read commit signing configuration; the commit needs your signature: fatal: bad boolean config value 'maybe'", result.stdout)
        self.assertEqual(self.commits(), [])
        self.assertNotIn('signing_fallback', self.journal())


if __name__ == '__main__':
    unittest.main()
