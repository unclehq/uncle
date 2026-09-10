#!/usr/bin/env bash
# Bash 3.2 entry points; Python owns the atomic journal and temporary Git index.
# No close marker is written by this library.
change_pr_complete() {
    if [[ "$CLOSE_ISSUE" != 1 || "${UNATTENDED:-0}" == 1 || -s "$UNATTENDED_FILE" ]]; then
        echo "PR handoff disabled or unattended; leaving the issue open."
        return 0
    fi
    if [[ -s "$ORIGIN_FILE" ]]; then
        # Journal validation proves PR ownership separately from close ownership.
        # The close sentinel retains its existing meaning on the no-Git path.
        change_pr_engine validate || return 0
        local recorded
        recorded="$(awk -F'\t' 'NR == 1 {print $1}' "$VERDICT_FILE")"
        issue_close_eligible "$recorded" \
            "$(origin_field "$ORIGIN_FILE" 1)" "$(origin_field "$ORIGIN_FILE" 2)" \
            "$VERDICT_FILE" "$ORIGIN_FILE" FINAL_AUDIT.md "$MARKER_FILE" \
            1 "$ORIGIN_BOUND" 1 "$(origin_fetch_method "$ORIGIN_FILE")" || return 0
    fi
    change_pr_engine handoff || true
}

change_pr_engine() {
    local pr_code
    IFS= read -r -d '' pr_code <<'PY' || true
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata
import uuid

STATE = Path('.uncle/workflow')
JOURNAL = STATE / 'pr' / 'journal.json'
AUDIT = Path('FINAL_AUDIT.md')


def run(*args, env=None, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env)
    if result.returncode:
        raise ValueError('Command failed: ' + ' '.join(args) + '\n' +
                         result.stderr.decode('utf-8', 'replace').strip())
    return result.stdout.decode('utf-8').strip()


def git(*args, **kwargs):
    return run('git', *args, **kwargs)


def gh(*args):
    # Same timeout selection and fallback as issue-close.sh.
    import shutil
    timeout = shutil.which('timeout') or shutil.which('gtimeout')
    prefix = [timeout, os.environ.get('STAGEGATE_CLOSE_TIMEOUT', '30')] if timeout else []
    return run(*prefix, 'gh', *args)


def save(j):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=JOURNAL.parent, prefix='.journal-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(j, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, JOURNAL)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read(path):
    return path.read_text() if path.exists() else ''


def head():
    return git('rev-parse', '--verify', 'HEAD')


def branch():
    return git('symbolic-ref', '--short', 'HEAD')


def snapshot(audit=False):
    # Never write the user's index. Store raw bytes so clean filters cannot
    # hide drift or publish content different from the files the auditor read.
    fd, index = tempfile.mkstemp(dir=STATE, prefix='pr-index-')
    os.close(fd)
    os.unlink(index)
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(index).resolve()))
    try:
        git('read-tree', '--empty', env=env)
        paths = set(subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).split(b'\0'))
        paths.update(subprocess.check_output(
            ['git', 'ls-tree', '-rz', '--name-only', 'HEAD']).split(b'\0'))
        entries = []
        for raw in sorted(paths):
            if not raw or raw.startswith(b'.uncle/workflow/') or raw == b'FINAL_AUDIT.md':
                continue
            path = Path(os.fsdecode(raw))
            if not path.exists() and not path.is_symlink():
                continue
            if path.is_symlink():
                mode, content = '120000', os.fsencode(os.readlink(path))
            elif path.is_file():
                mode = '100755' if path.stat().st_mode & 0o100 else '100644'
                content = path.read_bytes()
            else:
                raise ValueError('Submodules/nested repositories cannot be bound; use a supported tree.')
            oid = git('hash-object', '-w', '--no-filters', '--stdin', data=content)
            entries.append(mode.encode() + b' ' + oid.encode() + b'\t' + raw + b'\0')
        if audit:
            if AUDIT.is_symlink() or not AUDIT.is_file():
                raise ValueError('FINAL_AUDIT.md must be a regular file.')
            oid = git('hash-object', '-w', '--no-filters', '--stdin', data=AUDIT.read_bytes())
            mode = b'100755' if AUDIT.stat().st_mode & 0o100 else b'100644'
            entries.append(mode + b' ' + oid.encode() + b'\tFINAL_AUDIT.md\0')
        git('update-index', '-z', '--index-info', env=env, data=b''.join(entries))
        tree = git('write-tree', env=env)
        return tree
    finally:
        for name in (index, index + '.lock'):
            if os.path.exists(name):
                os.unlink(name)


