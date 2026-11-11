#!/usr/bin/env python3
"""Revalidate against a project's attestation, and re-issue it when nothing but documentation changed.

`revalidate.py` compares a project with the stage fingerprints the drivers recorded as stages passed. A project built before
those existed has none, and used to be refused ("no recorded passes"). Its attestation records enough to compare against: the
sha256 of each stage's approved documents and the filtered git tree the verification and audit judged (the same tree
`uncle verify` compares). This builds a per-stage plan from that, in the attestation's stage names.

When the plan finds nothing the change invalidates, the attestation is re-issued for the new tree with the recorded results
carried forward (a failure stays recorded as a failure). The claim is written into the attestation (`revalidation`) and
`uncle verify` checks it independently (check_9): every changed file is documentation, and everything outside documentation is
exactly what was recorded. A change to source, tests, configuration or an approved document is never carried forward.

Signing: the attestation is re-signed with the same signer a build uses (git's SSH signing key, or cosign with gitsign). If it
was signed and cannot be signed again, nothing is written: a signed statement is never downgraded to an unsigned one.
"""
import copy
import fnmatch
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STAGES = ('requirements', 'plan', 'review', 'implementation', 'verification', 'audit')
LABEL = {'requirements': 'requirements', 'plan': 'plan', 'review': 'adversarial review', 'implementation': 'implementation',
         'verification': 'verification', 'audit': 'final audit'}
DOC_STAGE = {
    'REQUIREMENTS.md': 'requirements', 'REQUIREMENTS_INTERPRETATION.md': 'requirements', 'BASELINE_REPORT.md': 'requirements',
    'CHANGE_REQUEST.md': 'requirements', 'CHANGE_SPEC.md': 'requirements',
    'PROJECT_PLAN.md': 'plan', 'UPDATED_PROJECT_PLAN.md': 'plan', 'CHANGE_PLAN.md': 'plan', 'UPDATED_CHANGE_PLAN.md': 'plan',
    'ADVERSARIAL_REVIEW.md': 'review', 'IMPLEMENTATION_NOTES.md': 'implementation',
    'AUTOMATED_TEST_REPORT.md': 'verification', 'CHANGE_TEST_REPORT.md': 'verification', 'TEST_REVIEW.md': 'verification',
    'PREFLIGHT_REPORT.md': 'verification', 'MANUAL_CHECKLIST.md': 'audit', 'VERIFICATION_REPORT.md': 'audit',
    'DEFECTS.md': 'audit', 'FINAL_AUDIT.md': 'audit',
}
TEST_DIRS = {'tests', 'test', '__tests__', 'e2e', 'spec', 'specs'}
TEST_GLOBS = ('*.test.*', '*.spec.*', 'test_*.py', '*_test.py', '*_test.go', 'playwright.config.*', 'vitest.config.*',
              'jest.config.*', 'conftest.py')


