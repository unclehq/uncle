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


# Raised only by `start`, which runs before any stage: the message names a
# branch problem, not a pending PR.
class StartError(ValueError):
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
    # just proved it still names this audited change. Once a Statement exists
    # the PR block is rendered from its predicate, never from a second seal.
    if isinstance(j.get('statement'), dict):
        return attestation().amend(attestation().from_statement(j['statement']), j, STATE)
    sealed = j.get('attestation')
    if not isinstance(sealed, dict):
        sealed = seal_attestation(j)
    return attestation().amend(sealed, j, STATE)


ENVELOPE = None
ATTESTATION_FILES = ('.uncle/attestation.json', '.uncle/attestation.sig')


def envelope():
    # The envelope/Statement module beside attestation.py; imported lazily for
    # the same reason.
    global ENVELOPE
    if ENVELOPE is None:
        lib = os.environ.get('UNCLE_LIB_DIR') or 'scripts/lib'
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import envelope as module
        ENVELOPE = module
    return ENVELOPE


def envelopes_enabled():
    # Attestation is enforced for every run whose driver created envelopes/;
    # a manifest without the directory is a directory that went missing.
    return (STATE / 'envelopes').is_dir() or (STATE / 'envelopes.manifest').exists()


def gate_names():
    names = set()
    for path in (STATE / 'approvals').glob('*'):
        if path.suffix in ('.sha256', '.gate-action'):
            names.add(path.name[:-len(path.suffix)])
    return sorted(names)


def blocking_findings():
    """The audit rows that block release, as short lines. Never raises."""
    try:
        text = Path('FINAL_AUDIT.md').read_text(errors='replace')
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith('|'):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) < 3 or cells[-1].upper() not in ('YES', '**YES**'):
            continue
        rows.append('%s  %s  %s' % (cells[0], cells[1] if len(cells) > 1 else '', cells[2][:96]))
    return rows


def blocked_gate(reason):
    """Show why publication is refused, and let the operator read the findings.

    The other blocked gates in this workflow ask rather than announce, and this
    one announced: it printed a line and exited, leaving the operator to open
    FINAL_AUDIT.md themselves to learn what was wrong.

    Skipping publishes anyway. It never turns a failing audit into a passing
    one: the release envelope still records `fail` and its reason, the Statement
    still carries them, and the PR opens with the blocking findings at the top
    so the first thing any reviewer reads is what the audit refused. A PR is a
    proposal under review, not a merge, which is why this is the operator's call
    to make -- but it is made on the record, not by quietly clearing the flag.
    """
    rows = blocking_findings()
    while True:
        print('', flush=True)
        print('Not publishing: ' + reason, flush=True)
        if rows:
            print('%d finding%s block this change:' % (len(rows), '' if len(rows) == 1 else 's'), flush=True)
            for row in rows[:8]:
                print('  ' + row, flush=True)
        print('Fix the findings and rerun FINAL_AUDIT, stop here and come back to', flush=True)
        print('it, or skip -- which publishes with these findings quoted in the PR', flush=True)
        print('and recorded as a failed release. It does not mark the audit passed.', flush=True)
        answer = ask('Blocked publication: [r]eview, [s]top, or s[k]ip and publish anyway? ',
                     's').strip().lower()
        if answer in ('r', 'review'):
            try:
                print(Path('FINAL_AUDIT.md').read_text(errors='replace'), flush=True)
            except OSError as failure:
                print('Could not read FINAL_AUDIT.md: %s' % failure, flush=True)
            continue
        if answer in ('k', 'skip'):
            # Typed in full: a single keystroke is too small a gesture for
            # publishing over an audit that says the change is broken.
            confirm = ask('Type "publish over the audit" to confirm: ', '').strip().lower()
            if confirm != 'publish over the audit':
                print('Not confirmed; publication remains blocked.', flush=True)
                continue
            return 'skip'
        return 'stop'


