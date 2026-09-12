#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/install/scripts" "$TMP/project with spaces" "$TMP/bin"
cp "$ROOT/scripts/from-issue.sh" "$TMP/install/scripts/"
cp -R "$ROOT/scripts/lib" "$TMP/install/scripts/"
printf 'Installation sentinel\n' > "$TMP/install/CHANGE_REQUEST.md"
cat > "$TMP/bin/gh" <<'GH'
#!/usr/bin/env bash
[[ "$*" == 'issue view 42 --repo example/project --json title,body,url,state,labels,comments' ]] || { echo unexpected-gh-call >> "$CALLS"; exit 1; }
printf '%s\n' '{"title":"Selected issue","body":"Exact issue body\n\n## Details\nKeep this text.","url":"https://github.com/example/project/issues/42"}'
GH
chmod +x "$TMP/bin/gh"
UNCLE_PROJECT_ROOT="$TMP/project with spaces" PATH="$TMP/bin:$PATH" \
    bash "$TMP/install/scripts/from-issue.sh" https://github.com/example/project/issues/42 --change < /dev/null > "$TMP/output"
grep -q '^Selected issue$' "$TMP/project with spaces/CHANGE_REQUEST.md"
grep -q '^Keep this text\.$' "$TMP/project with spaces/CHANGE_REQUEST.md"
grep -q 'example/project#42' "$TMP/project with spaces/CHANGE_REQUEST.md"
[[ "$(cat "$TMP/install/CHANGE_REQUEST.md")" == 'Installation sentinel' ]]
[[ ! -e "$TMP/install/.uncle" ]]
# Exercise new-mode state, refusal, errors, and deterministic creation races.
python3 -B - "$ROOT" "$TMP" <<'PYTEST'
import os
from pathlib import Path
import select
import subprocess
import sys

root, tmp = map(Path, sys.argv[1:])
script = tmp / 'install/scripts/from-issue.sh'
url = 'https://github.com/example/project/issues/42'
env = dict(os.environ, PATH=str(tmp / 'bin') + os.pathsep + os.environ['PATH'])
for name in ('stagegate.sh', 'change-workflow.sh'):
    (script.parent / name).write_text('#!/bin/bash\necho driver >> "$CALLS"\n')
env['CALLS'] = str(tmp / 'calls')
(tmp / 'bin/curl').write_text('#!/bin/bash\nexit 1\n')
(tmp / 'bin/curl').chmod(0o755)
(script.parents[1] / 'REQUIREMENTS.md').write_text('Install requirements sentinel\n')


def project(name):
    p = tmp / name
    p.mkdir()
    subprocess.run(['git', 'init', '-q', str(p)], check=True)
    return p


def run(p, *args, target=script, extra=None):
    (tmp / 'calls').unlink(missing_ok=True)
    return subprocess.run(['bash', str(target), url, *args],
                          env=dict(env, UNCLE_PROJECT_ROOT=str(p), **(extra or {})),
                          input='', capture_output=True, text=True, timeout=15)


def no_effects(p, result):
    assert not (p / '.uncle').exists(), result.stdout
    assert not (tmp / 'calls').exists(), result.stdout


def refused(p, result):
    assert result.returncode != 0, result.stdout
    assert not any(x in result.stdout for x in ('Created REQUIREMENTS', 'Updated REQUIREMENTS', 'Run:'))
    assert not os.path.lexists(p / 'CHANGE_REQUEST.md'), (result.stdout, result.stderr)
    no_effects(p, result)


p = project('absent')
(p / 'CHANGE_REQUEST.md').write_text('Change sentinel\n')
r = run(p, '--new', '--unattended')
assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
seed = (p / 'REQUIREMENTS.md').read_text()
assert seed.startswith('# Project brief\n') and seed.endswith('\n')
for text in ('Selected issue', 'Exact issue body\n\n## Details\nKeep this text.', url):
    assert text in seed, text
# Compare the generated contract with the repository's requirements guidance.
for heading in (root / 'REQUIREMENTS.md').read_text().splitlines():
    if heading.startswith('## '):
        assert heading in seed, heading
assert (p / 'CHANGE_REQUEST.md').read_text() == 'Change sentinel\n'
assert (script.parents[1] / 'REQUIREMENTS.md').read_text() == 'Install requirements sentinel\n'
assert (tmp / 'calls').read_text() == 'driver\n'
(tmp / 'calls').unlink()