def audit_hash():
    return hashlib.sha256(AUDIT.read_bytes()).hexdigest()


def load():
    try:
        j = json.loads(JOURNAL.read_text())
    except (OSError, ValueError) as error:
        raise ValueError('Missing/corrupt PR binding; resolve any prior outcome, then rerun FINAL_AUDIT.') from error
    required = {'version', 'owner', 'origin', 'audit_hash', 'reviewed_tree', 'commit_tree',
                'original_head', 'intended_head', 'original_branch', 'head_branch',
                'base_repo', 'head_repo', 'base_branch', 'phase', 'url', 'number', 'verdict_run'}
    if (not isinstance(j, dict) or not required <= j.keys() or j['version'] != 1
            or not isinstance(j['owner'], str) or not re.fullmatch(r'[0-9a-f]{32}', j['owner'])
            or j['phase'] not in ('auditing', 'bound', 'prepared', 'published', 'creating', 'created', 'unknown')):
        raise ValueError('Missing/corrupt PR binding; rerun FINAL_AUDIT.')
    return j


def validate(j, ready=True):
    if j['origin'] != read(STATE / 'origin') or j['audit_hash'] != audit_hash():
        raise ValueError('Origin or audit changed; rerun FINAL_AUDIT.')
    verdict = read(STATE / 'audit-verdict').strip().split('\t')
    if len(verdict) != 3 or verdict[0] != j['verdict_run'] or verdict[2] != j['audit_hash']:
        raise ValueError('Verdict binding changed; rerun FINAL_AUDIT.')
    if ready and verdict[1] not in ('READY', 'READY_WITH_NON_BLOCKING_ISSUES'):
        raise ValueError('PR requires an owned READY verdict.')
    if snapshot() != j['reviewed_tree'] or snapshot(True) != j['commit_tree']:
        raise ValueError('Reviewed files changed; rerun FINAL_AUDIT.')
    current = head()
    allowed = [j['original_head']]
    if j['intended_head']:
        allowed.append(j['intended_head'])
        if git('rev-parse', j['intended_head'] + '^{tree}') != j['commit_tree']:
            raise ValueError('Handoff commit tree differs from audit; rerun FINAL_AUDIT.')
        if git('rev-parse', j['intended_head'] + '^') != j['original_head']:
            raise ValueError('Handoff parent differs from audit; rerun FINAL_AUDIT.')
    if current not in allowed or branch() not in (j['original_branch'], j['head_branch']):
        raise ValueError('HEAD or branch changed; rerun FINAL_AUDIT.')
    if j['phase'] in ('published', 'creating', 'unknown', 'created') and (current != j['intended_head'] or branch() != j['head_branch']):
        raise ValueError('Published HEAD changed; rerun FINAL_AUDIT.')


def manual_signed_commit(j):
    import shlex
    command = 'git commit -S -m ' + shlex.quote(j['title'])
    ask('Commit signing needs your help. In another terminal, open this project, '
        'review and stage the audited changes, then run: ' + command + '. '
        'Return here and press ENTER (OK) when finished: ')
    candidate = head()
    if candidate == j['original_head']:
        raise ValueError('No new commit found; PR remains pending. Finish the signed commit and rerun.')
    if git('rev-parse', candidate + '^{tree}') != j['commit_tree']:
        raise ValueError('Manual commit differs from the audited files; rerun FINAL_AUDIT.')
    if git('rev-list', '--parents', '-n', '1', candidate).split() != [candidate, j['original_head']]:
        raise ValueError('Manual commit must have the audited HEAD as its only parent.')
    git('verify-commit', candidate)
    previous = j['intended_head']
    j['intended_head'] = candidate
    try:
        validate(j)
    except Exception:
        j['intended_head'] = previous
        raise
    j.pop('manual_signing', None)
    save(j)


def ask(prompt, default=None):
    try:
        if sys.stdin.isatty() and default is not None:
            import readline
            readline.set_startup_hook(lambda: readline.insert_text(default))
            try:
                answer = input(prompt)
            finally:
                readline.set_startup_hook(None)
        else:
            answer = input(prompt)
    except EOFError:
        raise ValueError('No answer received; PR remains pending. Rerun to resume.')
    return answer.strip() or default or ''