def release_blocked_reason(j):
    """Why release would be refused, or '' -- computed without asking anything.

    A preview of the check `write_attestation` performs after consent. When it
    blocks, the refusal is recorded exactly as the post-consent path records it:
    a `release` envelope with result `fail`. That envelope is the evidence that
    publication was refused and why, so skipping it to save the operator four
    questions would trade a record for a convenience.

    Any failure to work it out returns '': this exists to spare the operator
    questions, never to refuse a publication the real gate would have allowed.
    """
    if not envelopes_enabled():
        return ''
    try:
        env = envelope()
        if not (STATE / 'envelopes').is_dir():
            return ''
        artifact = snapshot(excludes=env.ARTIFACT_EXCLUDES)
        reason = env.blocking_reason(env.load_envelopes(STATE), artifact)
    except Exception:
        return ''
    if not reason:
        return ''
    override = override_entry(j)
    if override:
        reason += '; the override is recorded but does not release'
    try:
        extra = {'approvals': [env.approval_entry(STATE, name) for name in gate_names()]}
        if override:
            extra['override'] = override
        release = env.write_envelope(STATE, 'release', 'fail', reason=reason, artifact=artifact,
                                     inputs={'artifact': artifact}, evidence=['FINAL_AUDIT.md'],
                                     extra=extra)
        print('Envelope: release ' + release['result'], flush=True)
    except Exception:
        return ''          # cannot record the refusal: let the real gate handle it
    return reason


def consent_entry(artifact):
    # The consent just given: a person at the terminal, or a supervisor
    # receipt relayed for one. Only the former counts as human.
    env = envelope()
    answered = os.environ.get('UNCLE_GATE_ANSWERED_BY', '')
    delegated = answered if env.DELEGATED.match(answered) else ''
    approved = '' if delegated else (answered or os.environ.get('UNCLE_APPROVAL_NAME', '') or 'operator')
    return {'gate': 'publication', 'required': True, 'approved_by': approved,
            'delegated_by': delegated, 'digest': artifact, 'timestamp': env.utc_now()}


def override_entry(j):
    if (STATE / 'audit-override').exists():
        entry = envelope().approval_entry(STATE, 'FINAL_AUDIT_OVERRIDE')
        return {'gate': 'FINAL_AUDIT_OVERRIDE', 'approved_by': entry['approved_by'], 'delegated_by': entry['delegated_by']}
    record = override_record()
    if len(record) == 4 and record[0] == j['verdict_run'] and record[2] == j['audit_hash']:
        return {'gate': 'verdict-override', 'approved_by': os.environ.get('UNCLE_APPROVAL_NAME', '') or 'operator', 'delegated_by': ''}
    original = read(STATE / 'audit-verdict.original').strip().split('\t')
    if len(original) == 3 and original[2] == j['audit_hash'] and original[1] == 'NOT_READY':
        return {'gate': 'audit-findings', 'approved_by': os.environ.get('UNCLE_APPROVAL_NAME', '') or 'operator', 'delegated_by': ''}
    return None


def attest(j):
    """After consent: the release envelope, the Statement and its signature,
    written into the working tree and appended to the commit tree. Refuses
    before any git write when the blocking policy says so."""
    env = envelope()
    error = attestation().AttestationError
    if not (STATE / 'envelopes').is_dir():
        raise error('envelopes directory is missing but its manifest exists; rerun FINAL_AUDIT')
    artifact = snapshot(excludes=env.ARTIFACT_EXCLUDES)
    try:
        envelopes = env.load_envelopes(STATE)
    except env.EnvelopeError as failure:
        raise error(str(failure)) from failure
    approvals = [env.approval_entry(STATE, name) for name in gate_names()] + [consent_entry(artifact)]
    override = override_entry(j)
    reason = env.blocking_reason(envelopes, artifact)
    if reason and override:
        reason += '; the override is recorded but does not release'
    extra = {'approvals': approvals}
    if override:
        extra['override'] = override
    release = env.write_envelope(STATE, 'release', 'fail' if reason else 'pass', reason=reason, artifact=artifact,
                                 inputs={'artifact': artifact}, evidence=['FINAL_AUDIT.md'], extra=extra)
    print('Envelope: release ' + release['result'], flush=True)
    if reason and j.get('release_skipped') == reason:
        # The envelope above already says `fail` and why; the Statement carries
        # it. Publishing proceeds because the operator said so at the gate, on
        # the record -- nothing here is rewritten to look like a pass.
        print('Release refused by policy; publishing anyway at the operator\'s', flush=True)
        print('recorded instruction. The envelope and Statement record the refusal.', flush=True)
    elif reason:
        raise error(reason)
    envelopes['release'] = release
    method, detail = env.select_signer()
    origin = j['origin'].strip().split('\t')
    source = {'repository': j['base_repo'], 'issue': origin[1] if len(origin) >= 2 and origin[1].isdigit() else ''}
    run_id = os.environ.get('STAGEGATE_RUN_ID', '') or j['verdict_run']
    import supervisor
    known = supervisor.known_secret_values()

    def build(authentication):
        stmt = env.statement(j['head_repo'] + '@' + j['head_branch'], artifact, envelopes, approvals, source,
                             authentication, os.environ.get('UNCLE_VERSION', ''), run_id)
        return env.filter_strings(stmt, '.', known=known)

    stmt = build(method)
    payload = env.canonical(stmt)
    sig = None
    if method != 'none':
        sig, failure = env.sign(payload, method, detail)
        if sig is None:
            print('Signing failed: ' + failure + '; attestation written unauthenticated', flush=True)
            method = 'none'
            stmt = build(method)
            payload = env.canonical(stmt)
    write_attestation_files(payload, sig)
    j['statement'] = stmt
    j['signature'] = sig
    j['audited_tree'] = j['commit_tree']
    j['commit_tree'] = snapshot(True, attestation=True)
    print('Attestation: ' + method + ' ' + artifact[:12], flush=True)


