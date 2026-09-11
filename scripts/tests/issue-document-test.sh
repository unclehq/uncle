#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 - "$ROOT" "$@" <<'PY'
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
manual = sys.argv[2:] == ['--manual']
assert not sys.argv[2:] or manual, 'usage: issue-document-test.sh [--manual]'
source = (root / 'scripts/from-issue.sh').read_text()

def extract(name):
    start = '^' + name + r'\(\) \{$'
    assert len(re.findall(start, source, re.M)) == 1, name
    matches = re.findall(start + r'.*?^\}$', source, re.M | re.S)
    assert len(matches) == 1, name
    return matches[0]

writers = '\n'.join(extract(n) for n in ('write_change_request', 'write_new_project_brief'))
env = dict(os.environ, OWNER='example', REPO='project', ISSUE_NUM='42',
           URL='https://github.com/example/project/issues/42', TITLE='Fixture title', BODY='Fixture body')

def run(path, function, code=writers):
    return subprocess.run(['bash', '-euo', 'pipefail', '-c', code + '\n' + function],
                          cwd=path, env=env, capture_output=True, text=True, timeout=10)

def refused(result):
    return result.returncode != 0 and not any(s in result.stdout for s in ('Created REQUIREMENTS', 'Updated REQUIREMENTS'))