def title_default():
    text = read(Path('CHANGE_REQUEST.md'))
    match = re.search(r'^##\s+(?:\d+\.\s+)?Summary\s*\n(.*?)(?=^##\s|\Z)', text, re.M | re.S | re.I)
    title = match.group(1) if match else ''
    title = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in title)
    return ' '.join(title.split())[:72].strip() or 'Completed change'


def repo_name(value):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value):
        raise ValueError('Unsupported repository identity: ' + value)
    return value


def remote_repo(url):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?', url)
    if not match:
        raise ValueError('Unsupported GitHub remote: ' + url)
    return repo_name(match.group(1))


def remote_identity(remote):
    urls = git('remote', 'get-url', '--push', '--all', remote).splitlines()
    fetch = git('remote', 'get-url', '--all', remote).splitlines()
    if len(urls) != 1 or len(fetch) != 1 or remote_repo(urls[0]).lower() != remote_repo(fetch[0]).lower():
        raise ValueError('Ambiguous fetch/push remote: ' + remote)
    return remote_repo(urls[0])


def remote_sha(j):
    if remote_identity(j['remote']).lower() != j['head_repo'].lower():
        raise ValueError('Head remote changed; rerun FINAL_AUDIT.')
    rows = git('ls-remote', '--heads', j['remote'], 'refs/heads/' + j['head_branch']).splitlines()
    if len(rows) > 1:
        raise ValueError('Ambiguous remote SHA.')
    return rows[0].split()[0] if rows else ''


def resolve(j):
    origin = j['origin'].strip().split('\t')
    remotes = git('remote').splitlines()
    identities = {r: remote_identity(r) for r in remotes}
    if origin != ['']:
        if len(origin) != 3 or origin[2] != 'gh' or not origin[1].isdigit():
            raise ValueError('Only a gh-fetched origin authorizes this PR.')
        base = repo_name(origin[0])
    else:
        candidate = identities.get('origin', '')
        base = repo_name(ask('Base repository [owner/repo]: ', candidate))
    info = json.loads(gh('repo', 'view', base, '--json', 'nameWithOwner,defaultBranchRef'))
    if info['nameWithOwner'].lower() != base.lower():
        raise ValueError('Base repository identity mismatch.')
    base_branch = info['defaultBranchRef']['name']
    if not base_branch:
        raise ValueError('Base repository has no default branch.')
    # A fork checkout normally has origin + upstream. Only one non-base
    # repository may supply the head; duplicates and multiple forks fail closed.
    forks = [r for r, identity in identities.items() if identity.lower() != base.lower()]
    candidates = forks or list(identities)
    if len(candidates) != 1:
        raise ValueError('Ambiguous head remote; configure exactly one head remote.')
    remote = candidates[0]
    head_repo = identities[remote]
    if head_repo.lower() != base.lower():
        fork = json.loads(gh('api', 'repos/' + head_repo))
        if not fork.get('fork') or fork.get('parent', {}).get('full_name', '').lower() != base.lower():
            raise ValueError('Unsupported fork selector; head must be a direct fork of base.')
        owner = head_repo.split('/')[0]
        # gh --head owner:branch cannot select same-owner sibling repositories.
        if owner.lower() == base.split('/')[0].lower() or fork.get('owner', {}).get('type') != 'User':
            raise ValueError('Unsupported fork owner for gh --head.')
    target = j['original_branch']
    if target == base_branch:
        target = 'uncle/change-' + j['owner'][:12]
    git('check-ref-format', '--branch', target)
    j.update(base_repo=base, base_branch=base_branch, head_repo=head_repo,
             head_branch=target, remote=remote)
    j['remote_before'] = remote_sha(j)
    if j['remote_before'] not in ('', j['original_head']):
        raise ValueError('Remote head differs from audited HEAD; rerun FINAL_AUDIT.')
    save(j)


def lookup(j):
    rows = json.loads(gh('pr', 'list', '--repo', j['base_repo'], '--state', 'all',
                         '--head', j['head_branch'], '--limit', '1000', '--json',
                         'number,url,headRefName,headRefOid,headRepository,headRepositoryOwner,baseRefName'))
    if len(rows) >= 1000:
        raise ValueError('PR lookup truncated; independent reconciliation required.')
    matches = []
    for row in rows:
        repository = row.get('headRepository') or {}
        owner = row.get('headRepositoryOwner') or {}
        identity = owner.get('login', '') + '/' + repository.get('name', '')
        if (identity.lower() == j['head_repo'].lower() and row.get('headRefName') == j['head_branch']
                and row.get('baseRefName') == j['base_branch'] and row.get('headRefOid') == j['intended_head']):
            matches.append(row)
    if len(matches) > 1:
        raise ValueError('Multiple matching PRs; independent reconciliation required.')
    return matches[0] if matches else None