def write_attestation_files(payload, sig):
    Path('.uncle').mkdir(exist_ok=True)
    target = Path(ATTESTATION_FILES[0])
    if not target.exists() or target.read_bytes() != payload:
        target.write_bytes(payload)
    sig_path = Path(ATTESTATION_FILES[1])
    if sig is None:
        if sig_path.exists():
            sig_path.unlink()
    else:
        data = envelope().canonical(sig)
        if not sig_path.exists() or sig_path.read_bytes() != data:
            sig_path.write_bytes(data)


def restore_attestation_files(j):
    # Resuming at `prepared`: the files come back from the journal, byte for
    # byte, so the stored signature stays valid and the commit tree unchanged.
    write_attestation_files(envelope().canonical(j['statement']), j.get('signature'))


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


def snapshot(audit=False, excludes=(), attestation=False):
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
            name = os.fsdecode(raw)
            # The attestation names the tree it is committed into, so the
            # files carrying it are never part of the walk; they are appended
            # under the `attestation` flag, like FINAL_AUDIT.md under `audit`.
            if name in ATTESTATION_FILES:
                continue
            if any(name.startswith(x) if x.endswith('/') else name == x for x in excludes):
                continue
            path = Path(name)
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
        if attestation:
            for name in ATTESTATION_FILES:
                path = Path(name)
                if not path.is_file() or path.is_symlink():
                    continue
                oid = git('hash-object', '-w', '--no-filters', '--stdin', data=path.read_bytes())
                entries.append(b'100644 ' + oid.encode() + b'\t' + name.encode() + b'\0')
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
    phases = ('auditing', 'bound', 'prepared', 'published', 'creating', 'created', 'unknown')
    if isinstance(j, dict) and j.get('version') == 2:
        # Version 2 (Issue 60): the journal may begin at `start`, before any
        # stage, and records whether the head ref was claimed then.
        required = required | {'early_ref'}
        phases += ('started',)
    if (not isinstance(j, dict) or not required <= j.keys() or j['version'] not in (1, 2)
            or not isinstance(j['owner'], str) or not re.fullmatch(r'[0-9a-f]{32}', j['owner'])
            or not isinstance(j.get('early_ref', False), bool) or j['phase'] not in phases):
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
    # With a Statement the commit tree also carries the attestation files.
    committed = snapshot(True, attestation=True) if isinstance(j.get('statement'), dict) else snapshot(True)
    if snapshot() != j['reviewed_tree'] or committed != j['commit_tree']:
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


def signing_reason(reason):
    # One decoded, whitespace-collapsed line so the prompt stays a prompt.
    if isinstance(reason, bytes):
        reason = reason.decode('utf-8', 'replace')
    return ' '.join(str(reason).split())[:240]