with tempfile.TemporaryDirectory(prefix='issue-document-') as tmp:
    base = Path(tmp)
    for function, filename, heading in [('write_change_request', 'CHANGE_REQUEST.md', '# Change Request'),
                                         ('write_new_project_brief', 'REQUIREMENTS.md', '# Project brief')]:
        p = base / function
        p.mkdir()
        result = run(p, function)
        assert result.returncode == 0, result.stderr
        f = p / filename
        seed = f.read_text()
        assert seed.startswith(heading + '\n\nIssue 42\n'), f'{filename}: missing identity after heading'
        assert seed.splitlines().count('Issue 42') == 1
        assert env['URL'] in seed and env['TITLE'] in seed and env['BODY'] in seed
        if filename == 'REQUIREMENTS.md':
            f.write_text('Preserved prefix\n' + seed)
        for _ in range(2):
            assert run(p, function).returncode == 0
            assert f.read_text() == ('Preserved prefix\n' if filename == 'REQUIREMENTS.md' else '') + seed
    print('AT-1: exact identities, URLs, creation and repeated replacement passed')

    def install(p, kind):
        f, target = p / 'REQUIREMENTS.md', p / 'referent'
        if kind in ('file', 'markerless'):
            f.write_bytes(b'Preserve exact bytes\n')
        elif kind == 'directory':
            f.mkdir()
        else:
            if kind == 'symlink':
                target.write_bytes(b'Preserve referent\n')
            f.symlink_to(target)

    def preserved(p, kind):
        f, target = p / 'REQUIREMENTS.md', p / 'referent'
        if kind in ('file', 'markerless'):
            return f.read_bytes() == b'Preserve exact bytes\n'
        if kind == 'directory':
            return f.is_dir() and not list(f.iterdir())
        return (f.is_symlink() and os.readlink(f) == str(target) and
                (target.read_bytes() == b'Preserve referent\n' if kind == 'symlink' else not target.exists()))

    for kind in ('markerless', 'directory', 'dangling'):
        p = base / ('refusal-' + kind)
        p.mkdir()
        install(p, kind)
        assert refused(run(p, 'write_new_project_brief')) and preserved(p, kind), kind

    anchor = '    if [[ ! -e REQUIREMENTS.md && ! -L REQUIREMENTS.md ]]; then\n'
    assert writers.count(anchor) == 1
    assert writers.count('set -o noclobber;') == 1
    for mutation in (False, True):
        for kind in (('file', 'symlink', 'dangling') if mutation else ('file', 'symlink', 'dangling', 'directory')):
            p = base / f'race-{mutation}-{kind}'
            p.mkdir()
            code = writers.replace(anchor, anchor + '        printf "ready\\n" >&$READY_FD\n        read -r barrier <&$RELEASE_FD\n')
            if mutation:
                code = code.replace('set -o noclobber;', '')
            script = p / 'writer.sh'
            script.write_text(code + '\nwrite_new_project_brief\n')
            ready_r, ready_w = os.pipe()
            release_r, release_w = os.pipe()
            proc = subprocess.Popen(['bash', '-euo', 'pipefail', str(script)], cwd=p,
                env=dict(env, READY_FD=str(ready_w), RELEASE_FD=str(release_r)),
                pass_fds=(ready_w, release_r), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            os.close(ready_w)
            os.close(release_r)
            try:
                assert select.select([ready_r], [], [], 10)[0], 'absence barrier timeout'
                assert os.read(ready_r, 64) == b'ready\n'
                install(p, kind)
                os.write(release_w, b'continue\n')
                stdout, stderr = proc.communicate(timeout=10)
                result = subprocess.CompletedProcess([], proc.returncode, stdout, stderr)
                protected = refused(result) and preserved(p, kind)
                assert protected != mutation, f'race {kind}, mutation={mutation}'
                if mutation:
                    assert not preserved(p, kind), f'mutation did not alter {kind}'
            finally:
                os.close(ready_r)
                os.close(release_w)
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
    print('AT-3: seven refusal/race cases passed; AT-4: three noclobber mutations detected')

for name in ('change-plan.md', 'updated-change-plan.md'):
    prompt = (root / 'prompts/change' / name).read_text()
    for phrase in ('- CHANGE_REQUEST.md', 'first top-level `Seeded from` link', 'before the first `##`',
                   'first standalone `Issue N`', 'URL number wins', 'verbatim',
                   'omit the identity line', 'after title metadata', 'Ignore issue identities in body sections'):
        assert phrase in prompt, f'{name}: missing {phrase}'
print('AT-2: both prompt contracts passed')

if manual:
    evidence = Path(tempfile.mkdtemp(prefix='issue-document-manual-'))
    print(f'MC-1 evidence: {evidence}', flush=True)
    assert shutil.which('claude'), 'MC-1 requires claude'
    url = 'https://github.com/example/project/issues/22'
    link = f'Seeded from [example/project#22]({url}).'
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    failures = []
    for i, metadata in enumerate(('Issue 22\n' + link, link, 'Issue 99\n' + link, 'Issue 22', '', ''), 1):
        p = evidence / f'F-{i}'
        p.mkdir()
        for filename in filter(None, tracked):
            src, dest = root / filename, p / filename
            if src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        subprocess.run(['git', 'init', '-q', str(p)], check=True)
        (p / 'CHANGE_PLAN.md').unlink(missing_ok=True)
        shutil.copy2(root / 'CHANGE_SPEC.md', p / 'CHANGE_SPEC.md')
        (p / 'CHANGE_REQUEST.md').write_text('# Change Request\n\n' + metadata +
            '\n\n## Summary\nAdd issue identity to seeded documents.\n' +
            ('\n## Examples\nIssue 12\n' if i != 6 else ''))
        (p / 'BASELINE_REPORT.md').write_text('# Baseline\n\nChange surface: scripts/from-issue.sh, '
            'prompts/change/change-plan.md, prompts/change/updated-change-plan.md.\n'
            'Current seed format: heading, standalone Issue N, Seeded from link, body sections.\n')
        (p / 'ADVERSARIAL_REVIEW.md').write_text('# Review\n\nNo findings.\n')
        for stage, prompt in (('initial', 'change-plan.md'), ('revised', 'updated-change-plan.md')):
            with (p / 'prompts/change' / prompt).open() as stdin, (p / f'{stage}.log').open('w') as log:
                result = subprocess.run(['claude', '-p', '--allowedTools', 'Read,Write,Edit,Glob,Grep,Bash'],
                                        cwd=p, stdin=stdin, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode != 0:
                raise AssertionError(f'MC-1 external execution failed: {p}/{stage}.log (exit {result.returncode})')
            plan = p / 'CHANGE_PLAN.md'
            assert plan.is_file() and plan.stat().st_size, f'{p}: missing {stage} plan'
            shutil.copy2(plan, p / f'{stage}.md')
            text = plan.read_text()
            metadata_text = re.split(r'^##(?:\s|$)', text, maxsplit=1, flags=re.M)[0]
            identities = re.findall(r'^Issue (\d+)\s*$', metadata_text, re.M)
            expected = ['22'] if i <= 4 else []
            if identities != expected or (i <= 3 and url not in text) or (i >= 4 and re.search(r'https?://[^\s)]*/issues/\d+', metadata_text)):
                failures.append(f'F-{i}/{stage}: identity/URL mismatch')
            assert (p / f'{stage}.log').stat().st_size, 'empty model output'
    assert not failures, '\n'.join(failures)
    print('MC-1: six fixtures passed initial and revised generation; inspect retained placement')
PY