def verifier():
    """The attestation verifier owns the definitions of the filtered tree and of documentation; use it, do not copy it."""
    spec = importlib.util.spec_from_file_location('uncle_verify', HERE.parent / 'uncle-verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(path, v, protected=()):
    """'docs', 'tests' or 'source'. Unknown files are source: when unsure, the stages rerun."""
    if v.is_documentation(path):
        return 'docs'
    if path in protected or any(part in TEST_DIRS for part in path.split('/')[:-1]) \
            or any(fnmatch.fnmatch(path.rsplit('/', 1)[-1], g) for g in TEST_GLOBS):
        return 'tests'
    return 'source'


def _sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ''


def _protected(root):
    path = Path(root) / '.uncle' / 'workflow' / 'verification.paths'
    try:
        return {l.strip().rstrip('/') for l in path.read_text(encoding='utf-8').splitlines() if l.strip()}
    except OSError:
        return set()


def load(root, path=None):
    """(raw bytes, statement). Raises ValueError when there is nothing usable to compare with."""
    path = Path(path) if path else Path(root) / '.uncle' / 'attestation.json'
    try:
        raw = path.read_bytes()
        statement = json.loads(raw.decode('utf-8'))
        predicate = statement['predicate']
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('%s is missing or is not an attestation' % path) from None
    if not isinstance(predicate.get('envelopes'), dict) or not predicate.get('release'):
        raise ValueError('the attestation records no stage results or release tree')
    return raw, statement


def release_tree(v, statement):
    return v.digest_of((statement['predicate'].get('release') or {}).get('artifact'), 'gitTree')


def working_tree(v):
    """The project as it is now, uncommitted edits included, built through a throwaway index."""
    import tempfile
    fd, index = tempfile.mkstemp(prefix='uncle-revalidate-index-')
    os.close(fd)
    os.unlink(index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        v.git('add', '-A', env=env)
        return v.git('write-tree', env=env).decode().strip()
    finally:
        for name in (index, index + '.lock'):
            if os.path.exists(name):
                os.unlink(name)


def plan(root, statement=None, tree=None):
    """The per-stage plan against the attestation: {'rows', 'changed', 'files', 'baseline', 'current', 'stale', 'eligible'}.

    A row is {stage, action: reuse|run, reason, cause}. `cause` says why a stage reruns: `change` (the change invalidates it),
    `failed` (it did not pass last time) or `supervisor`. Only a `change` or `supervisor` cause stops the attestation being
    re-issued; a stage that failed before simply stays recorded as failed."""
    v = verifier()
    if statement is None:
        statement = load(root)[1]
    predicate = statement['predicate']
    baseline = release_tree(v, statement)
    if not baseline:
        raise ValueError('the attestation records no release tree')
    cause = {s: [] for s in STAGES}       # stage -> [(cause, reason)]
    recorded = {}
    for stage in STAGES:
        envelope = (predicate.get('envelopes') or {}).get(stage)
        if not isinstance(envelope, dict):
            cause[stage].append(('failed', 'no recorded result'))
            continue
        recorded[stage] = envelope
        if envelope.get('result') != 'pass':
            cause[stage].append(('failed', 'did not pass last time (%s)' % (envelope.get('reason') or envelope.get('result'))))
        for row in envelope.get('evidence') or []:
            rel, digest = str(row.get('path') or ''), (row.get('digest') or {}).get('sha256', '')
            if rel.startswith('.uncle/docs/') and digest and _sha(Path(root) / rel) != digest:
                owner = DOC_STAGE.get(Path(rel).name, stage)
                cause[owner].append(('change', '%s changed since it was approved' % rel))
    current = v.artifact_of(tree or working_tree(v))
    files = {'docs': [], 'tests': [], 'source': []}
    changed = []
    if current != baseline:
        try:
            changed = [p for p in v.git('diff', '--name-only', '-z', '--no-renames', baseline, current).decode().split('\0') if p]
        except Exception:                                   # the attested tree is not in this repository
            changed = None
            for stage in ('verification', 'audit'):
                cause[stage].append(('change', 'the attested tree %s is not in this repository, so nothing can be compared'
                                     % v.short(baseline)))
        if changed:
            protected = _protected(root)
            for path in changed:
                files[classify(path, v, protected)].append(path)
            if files['source']:
                cause['implementation'].append(('change', 'changed outside a run: ' + ', '.join(files['source'][:4])))
                cause['verification'].append(('change', 'source changed'))
                cause['audit'].append(('change', 'source changed'))
            if files['tests']:
                msg = 'protected verification file changed, needs review: ' + ', '.join(files['tests'][:4])
                cause['verification'].append(('change', msg))
                cause['audit'].append(('change', msg))
    rows = []
    first = None
    for i, stage in enumerate(STAGES):
        reasons = cause[stage]
        if reasons:
            kind = 'change' if any(c == 'change' for c, _ in reasons) else 'failed'
            rows.append({'stage': stage, 'action': 'run', 'cause': kind,
                         'reason': '; '.join(dict.fromkeys(r for _, r in reasons))})
            if first is None or (kind == 'change' and rows[first]['cause'] != 'change'):
                first = i if first is None else first
        elif first is not None and any(r['action'] == 'run' for r in rows):
            earlier = next(r for r in rows if r['action'] == 'run')
            rows.append({'stage': stage, 'action': 'run', 'cause': earlier['cause'],
                         'reason': 'follows %s, which must run again' % LABEL[earlier['stage']]})
        else:
            rows.append({'stage': stage, 'action': 'reuse', 'cause': '', 'reason': 'inputs unchanged; last passed'})
    return {'rows': rows, 'changed': changed, 'files': files, 'baseline': baseline, 'current': current,
            'stale': current != baseline, 'short': v.short}


def eligible(info):
    """True when the attestation can be re-issued: the tree changed, only documentation changed, and no stage is invalidated
    by the change (a stage that failed before does not count: its recorded failure is carried forward as it was)."""
    if not info['stale'] or not info['changed']:
        return False
    if info['files']['source'] or info['files']['tests']:
        return False
    return not any(r['action'] == 'run' and r['cause'] in ('change', 'supervisor') for r in info['rows'])


def _swap_tree(node, old, new):
    if isinstance(node, dict):
        return {k: (new if k == 'gitTree' and node[k] == old else _swap_tree(item, old, new)) for k, item in node.items()}
    if isinstance(node, list):
        return [_swap_tree(item, old, new) for item in node]
    return node


def reissue(root, info, statement, dry_run=False):
    """(ok, message). Writes .uncle/attestation.json (and .sig) for the new tree, or writes nothing."""
    import envelope as env
    v = verifier()
    if not eligible(info):
        return False, 'not eligible: the change is not documentation only, or a stage is invalidated by it'
    old, new = info['baseline'], info['current']
    rest_old, rest_new = v.rest_of(old), v.rest_of(new)
    if rest_old != rest_new:
        return False, 'refused: the project outside its documentation differs from the attested state'
    if dry_run:
        return True, 'would re-issue for %s, carrying the recorded results forward' % v.short(new)
    sig_path = Path(root) / '.uncle' / 'attestation.sig'
    was_signed = sig_path.is_file()
    method, detail = env.select_signer()
    if was_signed and method == 'none':
        return False, 'refused: the attestation was signed and no signer is configured; it will not be downgraded to unsigned'
    body = _swap_tree(copy.deepcopy(statement), old, new)
    body['predicate']['authentication'] = method
    body['predicate']['revalidation'] = {
        'method': 'documentation-only',
        'carried_forward_from': {'digest': {'gitTree': old}},
        'rest': {'digest': {'gitTree': rest_new}},
        'changed_files': sorted(info['changed']),
        'timestamp': env.utc_now(),
    }
    env.check_keys(body)
    payload = env.canonical(body)
    signature = None
    if method != 'none':
        signature, failure = env.sign(payload, method, detail)
        if signature is None:
            if was_signed:
                return False, 'refused: signing failed (%s); a signed attestation will not be downgraded to unsigned' % failure
            method = 'none'
            body['predicate']['authentication'] = 'none'
            payload = env.canonical(body)
    target = Path(root) / '.uncle' / 'attestation.json'
    tmp = target.with_name('.attestation.json.tmp')
    tmp.write_bytes(payload)
    if signature is not None:
        sig_tmp = sig_path.with_name('.attestation.sig.tmp')
        sig_tmp.write_bytes(env.canonical(signature))
        os.replace(sig_tmp, sig_path)
    elif sig_path.exists():
        sig_path.unlink()
    os.replace(tmp, target)
    return True, 're-issued for %s (%s); recorded results carried forward from %s' % (
        v.short(new), 'signed: ' + method if signature is not None else 'unsigned', v.short(old))