def manual_signed_commit(j, reason=None):
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
    # The classifier in ask() keys on the leading sentence, so the reason
    # follows it rather than replacing it.
    explanation = 'Automatic unsigned commit failed: ' + signing_reason(reason) + '. ' if reason else ''
    candidate = head()
    while candidate == j['original_head']:
        prefix = 'Commit signing needs your help. ' if j.get('requires_signature', True) else 'Commit needs your help. '
        ask(prefix + explanation + block +
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
    setting = subprocess.run(['git', 'config', '--includes', '--bool', '--get', 'commit.gpgsign'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    reason = None
    if setting.returncode not in (0, 1):
        reason = ('cannot read commit signing configuration: '
                  + setting.stderr.strip().split('\n')[0])
        print('Cannot read commit signing configuration; the commit needs your signature: '
              + setting.stderr.strip().split('\n')[0], flush=True)
        j['requires_signature'] = True
    elif setting.stdout.strip() == 'true':
        j['requires_signature'] = True
    else:
        j['requires_signature'] = False
        j.pop('manual_signing', None)
        automatic_commit(j)
        return
    j['manual_signing'] = True
    save(j)  # Record the pending user action before displaying it.
    manual_signed_commit(j, reason)


SIGNING_ERROR = re.compile(r'(?i)sign|gpg|pinentry|ssh-keygen')


def automatic_commit(j):
    # Stage the exact audited tree and let normal hooks run. The explicit flag
    # prevents inherited configuration from invoking the user's signer.
    git('read-tree', j['commit_tree'])
    committed = subprocess.run(['git', 'commit', '--no-gpg-sign', '-m', j['title']],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if committed.returncode:
        reason = committed.stderr.strip()
        if not SIGNING_ERROR.search(committed.stderr):
            raise ValueError('Automatic commit failed: ' + reason.split('\n')[0])
        j.update(requires_signature=True, manual_signing=True,
                 signing_fallback=reason.split('\n')[0])
        save(j)
        print('Automatic commit failed; git requires a signature: '
              + reason.split('\n')[0], flush=True)
        manual_signed_commit(j, reason)
        return
    candidate = head()
    j.pop('manual_signing', None)
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


COLLISION = 'Intended branch already exists with different content.'


def early_ref_oid(j):
    return git('for-each-ref', '--format=%(objectname)', 'refs/heads/' + j['head_branch'])


def claim_ref(j):
    # The one mutation `start` makes: a local ref at the starting HEAD, created
    # only if absent (zero old-OID). An existing ref is accepted only at that
    # OID; anything else is someone's branch and is never moved.
    # Nothing to claim only when the target is the branch the operator was
    # already on. original_branch now names this run's own branch once start
    # has moved HEAD, so comparing against it would skip the claim entirely --
    # and with it the collision check that protects someone else's ref.
    if j['head_branch'] == (j.get('base_checkout_branch') or j['original_branch']):
        return
    existing = early_ref_oid(j)
    if existing == j['original_head']:
        return
    if existing:
        raise StartError(COLLISION)
    git('update-ref', 'refs/heads/' + j['head_branch'], j['original_head'], '0' * 40)


def default_branch(remotes):
    # Only a unique local refs/remotes/<remote>/HEAD identifies the default
    # branch without GitHub access; anything else defers naming to resolve().
    found = set()
    for row in git('for-each-ref', '--format=%(refname)\t%(symref)', 'refs/remotes/').splitlines():
        name, _, target = row.partition('\t')
        match = re.fullmatch(r'refs/remotes/([^/]+)/HEAD', name)
        if match and match.group(1) in remotes and target.startswith('refs/remotes/' + match.group(1) + '/'):
            found.add(target[len('refs/remotes/' + match.group(1) + '/'):])
    return next(iter(found)) if len(found) == 1 else None


def restore_unborn_head():
    """Repair a HEAD left pointing at a branch that no longer exists.

    `start` moves HEAD onto the branch it creates so the run's work never lands
    on the default branch. That leaves one way to break the checkout that did
    not exist before: if something outside the run deletes or renames that
    branch, HEAD names a ref with no commit, `git rev-parse HEAD` fails, and
    every tracked file reads as newly added. The working tree is untouched --
    only the pointer is wrong -- so this puts it back on the branch the run
    started from and lets the caller report the real problem.

    Returns the restored branch name, or '' when there is nothing to repair or
    nothing safe to repair it with.
    """
    if not JOURNAL.exists():
        return ''
    if subprocess.run(['git', 'rev-parse', '--verify', '-q', 'HEAD'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        return ''                       # HEAD resolves; nothing is broken
    try:
        j = load()
    except ValueError:
        return ''
    base = j.get('base_checkout_branch')
    if not base:
        return ''                       # pre-switch journal: not ours to fix
    # Only onto a branch that exists and still holds the commit the run began
    # at. Anything else would move the checkout somewhere the operator did not
    # leave it, which is worse than reporting an unborn HEAD.
    if git('for-each-ref', '--format=%(objectname)', 'refs/heads/' + base) != j['original_head']:
        return ''
    git('symbolic-ref', 'HEAD', 'refs/heads/' + base)
    return base


def restore_moved_head():
    """Put HEAD back when uncle's own branch was moved out from under it.

    Deleting the run's branch leaves HEAD unborn, which is loud. Moving it is
    silent and worse: HEAD is a symbolic ref, so the operator's checkout
    follows the branch to a commit this run never created, while the working
    tree still holds the original content.

    Only while the run is still `started`. Once an audit has bound a commit,
    HEAD advancing is the run's own doing, not tampering, and moving it back
    would undo legitimate work.

    Returns the branch HEAD was restored to, or '' when there is nothing to do.
    """
    if not JOURNAL.exists():
        return ''
    try:
        j = load()
    except ValueError:
        return ''
    base = j.get('base_checkout_branch')
    if not base or j.get('phase') != 'started' or not j.get('head_branch'):
        return ''
    if branch() != j['head_branch'] or head() == j['original_head']:
        return ''
    # Only back onto a branch still holding the commit the run began at;
    # anything else is not the position the operator left.
    if git('for-each-ref', '--format=%(objectname)', 'refs/heads/' + base) != j['original_head']:
        return ''
    git('symbolic-ref', 'HEAD', 'refs/heads/' + base)
    return base


def started_journal():
    # A `started` journal that still describes this checkout; None otherwise.
    if not JOURNAL.exists():
        return None
    j = load()
    if j['phase'] != 'started' or j['original_head'] != head() or j['original_branch'] != branch():
        return None
    return j


def start():
    try:
        start_build()
    except ValueError as error:
        raise StartError(str(error)) from error


def start_build():
    if git('rev-parse', '--show-prefix'):
        return
    if subprocess.run(['git', 'rev-parse', '--verify', '-q', 'HEAD'], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        return  # unborn HEAD: nothing to branch from
    current_branch = git('branch', '--show-current')
    remotes = git('remote').splitlines()
    if not current_branch or not remotes:
        return  # detached HEAD or no remote: today's path, no journal
    if JOURNAL.exists():
        try:
            j = load()
        except ValueError:
            return  # left for the audit, which reports it today
        if j['phase'] != 'started':
            return  # an audit or handoff owns this journal
        # After a repair the checkout sits on base_checkout_branch rather than
        # the branch the journal recorded. That is still this run's journal, and
        # resuming it is what re-runs claim_ref -- so a candidate ref someone
        # else moved is reported as a collision instead of being quietly stepped
        # around with a fresh name.
        if j['original_head'] == head() and current_branch in (
                j['original_branch'], j.get('base_checkout_branch')):
            if j['early_ref']:
                claim_ref(j)
            return
    j = dict(version=2, owner=uuid.uuid4().hex, origin=read(STATE / 'origin'),
             original_head=head(), original_branch=current_branch, reviewed_tree='',
             intended_head='', commit_tree='', audit_hash='', verdict_run='',
             base_repo='', head_repo='', base_branch='', head_branch='',
             phase='started', url='', number=None, early_ref=False)
    default = default_branch(remotes)
    if default is not None:
        target = current_branch if current_branch != default else branch_name(j)
        git('check-ref-format', '--branch', target)
        j.update(head_branch=target, early_ref=True)
        claim_ref(j)  # a collision leaves no journal behind
        if j['head_branch'] != j['original_branch']:
            # Move onto the branch now, so every stage's work happens there and
            # the default branch is never written to. The ref was just created
            # at this exact commit, so pointing HEAD at it changes no file and
            # touches no index entry -- uncommitted work carries over untouched.
            # This is the same mechanism publication uses for the same reason;
            # it simply happens before the first stage instead of after the
            # last one.
            git('symbolic-ref', 'HEAD', 'refs/heads/' + j['head_branch'])
            # Where the checkout actually came from, kept before the next line
            # overwrites it. If this branch is deleted or moved from outside the
            # run, HEAD is left unborn and every tracked file reads as newly
            # added; recovering needs the name that was here first, and nothing
            # else records it.
            j['base_checkout_branch'] = j['original_branch']
            # From here the run *starts* on the branch. Every later phase
            # checks `branch() == original_branch` to detect someone moving the
            # checkout mid-run, and that check must keep meaning that.
            j['original_branch'] = j['head_branch']
    save(j)
    if j['early_ref']:
        print('Branch: ' + j['head_branch'], flush=True)


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
    # The branch the checkout was on before this run moved it, when it did.
    # Asking original_branch here would name uncle's own branch as the
    # operator's, so a deferred naming would reuse the very identity that
    # was abandoned.
    target = j.get('base_checkout_branch') or j['original_branch']
    if j.get('early_ref'):
        # A started journal owns the head identity (Issue 60). Only the
        # current-versus-default classification is recomputed: a name bound
        # before the label lookup or a brief rewrite still publishes.
        if (target == base_branch) == (j['head_branch'] == target):
            raise ValueError('Early branch identity conflicts with the base branch; rerun FINAL_AUDIT.')
        target = j['head_branch']
    elif target == base_branch:
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
    # Recover an exact commit that completed immediately before its journal
    # update. This check must precede validate(), whose job is to reject any
    # other unexpected HEAD movement.
    if (j.get('phase') == 'prepared' and not j.get('intended_head')
            and branch() == j['head_branch'] and head() != j['original_head']
            and git('rev-parse', 'HEAD^{tree}') == j['commit_tree']
            and git('rev-parse', 'HEAD^') == j['original_head']):
        j['intended_head'] = head()
        j['requires_signature'] = False
        j.pop('manual_signing', None)
        save(j)
    if j.get('manual_signing'):
        if j['intended_head']:
            manual_signed_commit(j)
        elif j.get('signing_fallback'):
            manual_signed_commit(j, j['signing_fallback'])
        else:
            # A pending journal from before automatic commits redetects config.
            prepare_commit(j)
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
        # What blocks release depends on the envelopes and the artifact, not on
        # the consent given below -- so it can be known now. It used to be
        # checked only after the operator had typed a PR title, a work summary,
        # verification steps and a y/n: four answers collected for a PR the
        # driver had already decided it would not create.
        blocked = release_blocked_reason(j)
        if blocked:
            if blocked_gate(blocked) != 'skip':
                # The same error the post-consent gate raises, so the exit code
                # and the wording do not depend on which one caught it.
                raise attestation().AttestationError(blocked)
            # Durable, so the later gate sees the same decision this one made
            # and the record survives a resume.
            j['release_skipped'] = blocked
            save(j)
            print('Publishing over a failed audit, on the record.', flush=True)
        print('Audited files to commit and publish:', flush=True)
        print(git('diff', '--name-status', j['original_head'], j['commit_tree']), flush=True)
        print(git('diff', '--no-ext-diff', '--no-textconv', j['original_head'], j['commit_tree']), flush=True)
        print('Target: ' + j['base_repo'] + ':' + j['base_branch'] + ' <- ' + j['head_repo'] + ':' + j['head_branch'], flush=True)
        if envelopes_enabled():
            print('After consent, .uncle/attestation.json (and .sig when a signer exists) are added to this commit.', flush=True)
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
        skipped = j.get('release_skipped')
        if skipped:
            # First thing a reviewer reads. A PR published over a failing audit
            # must not look like one that passed.
            rows = blocking_findings()
            banner = ('> [!WARNING]\n'
                      '> **Published over a failing final audit.** ' + skipped + '\n')
            if rows:
                banner += '>\n> Blocking findings:\n'
                for row in rows[:10]:
                    banner += '> - ' + row.replace('\n', ' ') + '\n'
            body = banner + '\n' + body
        record = override_record()
        if len(record) == 4 and record[0] == j['verdict_run'] and record[2] == j['audit_hash']:
            # An overridden verdict is not a READY verdict; the PR says so.
            body = ('> Created by operator override over a **' + record[1]
                    + '** audit verdict.\n\n') + body
        if envelopes_enabled():
            # The release envelope, Statement and signature; refuses here,
            # before any git write, when the blocking policy says so.
            attest(j)
            sealed = sealed_attestation(j)
        else:
            print('Attestation: none (no envelopes directory; run predates attestation)', flush=True)
            # The consent just given is the publication gate; only a person at
            # the terminal reaches this line, so it is the one field stamped here.
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
        if isinstance(j.get('statement'), dict):
            restore_attestation_files(j)
        validate(j)
        current_branch = branch()
        if current_branch != j['head_branch']:
            # Branch creation precedes switching; a crash resumes the same ref.
            refs = early_ref_oid(j)
            if refs and refs != j['original_head']:
                raise ValueError(COLLISION)
            if not refs:
                if j.get('early_ref'):
                    raise ValueError('Pre-created branch is missing; rerun FINAL_AUDIT.')
                git('update-ref', 'refs/heads/' + j['head_branch'], j['original_head'], '0' * 40)
            git('symbolic-ref', 'HEAD', 'refs/heads/' + j['head_branch'])
        if not j['intended_head']:
            prepare_commit(j)
        current_branch = branch()
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
    restored = restore_unborn_head()
    if restored:
        print('Recovered HEAD onto ' + restored + ': the run\'s branch was removed.',
              flush=True)
        if action != 'start':
            # `start` can simply claim the name again. Every later action was
            # bound to that exact branch, so the run stops -- and says which of
            # the two things went wrong. Falling through would reach the generic
            # "HEAD or branch changed", which describes the repair this function
            # just performed rather than the cause.
            raise ValueError('Pre-created branch is missing; rerun FINAL_AUDIT.')
    moved = restore_moved_head()
    if moved:
        print('Recovered HEAD onto ' + moved + ": the run's branch was moved.", flush=True)
    if action == 'start':
        start()
    elif action == 'freeze':
        started = None
        previous = None
        if JOURNAL.exists():
            previous = load()
            if previous['phase'] in ('creating', 'unknown'):
                raise ValueError('Unresolved PR outcome; reconcile existing journal before a fresh audit.')
            started = started_journal()
        j = dict(version=1, owner=uuid.uuid4().hex, origin=read(STATE / 'origin'),
                 original_head=head(), original_branch=branch(), reviewed_tree=snapshot(),
                 intended_head='', commit_tree='', audit_hash='', verdict_run='',
                 base_repo='', head_repo='', base_branch='', head_branch='',
                 phase='auditing', url='', number=None)
        if started and (not started['early_ref'] or started['head_branch'] == started['original_branch']
                        or early_ref_oid(started) == started['original_head']):
            # The audit binds the identity claimed at start. A ref that was
            # moved or deleted since is left alone; naming defers to resolve().
            j.update(version=2, owner=started['owner'], head_branch=started['head_branch'],
                     early_ref=started['early_ref'])
        # Carried across the journal handover whether or not the early identity
        # survived: it records where the checkout was before the run moved it,
        # which is what puts HEAD back if the branch is removed, and what
        # resolve() must treat as the base. An abandoned identity does not make
        # the checkout's origin unknown.
        carried = (started or previous or {}).get('base_checkout_branch')
        if carried:
            j['base_checkout_branch'] = carried
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
    elif action == 'artifact':
        # The digest every envelope and the Statement subject name: working
        # files minus the workflow's own state and documents.
        print(snapshot(excludes=envelope().ARTIFACT_EXCLUDES))
    elif action == 'run-branch-name':
        # The branch a run works on, derived from whichever brief this project
        # has. Read-only and journal-free, so it can be asked before anything
        # exists -- which is when a worktree has to be created. No owner suffix:
        # the caller makes it unique if the name is taken.
        print(label_prefix(read(STATE / 'origin')) + slug(slug_text()))
    elif action == 'branch-name':
        # Read-only: the name a worktree run works in, derived exactly as
        # `start` would from the same origin and title, minus the owner suffix
        # that does not exist before `start`. Neither reads nor writes the journal.
        title, repo, issue, fetch = sys.argv[2:6]
        print(label_prefix('\t'.join([repo, issue, fetch])) + slug(title))
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
except StartError as error:
    print('Branch setup failed: ' + str(error), flush=True)
    sys.exit(1)
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
