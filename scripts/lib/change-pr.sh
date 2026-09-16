#!/usr/bin/env bash
# Bash 3.2 entry points; Python owns the atomic journal and temporary Git index.
# No close marker is written by this library.

# Whether a person can answer the handoff prompts: a terminal, or the TUI
# relay (uncle_tui.py sets UNCLE_STATUS_FILE and types answers down the pipe).
# A bare pipe grants nothing, so a headless run keeps the skip below.
change_pr_person_channel() {
    [[ -t 0 || -n "${UNCLE_STATUS_FILE:-}" ]]
}

change_pr_complete() {
    # The publication boundary. The unattended stages have ended; whether the
    # handoff dialogs open depends only on whether someone can answer them.
    # The unattended ledger never routes: an attended rerun after a headless
    # run still publishes.
    local interactive=0 boundary=0
    if [[ "$CLOSE_ISSUE" == 1 ]]; then
        if [[ "${UNATTENDED:-0}" != 1 ]]; then
            interactive=1
            if [[ -s "$UNATTENDED_FILE" ]]; then
                boundary=1
            fi
        elif change_pr_person_channel; then
            interactive=1
            boundary=1
        fi
    fi
    if [[ "$interactive" != 1 ]]; then
        # Disabled or headless: only a commit the person already made
        # continues, and no dialog may wait on anyone (EOF pends instead).
        if ! change_pr_engine completed-signing-resume >/dev/null 2>&1 </dev/null; then
            if [[ -s "$ORIGIN_FILE" ]]; then
                echo "PR handoff disabled or unattended; leaving the issue open."
            else
                echo "PR handoff disabled or unattended; no PR was created."
            fi
            return 0
        fi
        change_pr_publish 0 </dev/null
        return 0
    fi
    if [[ "$boundary" == 1 ]]; then
        echo "Publication boundary: unattended stages ended; a person answers from here."
    fi
    change_pr_publish 1
}

change_pr_publish() {
    local interactive="$1" status=0
    # The engine reads this for the override dialog only; the driver's own
    # unattended flag and ledger are untouched. Only a person may overrule.
    local -x UNCLE_UNATTENDED="${UNCLE_UNATTENDED:-0}"
    if [[ "$interactive" == 1 ]]; then
        UNCLE_UNATTENDED=0
    fi
    # Journal validation proves PR ownership separately from close ownership.
    # The close sentinel retains its existing meaning on the no-Git path.
    # Exit 3 is the one recoverable failure: the recorded verdict is not
    # READY, so the operator gets one explicit override decision, showing the
    # actual verdict. Headless runs are never asked.
    change_pr_engine validate || status=$?
    if [[ "$status" == 3 ]]; then
        if [[ "$interactive" == 1 ]] && change_pr_engine verdict-override; then
            change_pr_engine validate || return 0
        else
            return 0
        fi
    elif [[ "$status" != 0 ]]; then
        return 0
    fi
    if [[ -s "$ORIGIN_FILE" ]]; then
        local recorded verdict_class
        recorded="$(awk -F'\t' 'NR == 1 {print $1}' "$VERDICT_FILE")"
        verdict_class="$(awk -F'\t' 'NR == 1 {print $2}' "$VERDICT_FILE")"
        case "$verdict_class" in
            READY|READY_WITH_NON_BLOCKING_ISSUES)
                issue_close_eligible "$recorded" \
                    "$(origin_field "$ORIGIN_FILE" 1)" "$(origin_field "$ORIGIN_FILE" 2)" \
                    "$VERDICT_FILE" "$ORIGIN_FILE" FINAL_AUDIT.md "$MARKER_FILE" \
                    1 "$ORIGIN_BOUND" 1 "$(origin_fetch_method "$ORIGIN_FILE")" || return 0
                ;;
            *)
                # Validation passed, so an operator override exists. An
                # override creates the PR; it never closes the issue.
                echo "Final audit verdict: $verdict_class — leaving the issue open."
                ;;
        esac
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
import time
import unicodedata
import uuid