def record_pr(j, row):
    j.update(phase='created', url=row['url'], number=row['number'])
    save(j)
    print('PR: ' + j['url'], flush=True)


def handoff(j):
    if j.get('manual_signing'):
        manual_signed_commit(j)
    validate(j)
    gh('auth', 'status')
    if not j['base_repo']:
        resolve(j)
    else:
        info = json.loads(gh('repo', 'view', j['base_repo'], '--json', 'nameWithOwner,defaultBranchRef'))
        if info['nameWithOwner'].lower() != j['base_repo'].lower() or info['defaultBranchRef']['name'] != j['base_branch']:
            raise ValueError('Base repository changed; rerun FINAL_AUDIT.')
    if j['phase'] == 'created':
        validate(j)
        if remote_sha(j) != j['intended_head']:
            raise ValueError('PR head drifted after creation; rerun FINAL_AUDIT. Existing PR retained: ' + j['url'])
        row = lookup(j)
        if not row or row['number'] != j['number']:
            raise ValueError('Recorded PR no longer matches audited head; independent reconciliation required.')
        print('PR: ' + j['url'])
        return
    if j['phase'] in ('creating', 'unknown'):
        row = lookup(j)
        if row:
            if remote_sha(j) != j['intended_head']:
                raise ValueError('Remote drift after uncertain creation; existing PR retained; rerun FINAL_AUDIT.')
            record_pr(j, row)
            return
        raise ValueError('Prior PR outcome is unknown; independent resolution required before any new create.')
    if j['phase'] == 'bound':
        print('Audited files to commit and publish:', flush=True)
        print(git('diff', '--name-status', j['original_head'], j['commit_tree']), flush=True)
        print(git('diff', '--no-ext-diff', '--no-textconv', j['original_head'], j['commit_tree']), flush=True)
        print('Target: ' + j['base_repo'] + ':' + j['base_branch'] + ' <- ' + j['head_repo'] + ':' + j['head_branch'], flush=True)
        title = ask('PR title [default: ' + title_default() + ']: ', title_default())
        summary = ask('Work summary: ')
        manual = ask('Manual verification steps: ')
        if not summary or not manual:
            raise ValueError('Summary and manual verification steps must be nonempty; PR remains pending.')
        if ask('Commit and publish exactly this audited diff and create the PR? [y/n]: ').lower() != 'y':
            raise ValueError('Publication declined; rerun to resume PR handoff.')
        validate(j)
        if remote_sha(j) != j['remote_before']:
            raise ValueError('Remote changed during prompts; rerun FINAL_AUDIT.')
        body = '## Work summary\n\n' + summary + '\n\n## Manual verification\n\n' + manual + '\n'
        if j['origin']:
            origin = j['origin'].strip().split('\t')
            body += '\nCloses ' + origin[0] + '#' + origin[1] + '\n'
        j.update(phase='prepared', title=title, body=body)
        save(j)  # Consent and mutation intent precede commit creation.
    if j['phase'] == 'prepared':
        validate(j)
        if not j['intended_head']:
            try:
                j['intended_head'] = git('commit-tree', j['commit_tree'], '-p', j['original_head'],
                                         data=(j['title'] + '\n').encode())
            except ValueError as error:
                if not re.search(r'gpg|signing|failed to sign|no agent running|pinentry', str(error), re.I):
                    raise
                print(str(error), flush=True)
                j['manual_signing'] = True
                save(j)
                manual_signed_commit(j)
            save(j)
        current_branch = branch()
        if current_branch != j['head_branch']:
            # Branch creation precedes switching; a crash resumes the same ref.
            refs = git('for-each-ref', '--format=%(objectname)', 'refs/heads/' + j['head_branch'])
            if refs and refs != j['original_head']:
                raise ValueError('Intended branch already exists with different content.')
            if not refs:
                git('update-ref', 'refs/heads/' + j['head_branch'], j['original_head'], '0' * 40)
            git('symbolic-ref', 'HEAD', 'refs/heads/' + j['head_branch'])
        if head() == j['original_head']:
            git('update-ref', 'HEAD', j['intended_head'], j['original_head'])
        # Update only the index after the exact tree was approved; never reset,
        # stash or overwrite working files. Resuming repeats this safely.
        git('read-tree', j['commit_tree'])
        validate(j)
        remote = remote_sha(j)
        if remote != j['intended_head']:
            if remote != j['remote_before']:
                raise ValueError('Remote changed before push; rerun FINAL_AUDIT.')
            git('push', '--', j['remote'], j['intended_head'] + ':refs/heads/' + j['head_branch'])
        if remote_sha(j) != j['intended_head']:
            raise ValueError('Published SHA mismatch; rerun FINAL_AUDIT.')
        j['phase'] = 'published'
        save(j)
    validate(j)
    if remote_sha(j) != j['intended_head']:
        raise ValueError('Remote changed before PR creation; rerun FINAL_AUDIT.')
    row = lookup(j)  # Open, closed and merged PRs, before every create attempt.
    if row:
        record_pr(j, row)
        return
    validate(j)
    info = json.loads(gh('repo', 'view', j['base_repo'], '--json', 'nameWithOwner,defaultBranchRef'))
    if (info['nameWithOwner'].lower() != j['base_repo'].lower()
            or info['defaultBranchRef']['name'] != j['base_branch']):
        raise ValueError('Base repository changed during prompts; rerun FINAL_AUDIT.')
    if remote_sha(j) != j['intended_head']:
        raise ValueError('Remote changed during lookup; rerun FINAL_AUDIT.')
    j['phase'] = 'creating'
    save(j)
    fd, body = tempfile.mkstemp(prefix='uncle-pr-body-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(j['body'])
        created_url = gh('pr', 'create', '--repo', j['base_repo'], '--head',
           j['head_repo'].split('/')[0] + ':' + j['head_branch'], '--base', j['base_branch'],
           '--title', j['title'], '--body-file', body).splitlines()[-1]
        if not re.fullmatch(r'https://github\.com/' + re.escape(j['base_repo']) + r'/pull/[0-9]+', created_url, re.I):
            raise ValueError('Create returned an unexpected PR URL; independent reconciliation required.')
        j['url'] = created_url
        save(j)
        returned = json.loads(gh('pr', 'view', created_url, '--repo', j['base_repo'], '--json', 'number,headRefOid'))
        if returned['headRefOid'] != j['intended_head']:
            raise ValueError('Returned PR SHA differs from audit; existing PR retained: ' + created_url)
        row = lookup(j)
        if not row or row['number'] != returned['number']:
            raise ValueError('Created PR could not be verified; reconcile on rerun.')
        validate(j)
        if remote_sha(j) != j['intended_head']:
            raise ValueError('PR head drifted after creation; existing PR retained; rerun FINAL_AUDIT.')
        record_pr(j, row)
    except (OSError, ValueError, subprocess.SubprocessError):
        j['phase'] = 'unknown'
        save(j)
        raise
    finally:
        os.unlink(body)


def main():
    action = sys.argv[1]
    if git('rev-parse', '--show-prefix'):
        raise ValueError('PR binding requires the Git worktree root.')
    if action == 'freeze':
        if JOURNAL.exists():
            previous = load()
            if previous['phase'] in ('creating', 'unknown'):
                raise ValueError('Unresolved PR outcome; reconcile existing journal before a fresh audit.')
        j = dict(version=1, owner=uuid.uuid4().hex, origin=read(STATE / 'origin'),
                 original_head=head(), original_branch=branch(), reviewed_tree=snapshot(),
                 intended_head='', commit_tree='', audit_hash='', verdict_run='',
                 base_repo='', head_repo='', base_branch='', head_branch='',
                 phase='auditing', url='', number=None)
        save(j)
    elif action == 'bind':
        j = load()
        if (j['phase'] != 'auditing' or head() != j['original_head'] or branch() != j['original_branch']
                or snapshot() != j['reviewed_tree'] or read(STATE / 'origin') != j['origin']):
            raise ValueError('Files, origin, HEAD or branch changed during audit; rerun FINAL_AUDIT.')
        j.update(audit_hash=audit_hash(), commit_tree=snapshot(True),
                 verdict_run=read(STATE / 'audit-verdict').split('\t')[0], phase='bound')
        save(j)
    elif action == 'validate':
        j = load()
        if j.get('manual_signing'):
            manual_signed_commit(j)
        validate(j)
    elif action == 'handoff':
        handoff(load())
    else:
        raise ValueError('Unknown PR action.')

try:
    main()
except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
    print('PR pending: ' + str(error), flush=True)
    sys.exit(1)
PY
    python3 -c "$pr_code" "$@"
}