p = project('existing')
f = p / 'REQUIREMENTS.md'
f.write_text('Prefix\n\n# Project brief\nOld tail\n')
r = run(p, '--new')
assert r.returncode == 0, r.stderr
assert f.read_text() == 'Prefix\n' + seed
assert run(p, '--new').returncode == 0
assert f.read_text() == 'Prefix\n' + seed

for kind in ('markerless', 'directory', 'dangling'):
    p = project(kind)
    f = p / 'REQUIREMENTS.md'
    if kind == 'markerless':
        f.write_bytes(b'Keep exact bytes\n')
    elif kind == 'directory':
        f.mkdir()
    else:
        f.symlink_to(p / 'missing')
    refused(p, run(p, '--new'))
    if kind == 'markerless':
        assert f.read_bytes() == b'Keep exact bytes\n'
    elif kind == 'directory':
        assert f.is_dir() and not list(f.iterdir())
    else:
        assert f.is_symlink() and os.readlink(f) == str(p / 'missing')
        assert not (p / 'missing').exists()

for kind in ('request', 'code', 'fresh'):
    p = project('auto-' + kind)
    if kind == 'request':
        (p / 'CHANGE_REQUEST.md').write_text('Existing request\n')
    elif kind == 'code':
        (p / 'app.py').touch()
        subprocess.run(['git', '-C', str(p), 'add', 'app.py'], check=True)
    r = run(p)
    assert r.returncode == 0, r.stderr
    assert (p / ('REQUIREMENTS.md' if kind == 'fresh' else 'CHANGE_REQUEST.md')).exists()
    if kind == 'fresh':
        assert (tmp / 'calls').read_text() == 'driver\n'
        (tmp / 'calls').unlink()
    else:
        no_effects(p, r)

original_gh = (tmp / 'bin/gh').read_text()
for kind, body in [('fetch', 'exit 1'), ('parse', "echo '{broken'"), ('empty', "echo '{}' ")]:
    (tmp / 'bin/gh').write_text('#!/bin/bash\n' + body + '\n')
    p = project(kind + '-error')
    refused(p, run(p, '--new'))
    assert not (p / 'REQUIREMENTS.md').exists()
(tmp / 'bin/gh').write_text(original_gh)

# A test-only copy pauses inside the absent branch; pipes avoid timing sleeps.
source = script.read_text()
anchor = '    if [[ ! -e REQUIREMENTS.md && ! -L REQUIREMENTS.md ]]; then\n'
assert source.count(anchor) == 1
for kind in ('file', 'symlink', 'dangling', 'write-error'):
    p = project('race-' + kind)
    ready_r, ready_w = os.pipe()
    release_r, release_w = os.pipe()
    hooked = script.parent / 'race-from-issue.sh'
    hooked.write_text(source.replace(anchor, anchor +
        '        printf "ready\\n" >&$READY_FD\n        read -r barrier <&$RELEASE_FD\n'))
    proc = subprocess.Popen(['bash', str(hooked), url, '--new', '--unattended'],
        env=dict(env, UNCLE_PROJECT_ROOT=str(p), READY_FD=str(ready_w), RELEASE_FD=str(release_r)),
        pass_fds=(ready_w, release_r), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    os.close(ready_w)
    os.close(release_r)
    try:
        assert select.select([ready_r], [], [], 10)[0], 'absence barrier not reached'
        assert os.read(ready_r, 64) == b'ready\n'
        f = p / 'REQUIREMENTS.md'
        sentinel = p / 'sentinel'
        if kind == 'file':
            f.write_bytes(b'Concurrent file\n')
        elif kind in ('symlink', 'dangling'):
            if kind == 'symlink':
                sentinel.write_bytes(b'Concurrent referent\n')
            f.symlink_to(sentinel)
            assert f.is_symlink()
        else:
            f.mkdir()  # Forces a write failure even when tests run as root.
        os.write(release_w, b'continue\n')
        stdout, stderr = proc.communicate(timeout=10)
        refused(p, subprocess.CompletedProcess([], proc.returncode, stdout, stderr))
        if kind == 'file':
            assert f.read_bytes() == b'Concurrent file\n'
        elif kind in ('symlink', 'dangling'):
            assert f.is_symlink() and os.readlink(f) == str(sentinel)
            if kind == 'symlink':
                assert sentinel.read_bytes() == b'Concurrent referent\n'
            else:
                assert not sentinel.exists()
        else:
            assert f.is_dir() and not list(f.iterdir())
    finally:
        os.close(ready_r)
        os.close(release_w)
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
print('new-mode: seed, compatibility, errors, auto routing, and 4 barriers passed')
PYTEST
echo 'issue-project-root-test: passed'