STATE = Path('.uncle/workflow')
JOURNAL = STATE / 'pr' / 'journal.json'
OVERRIDE = STATE / 'pr' / 'verdict-override'
AUDIT = Path('FINAL_AUDIT.md')


# Distinct from every other failure so the driver can tell the one case an
# operator may overrule (exit 3) from corruption that only a rerun fixes.
class NotReadyError(ValueError):
    pass


ATTESTATION = None


def attestation():
    # Imported only when sealing or rendering, so a bare load of this engine
    # (pr-reconcile-test.py) needs no library path.
    global ATTESTATION
    if ATTESTATION is None:
        lib = os.environ.get('UNCLE_LIB_DIR') or 'scripts/lib'
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import attestation as module
        ATTESTATION = module
    return ATTESTATION


def seal_attestation(j):
    # Sealed from driver state only, at bind: after the last agent stage.
    return attestation().seal(j, STATE, root='.', version=os.environ.get('UNCLE_VERSION', ''),
                              lib=os.environ.get('UNCLE_LIB_DIR') or 'scripts/lib')


def sealed_attestation(j):
    # The bind seal, plus the rows the driver itself writes after bind. A
    # journal bound before attestation existed is sealed now; validate() has
    # just proved it still names this audited change.
    sealed = j.get('attestation')
    if not isinstance(sealed, dict):
        sealed = seal_attestation(j)
    return attestation().amend(sealed, j, STATE)


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


def override_record():
    return read(OVERRIDE).strip().split('\t')


# An override authorizes exactly one audited verdict: any rerun of the audit
# or a different verdict class brings the dialog back.
def override_allows(j, verdict):
    record = override_record()
    return (len(record) == 4 and record[0] == j['verdict_run']
            and record[1] == verdict and record[2] == j['audit_hash'])


def validate(j, ready=True):
    if 'manual_signed_head' in j and j['manual_signed_head'] != j['intended_head']:
        raise ValueError('Signed handoff marker differs from intended HEAD.')
    if j['origin'] != read(STATE / 'origin') or j['audit_hash'] != audit_hash():
        raise ValueError('Origin or audit changed; rerun FINAL_AUDIT.')
    check_remotes(j)
    verdict = read(STATE / 'audit-verdict').strip().split('\t')
    if len(verdict) != 3 or verdict[0] != j['verdict_run'] or verdict[2] != j['audit_hash']:
        raise ValueError('Verdict binding changed; rerun FINAL_AUDIT.')
    if ready and verdict[1] not in ('READY', 'READY_WITH_NON_BLOCKING_ISSUES'):
        if not override_allows(j, verdict[1]):
            raise NotReadyError('PR requires an owned READY verdict.')
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
    # Stage the exact reviewed tree, including untracked files, without
    # reapplying clean filters or changing working files. Only the user runs it.
    command = ('git read-tree ' + shlex.quote(j['commit_tree'])
               + ' && git commit ' + ('-S ' if j.get('requires_signature', True) else '--no-gpg-sign ')
               + '-m ' + shlex.quote(j['title']))
    if os.environ.get('UNCLE_SIGNING_JSON') == '1':
        block = json.dumps(command) + ' '
    else:
        block = 'In another terminal, open this project, review the audited changes, then run:\n' + command + '\n'
    candidate = head()
    while candidate == j['original_head']:
        prefix = 'Commit signing needs your help. ' if j.get('requires_signature', True) else 'Commit needs your help. '
        ask(prefix + block +
            'Return here and press ENTER (OK) when finished: ')
        candidate = head()
        if candidate == j['original_head']:
            if ask('No new commit found. Keep the commit dialog open? [y/n]: ').lower() != 'y':
                raise ValueError('No new commit found; PR remains pending. Finish the commit and resume.')
    if git('rev-parse', candidate + '^{tree}') != j['commit_tree']:
        raise ValueError('Manual commit differs from the audited files; rerun FINAL_AUDIT.')
    if git('rev-list', '--parents', '-n', '1', candidate).split() != [candidate, j['original_head']]:
        raise ValueError('Manual commit must have the audited HEAD as its only parent.')
    if j.get('requires_signature', True):
        git('verify-commit', candidate)
    previous = j['intended_head']
    j['intended_head'] = candidate
    try:
        validate(j)
    except Exception:
        j['intended_head'] = previous
        raise
    j['manual_signed_head'] = candidate
    j.pop('manual_signing', None)
    save(j)



