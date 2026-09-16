"""Disposable Git repositories for tests, with signing turned off at every level.

Every fixture repository sets local `commit.gpgsign=false` and
`tag.gpgsign=false`, every command passes the same `-c` overrides, and every
commit passes `--no-gpg-sign`, so no fixture can reach the user's signer even
when the inherited configuration turns signing on. `fake_signer` builds an
environment that proves it: global config demands signing through a script
that records and refuses; a helper commit under that environment leaves the
script's log absent.
"""
import os
from pathlib import Path
import shutil
import subprocess

REAL_GIT = shutil.which('git')
NO_SIGN = ('-c', 'commit.gpgsign=false', '-c', 'tag.gpgsign=false')

SIGNER = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SIGNER_CALLS"
exit 1
'''


def isolated_env(**extra):
    """The parent environment minus workflow, git and signing-agent state."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('UNCLE_', 'STAGEGATE_', 'WORKFLOW_', 'GIT_', 'GPG_', 'SSH_'))}
    env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
    env.update(extra)
    return env


def git(repo, *args, env=None, check=True, data=None):
    result = subprocess.run([REAL_GIT, *NO_SIGN, *args], cwd=str(repo), env=env or isolated_env(),
                            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=data is None)
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    out = result.stdout
    return (out.decode() if isinstance(out, bytes) else out).strip()


def init_repo(path, env=None, branch='main'):
    """`git init` with local signing disabled and a fixture identity; returns the path."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    git(path, 'init', '-q', '-b', branch, env=env)
    for key, value in (('commit.gpgsign', 'false'), ('tag.gpgsign', 'false'), ('gpg.format', 'openpgp'),
                       ('user.name', 'Fixture'), ('user.email', 'fixture@example.test')):
        git(path, 'config', key, value, env=env)
    return path


def commit(repo, message, env=None, add_all=True):
    """One unsigned commit of the working tree; returns its SHA."""
    if add_all:
        git(repo, 'add', '-A', env=env)
    git(repo, 'commit', '--no-gpg-sign', '-q', '--allow-empty', '-m', message, env=env)
    return git(repo, 'rev-parse', 'HEAD', env=env)


def fake_signer(tmp, env=None):
    """An environment whose *global* git config demands signing through a
    script that logs its arguments to `signer.log` and exits 1. Returns
    (env, log_path). The log must stay absent under `init_repo`/`commit`."""
    tmp = Path(tmp)
    script = tmp / 'fake-signer'
    script.write_text(SIGNER)
    script.chmod(0o755)
    log = tmp / 'signer.log'
    config = tmp / 'gitconfig'
    config.write_text('[commit]\n\tgpgsign = true\n[tag]\n\tgpgsign = true\n'
                      '[gpg]\n\tprogram = %s\n[gpg "ssh"]\n\tprogram = %s\n' % (script, script))
    env = dict(env or isolated_env())
    env.update(GIT_CONFIG_GLOBAL=str(config), SIGNER_CALLS=str(log))
    return env, log