def signing_resume(j):
    # Probe only: preserve the journal and ask/validate again during handoff.
    if j['phase'] not in ('prepared', 'published', 'creating', 'unknown', 'created'):
        raise ValueError('No prepared signing handoff.')
    marker = j.get('manual_signed_head')
    if marker is not None and marker != j['intended_head']:
        raise ValueError('Signed handoff marker differs from intended HEAD.')
    candidate = head()
    if j.get('manual_signing'):
        if j['phase'] != 'prepared':
            raise ValueError('Invalid pending signing phase.')
        if candidate == j['original_head']:
            validate(j)
            return
    elif not j['intended_head'] or candidate != j['intended_head']:
        raise ValueError('No current signed handoff commit.')
    if git('rev-parse', candidate + '^{tree}') != j['commit_tree']:
        raise ValueError('Signed handoff tree differs from audit.')
    if git('rev-list', '--parents', '-n', '1', candidate).split() != [candidate, j['original_head']]:
        raise ValueError('Signed handoff must have the audited HEAD as its only parent.')
    if j.get('requires_signature', True):
        git('verify-commit', candidate)
    validate(dict(j, intended_head=candidate))


def prepare_commit(j):
    # Read-only detection; git merges system, global, local, include,
    # includeIf, worktree and environment levels itself. Only a definite
    # "off" reading commits automatically; "on" and unreadable both hand the
    # commit to the person, who signs.
    setting = subprocess.run(['git', 'config', '--bool', '--get', 'commit.gpgsign'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if setting.returncode not in (0, 1):
        print('Cannot read commit signing configuration; the commit needs your signature: '
              + setting.stderr.strip().split('\n')[0], flush=True)
        j['requires_signature'] = True
    elif setting.stdout.strip() == 'true':
        j['requires_signature'] = True
    else:
        j['requires_signature'] = False
        automatic_commit(j)
        return
    j['manual_signing'] = True
    save(j)  # Record the pending user action before displaying it.
    manual_signed_commit(j)


SIGNING_ERROR = re.compile(r'(?i)sign|gpg|pinentry|ssh-keygen')


def automatic_commit(j):
    # One object, no sign flag: git's own configuration still decides. If git
    # reports a signing failure anyway, the person signs instead.
    try:
        candidate = git('commit-tree', j['commit_tree'], '-p', j['original_head'], '-m', j['title'])
    except ValueError as error:
        stderr = str(error).split('\n', 1)[1] if '\n' in str(error) else ''
        if not SIGNING_ERROR.search(stderr):
            raise
        reason = stderr.strip().split('\n')[0]
        j.update(requires_signature=True, manual_signing=True, signing_fallback=reason)
        save(j)
        print('Automatic commit failed; git requires a signature: ' + reason, flush=True)
        manual_signed_commit(j)
        return
    j['intended_head'] = candidate
    try:
        validate(j)
    except Exception:
        j['intended_head'] = ''
        raise
    save(j)



GATE = None


def gate():
    """The gate-identity helper (receipts for supervisor-relayed answers); a
    bare load of this engine without the library path has none."""
    global GATE
    if GATE is None:
        lib = os.environ.get('UNCLE_LIB_DIR') or 'scripts/lib'
        if lib not in sys.path:
            sys.path.insert(0, lib)
        try:
            import gate_answer
            GATE = gate_answer.Gate()
        except ImportError:
            GATE = False
    return GATE or None


def ask(prompt, default=None):
    helper = gate()
    if helper is not None:
        # Every handoff prompt decides publication; the signing prefix takes
        # precedence in the classifier. Standing delegation never answers either.
        helper.open(prompt, signing=prompt.startswith(('Commit signing needs your help.', 'Commit needs your help.')),
                    class_hint='sensitive:publication')
    try:
        if sys.stdin.isatty() and default is not None:
            import readline
            readline.set_startup_hook(lambda: readline.insert_text(default))
            try:
                answer = input(prompt)
            finally:
                readline.set_startup_hook(None)
        elif sys.stdin.isatty():
            answer = input(prompt)
        else:
            # Read exactly one answer. TextIO buffering can consume answers
            # intended for the next engine process (override then handoff).
            print(prompt, end='', flush=True)
            data = bytearray()
            while True:
                char = os.read(sys.stdin.fileno(), 1)
                if not char:
                    if not data:
                        raise EOFError
                    break
                if char == b'\n':
                    break
                data.extend(char)
            answer = data.decode('utf-8')
    except EOFError:
        if helper is not None:
            helper.read('')
        raise ValueError('No answer received; PR remains pending. Rerun to resume.')
    if helper is not None:
        # Attribution comes from the receipt alone; the answer is used as read.
        os.environ['UNCLE_GATE_ANSWERED_BY'] = helper.read(answer)
    return answer.strip() or default or ''


def title_default():
    text = read(Path('CHANGE_REQUEST.md'))
    match = re.search(r'^##\s+(?:\d+\.\s+)?Summary\s*\n(.*?)(?=^##\s|\Z)', text, re.M | re.S | re.I)
    title = match.group(1) if match else ''
    title = ''.join(' ' if unicodedata.category(c).startswith('C') else c for c in title)
    return ' '.join(title.split())[:72].strip() or 'Completed change'


def slug_text():
    path = Path('CHANGE_REQUEST.md')
    text = read(path if path.exists() else Path('REQUIREMENTS.md'))
    match = re.search(r'^##\s+(?:\d+\.\s+)?Summary\s*\n(.*?)(?=^##\s|\Z)', text, re.M | re.S | re.I)
    if match:
        return match.group(1)
    match = re.search(r'^# ([^\n]*)', text, re.M)
    return match.group(1) if match else ''


def slug(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')[:40].strip('-') or 'change'


def label_prefix(origin):
    fields = origin.strip().split('\t')
    if len(fields) != 3 or fields[2] != 'gh':
        return 'uncle/'
    try:
        result = subprocess.run(['gh', 'issue', 'view', fields[1], '--repo', fields[0],
                                 '--json', 'labels'], capture_output=True, text=True,
                                timeout=int(os.environ.get('STAGEGATE_CLOSE_TIMEOUT', '30')))
        if result.returncode:
            raise ValueError('Label lookup failed')
        labels = {label['name'].casefold() for label in json.loads(result.stdout)['labels']}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError):
        print('Label lookup failed; using uncle/ prefix', flush=True)
        return 'uncle/'
    for label, prefix in [('enhancement', 'feat/'), ('bug', 'bug/'), ('documentation', 'doc/')]:
        if label in labels:
            return prefix
    return 'uncle/'


def branch_name(j):
    return label_prefix(j['origin']) + slug(slug_text()) + '-' + j['owner'][:12]


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


def remote_configuration():
    # Effective fetch and push URLs per remote, captured verbatim: an invalid
    # destination must not block the audit, only the handoff that uses it.
    config = {}
    for remote in git('remote').splitlines():
        config[remote] = [git('remote', 'get-url', '--all', remote).splitlines(),
                          git('remote', 'get-url', '--push', '--all', remote).splitlines()]
    return config


def check_remotes(j):
    # An origin-less run has no issue naming its destination, so the audit
    # binds the remote configuration instead. Journals bound before this field
    # existed fail closed; the guard is never backfilled.
    if j['origin']:
        return
    recorded = j.get('audit_remotes')
    well_formed = (isinstance(recorded, dict) and all(
        isinstance(name, str) and isinstance(urls, list) and len(urls) == 2
        and all(isinstance(group, list) and all(isinstance(url, str) for url in group) for group in urls)
        for name, urls in recorded.items()))
    if not well_formed or recorded != remote_configuration():
        raise ValueError('Remote configuration changed; rerun FINAL_AUDIT.')


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
    if not remotes and origin == ['']:
        # No issue names a destination and nothing can be derived: fail before
        # any prompt or remote mutation; the bound journal resumes after repair.
        raise ValueError('No Git remote is configured; add a GitHub remote and rerun to resume PR handoff.')
    if not remotes:
        url = ask('No Git remote is configured. GitHub remote URL for this PR (blank to cancel): ')
        if not url:
            raise ValueError('PR destination not configured; resume publication after adding a remote.')
        identity = remote_repo(url)
        if origin != [''] and identity.lower() != origin[0].lower():
            fork = json.loads(gh('api', 'repos/' + identity))
            if not fork.get('fork') or fork.get('parent', {}).get('full_name', '').lower() != origin[0].lower():
                raise ValueError('Destination must match the issue repository or its direct fork; no remote was added.')
        git('remote', 'add', 'origin', url)
        remotes = ['origin']
    identities = {r: remote_identity(r) for r in remotes}
    if origin != ['']:
        if len(origin) == 2 and origin[1].isdigit():
            # Older runs saved repo + number without a fetch-provider field.
            # Verify that identity now; retain the original bound journal bytes.
            base = repo_name(origin[0])
            issue = json.loads(gh('api', 'repos/' + base + '/issues/' + origin[1]))
            if (issue.get('number') != int(origin[1]) or issue.get('pull_request')
                    or str(issue.get('html_url', '')).lower() != ('https://github.com/' + base + '/issues/' + origin[1]).lower()):
                raise ValueError('Legacy issue origin could not be verified with GitHub.')
        elif len(origin) != 3 or origin[2] != 'gh' or not origin[1].isdigit():
            raise ValueError('Only a gh-fetched origin authorizes this PR.')
        base = repo_name(origin[0])
    else:
        # Base derived from the remotes, never asked: upstream, else origin,
        # else the sole remote. Anything else fails closed and resumable.
        for name in ('upstream', 'origin'):
            if name in identities:
                base = identities[name]
                break
        else:
            if len(identities) != 1:
                raise ValueError('Ambiguous base remote; name one remote origin or upstream.')
            base = next(iter(identities.values()))
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
        target = branch_name(j)
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


def reconcile_absent(j):
    """Independently confirm no PR exists before retrying approved creation."""
    from urllib.parse import urlencode
    if j.get('url'):
        raise ValueError('A prior create returned a PR URL; resolve that PR before retrying.')
    query = urlencode(dict(state='all', head=j['head_repo'].split('/')[0] + ':' + j['head_branch'],
                           base=j['base_branch'], per_page=100))
    rows = json.loads(gh('api', 'repos/' + j['base_repo'] + '/pulls?' + query))
    if not isinstance(rows, list):
        raise ValueError('PR outcome remains unknown: independent reconciliation returned an invalid response.')
    if rows:
        raise ValueError('A PR exists for this branch; reconcile its identity before retrying creation.')
    validate(j)
    if remote_sha(j) != j['intended_head']:
        raise ValueError('Remote changed during PR reconciliation; rerun FINAL_AUDIT.')
    j['phase'] = 'published'
    save(j)
    print('No existing PR found by independent lookup; resuming approved creation.', flush=True)


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
        reconcile_absent(j)
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
        record = override_record()
        if len(record) == 4 and record[0] == j['verdict_run'] and record[2] == j['audit_hash']:
            # An overridden verdict is not a READY verdict; the PR says so.
            body = ('> Created by operator override over a **' + record[1]
                    + '** audit verdict.\n\n') + body
        # The consent just given is the publication gate; only a person at the
        # terminal reaches this line, so it is the one field stamped here.
        sealed = sealed_attestation(j)
        sealed['gate_publication'] = 'APPROVED (human)'
        j['attestation'] = sealed
        body = attestation().attach_body(body, sealed)
        if j['origin']:
            origin = j['origin'].strip().split('\t')
            body += '\nCloses ' + origin[0] + '#' + origin[1] + '\n'
        j.update(phase='prepared', title=title, body=body)
        save(j)  # Consent and mutation intent precede commit creation.
    if j['phase'] == 'prepared':
        validate(j)
        if not j['intended_head']:
            prepare_commit(j)
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
    if attestation().MARKER not in j['body']:
        # A journal prepared before attestation existed; validate() just
        # passed, so the seal describes this audited change. Once only.
        j['attestation'] = sealed_attestation(j)
        j['body'] = attestation().attach_body(j['body'], j['attestation'])
        save(j)
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
        if not j['origin']:
            j['audit_remotes'] = remote_configuration()
        save(j)
    elif action == 'bind':
        j = load()
        if (j['phase'] != 'auditing' or head() != j['original_head'] or branch() != j['original_branch']
                or snapshot() != j['reviewed_tree'] or read(STATE / 'origin') != j['origin']):
            raise ValueError('Files, origin, HEAD or branch changed during audit; rerun FINAL_AUDIT.')
        check_remotes(j)
        j.update(audit_hash=audit_hash(), commit_tree=snapshot(True),
                 verdict_run=read(STATE / 'audit-verdict').split('\t')[0], phase='bound')
        # Sealed here, after the last agent stage and before any handoff.
        j['attestation'] = seal_attestation(j)
        save(j)
    elif action == 'validate':
        j = load()
        if j.get('manual_signing'):
            manual_signed_commit(j)
        validate(j)
    elif action == 'verdict-override':
        j = load()
        verdict = read(STATE / 'audit-verdict').strip().split('\t')
        if len(verdict) != 3 or verdict[0] != j['verdict_run'] or verdict[2] != j['audit_hash']:
            raise ValueError('Verdict binding changed; rerun FINAL_AUDIT.')
        if verdict[1] in ('READY', 'READY_WITH_NON_BLOCKING_ISSUES'):
            return
        if os.environ.get('UNCLE_UNATTENDED') == '1':
            raise NotReadyError('PR requires an owned READY verdict.')
        answer = ask('The audit verdict is ' + verdict[1] +
                     ', not READY. Create the PR anyway? [y/N]: ')
        if answer.lower() not in ('y', 'yes'):
            raise ValueError('Publication declined; PR remains pending.')
        OVERRIDE.write_text('\t'.join([j['verdict_run'], verdict[1], j['audit_hash'],
                                       time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())]) + '\n')
        print('Override recorded; creating the PR over a ' + verdict[1] + ' verdict.', flush=True)
    elif action == 'signing-resume':
        signing_resume(load())
    elif action == 'completed-signing-resume':
        # Headless probe: a commit the person already made resumes; an
        # unchanged HEAD would reopen a dialog nobody is there to answer.
        j = load()
        if head() == j['original_head']:
            raise ValueError('No completed signed handoff commit.')
        signing_resume(j)
    elif action == 'handoff':
        handoff(load())
    else:
        raise ValueError('Unknown PR action.')

try:
    main()
except NotReadyError as error:
    print('PR pending: ' + str(error), flush=True)
    sys.exit(3)
except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError) as error:
    if ATTESTATION is not None and isinstance(error, ATTESTATION.AttestationError):
        # Recoverable like NotReady (exit 3) but not overridable: the
        # audited state is unusable, so no PR is created.
        print('PR pending: Attestation blocked: ' + str(error), flush=True)
        sys.exit(3)
    print('PR pending: ' + str(error), flush=True)
    sys.exit(1)
PY
    # The attestation module lives beside this file; the driver may override.
    UNCLE_LIB_DIR="${UNCLE_LIB_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" \
        python3 -c "$pr_code" "$@"
}
