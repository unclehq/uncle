#!/usr/bin/env python3
"""Standalone verifier for an Uncle change attestation (Issue 59).

Stdlib only, plus `git`. `ssh-keygen`, `cosign` and `gh` are optional and
their absence is a one-line message. Runs in the checkout it is pointed at;
nothing from the Uncle install is imported, so `canonical()` and
`ARTIFACT_EXCLUDES` below are copies of scripts/lib/envelope.py and must stay
byte-identical.

Exit codes: 0 VERIFIED; 1 NOT VERIFIED or refused; 2 usage or a required tool
missing; 3 integrity only (no signature, untrusted signature, or a missing
optional tool).
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

STATEMENT_TYPE = 'https://in-toto.io/Statement/v1'
PREDICATE_TYPE = 'https://uncle.dev/attestation/v1'
SCHEMA_VERSION = '1'
PAYLOAD_TYPE = 'application/vnd.in-toto+json'
SSH_NAMESPACE = 'uncle-attestation'
DOCUMENTS = ('BASELINE_REPORT', 'CHANGE_SPEC', 'ADVERSARIAL_REVIEW', 'CHANGE_PLAN')
DELEGATED = re.compile(r'^(unattended|supervisor:.*|disabled:.*)$', re.S)

ARTIFACT_EXCLUDES = (
    '.uncle/',
    'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md',
    'BASELINE_REPORT.md', 'CHANGE_REQUEST.md', 'CHANGE_SPEC.md', 'CHANGE_PLAN.md',
    'UPDATED_CHANGE_PLAN.md', 'ADVERSARIAL_REVIEW.md', 'IMPLEMENTATION_NOTES.md',
    'CHANGE_TEST_REPORT.md', 'AUTOMATED_TEST_REPORT.md', 'MANUAL_CHECKLIST.md',
    'VERIFICATION_REPORT.md', 'DEFECTS.md', 'FINAL_AUDIT.md', 'PREFLIGHT_REPORT.md', 'TEST_REVIEW.md',
)


# --- canonical JSON (RFC 8785), copied from scripts/lib/envelope.py ----------

def canonical(value):
    out = []
    _emit(value, out)
    return ''.join(out).encode('utf-8')


def _emit(value, out):
    if value is None:
        out.append('null')
    elif value is True:
        out.append('true')
    elif value is False:
        out.append('false')
    elif isinstance(value, int):
        out.append(str(value))
    elif isinstance(value, float):
        raise ValueError('floats are not canonicalizable here')
    elif isinstance(value, str):
        out.append(_string(value))
    elif isinstance(value, (list, tuple)):
        out.append('[')
        for index, item in enumerate(value):
            if index:
                out.append(',')
            _emit(item, out)
        out.append(']')
    elif isinstance(value, dict):
        out.append('{')
        keys = list(value)
        if not all(isinstance(key, str) for key in keys):
            raise ValueError('object keys must be strings')
        for index, key in enumerate(sorted(keys, key=lambda k: k.encode('utf-16-be'))):
            if index:
                out.append(',')
            out.append(_string(key))
            out.append(':')
            _emit(value[key], out)
        out.append('}')
    else:
        raise ValueError('unsupported value: ' + type(value).__name__)


_ESCAPES = {'\b': '\\b', '\t': '\\t', '\n': '\\n', '\f': '\\f', '\r': '\\r', '"': '\\"', '\\': '\\\\'}


def _string(text):
    out = ['"']
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20:
            out.append('\\u%04x' % ord(char))
        else:
            out.append(char)
    out.append('"')
    return ''.join(out)


def pae(payload_type, payload):
    return b' '.join([b'DSSEv1', str(len(payload_type)).encode(), payload_type.encode(),
                      str(len(payload)).encode(), payload])


# --- helpers -----------------------------------------------------------------

class Refused(Exception):
    """A check failed; carries the lines to print."""


class Usage(Exception):
    pass


def git(*args, data=None, env=None, check=True):
    result = subprocess.run(['git', *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode:
        raise Refused(['git ' + ' '.join(args) + ' failed: ' + result.stderr.decode('utf-8', 'replace').strip()])
    return result.stdout


def excluded(path):
    return any(path.startswith(prefix) if prefix.endswith('/') else path == prefix for prefix in ARTIFACT_EXCLUDES)


def artifact_of(tree):
    """The tree minus ARTIFACT_EXCLUDES, rebuilt through a temporary index."""
    fd, index = tempfile.mkstemp(prefix='uncle-verify-index-')
    os.close(fd)
    os.unlink(index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        git('read-tree', tree, env=env)
        paths = [p for p in git('ls-tree', '-r', '-z', '--name-only', tree).decode('utf-8').split('\0') if p]
        drop = [p for p in paths if excluded(p)]
        if drop:
            git('update-index', '--force-remove', '-z', '--stdin', env=env,
                data=b''.join(p.encode('utf-8') + b'\0' for p in drop))
        return git('write-tree', env=env).decode().strip()
    finally:
        for name in (index, index + '.lock'):
            if os.path.exists(name):
                os.unlink(name)


def short(value):
    value = str(value or '')
    return value[:4] + '…' + value[-4:] if len(value) > 12 else (value or 'missing')


def digest_of(node, kind):
    return ((node or {}).get('digest') or {}).get(kind, '') if isinstance(node, dict) else ''


# --- checks ------------------------------------------------------------------

def check_1(raw):
    try:
        value = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise Usage('attestation is not JSON')
    if not isinstance(value, dict) or value.get('_type') != STATEMENT_TYPE:
        raise Usage('refused: not an in-toto Statement v1 (_type %r)' % (value.get('_type') if isinstance(value, dict) else None))
    if value.get('predicateType') != PREDICATE_TYPE:
        raise Usage('refused: unknown predicateType %r' % value.get('predicateType'))
    predicate = value.get('predicate')
    if not isinstance(predicate, dict) or predicate.get('schema_version') != SCHEMA_VERSION:
        raise Usage('refused: unsupported schema_version %r' % (predicate.get('schema_version') if isinstance(predicate, dict) else None))
    if canonical(value) != raw:
        raise Refused(['attestation bytes are not canonical', '  re-serialized: %d bytes' % len(canonical(value)),
                       '  on disk:        %d bytes' % len(raw)])
    subjects = value.get('subject')
    if not isinstance(subjects, list) or len(subjects) != 1 or not digest_of(subjects[0], 'gitTree'):
        raise Refused(['attestation subject is missing its gitTree digest'])
    return value, 'attestation canonical, in-toto Statement, schema v%s' % SCHEMA_VERSION


def check_2(raw, statement, sig_bytes, args):
    """(line, verdict): verdict is 'VERIFIED' only for a valid signature against
    a supplied trust root; otherwise an integrity-only label."""
    authentication = statement['predicate'].get('authentication')
    if sig_bytes is None:
        if authentication != 'none':
            raise Refused(['attestation claims authentication %r but no .sig is present' % authentication])
        return 'no signature (authentication: none)', 'INTEGRITY ONLY — NOT AUTHENTICATED'
    try:
        envelope = json.loads(sig_bytes.decode('utf-8'))
        signatures = envelope['signatures']
        payload = base64.b64decode(envelope['payload'], validate=True)
        sig = base64.b64decode(signatures[0]['sig'], validate=True)
        method = signatures[0].get('signer', '')
    except (ValueError, KeyError, IndexError, TypeError, UnicodeDecodeError):
        raise Refused(['signature file is not a DSSE envelope'])
    if envelope.get('payloadType') != PAYLOAD_TYPE or payload != raw:
        raise Refused(['DSSE payload differs from the attestation bytes',
                       '  payload sha256:     ' + hashlib.sha256(payload).hexdigest(),
                       '  attestation sha256: ' + hashlib.sha256(raw).hexdigest()])
    data = pae(PAYLOAD_TYPE, raw)
    if method == 'ssh':
        allowed = args.allowed_signers or os.path.join('.uncle', 'allowed_signers')
        if not os.path.isfile(allowed):
            return 'signature present (ssh); no trust root at ' + allowed, 'INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED'
        if not shutil.which('ssh-keygen'):
            return 'signature present (ssh); ssh-keygen is not installed, so it was not checked', 'INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED'
        principals = []
        for line in Path(allowed).read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                principals.append(line.split()[0])
        with tempfile.TemporaryDirectory(prefix='uncle-verify-') as tmp:
            sig_path = Path(tmp) / 'attestation.sig'
            sig_path.write_bytes(sig)
            for principal in principals:
                result = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', allowed, '-I', principal,
                                         '-n', SSH_NAMESPACE, '-s', str(sig_path)], input=data,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode == 0:
                    return 'signature valid (ssh: %s, %s)' % (principal, allowed), 'VERIFIED'
        raise Refused(['signature invalid against ' + allowed,
                       '  principals tried: ' + (', '.join(principals) or 'none')])
    if method == 'sigstore':
        if not (args.certificate_identity and args.certificate_oidc_issuer):
            return 'signature present (sigstore); no --certificate-identity/--certificate-oidc-issuer given', 'INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED'
        if not shutil.which('cosign'):
            return 'signature present (sigstore); cosign is not installed, so it was not checked', 'INTEGRITY ONLY — SIGNATURE PRESENT BUT UNTRUSTED'
        with tempfile.TemporaryDirectory(prefix='uncle-verify-') as tmp:
            bundle = Path(tmp) / 'bundle.json'
            bundle.write_bytes(sig)
            blob = Path(tmp) / 'pae'
            blob.write_bytes(data)
            result = subprocess.run(['cosign', 'verify-blob', '--bundle', str(bundle),
                                     '--certificate-identity', args.certificate_identity,
                                     '--certificate-oidc-issuer', args.certificate_oidc_issuer, str(blob)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            raise Refused(['sigstore signature invalid: ' + (result.stderr.strip().split('\n') or [''])[0]])
        return 'signature valid (sigstore: %s)' % args.certificate_identity, 'VERIFIED'
    raise Refused(['unknown signature method %r' % method])


def check_3(statement, tree):
    predicate = statement['predicate']
    envelopes = predicate.get('envelopes') or {}
    embedded = {}
    for env in envelopes.values():
        for row in (env.get('evidence') or []) if isinstance(env, dict) else []:
            embedded.setdefault(row.get('path'), digest_of(row, 'sha256'))
    lines = []
    for entry in predicate.get('approvals') or []:
        name = entry.get('gate')
        if name not in DOCUMENTS:
            continue
        recorded = entry.get('digest') or ''
        path = name + '.md'
        blob = git('rev-parse', '--verify', '-q', tree + ':' + path, check=False).decode().strip()
        if blob:
            actual = hashlib.sha256(git('cat-file', 'blob', blob)).hexdigest()
            where = 'committed'
        else:
            actual = embedded.get(path, '')
            where = 'embedded'
        if not recorded or actual != recorded:
            raise Refused(['approved %s digest mismatch (%s copy)' % (name, where),
                           '  approved:  ' + (recorded or 'missing'), '  present:   ' + (actual or 'missing')])
        lines.append('approved %s %s' % (name.lower().replace('_', ' '), short(recorded)))
    if not lines:
        raise Refused(['no approved document is recorded in the attestation'])
    return lines


def check_4(statement):
    envelopes = statement['predicate'].get('envelopes') or {}
    release = digest_of((statement['predicate'].get('release') or {}).get('artifact'), 'gitTree')
    values = {
        'implementation artifact': digest_of((envelopes.get('implementation') or {}).get('artifact'), 'gitTree'),
        'verification input': digest_of(((envelopes.get('verification') or {}).get('inputs') or {}).get('artifact'), 'gitTree'),
        'audit input': digest_of(((envelopes.get('audit') or {}).get('inputs') or {}).get('artifact'), 'gitTree'),
    }
    for name, value in values.items():
        if not release or value != release:
            raise Refused(['artifact mismatch', '  %s: %s' % (name.ljust(24), value or 'missing'),
                           '  release artifact:         ' + (release or 'missing')])
    return 'implementation artifact ' + short(release), release


def check_5(statement):
    envelopes = statement['predicate'].get('envelopes') or {}
    lines = []
    for stage in ('review', 'verification', 'audit'):
        env = envelopes.get(stage)
        result = env.get('result') if isinstance(env, dict) else 'missing'
        if result != 'pass':
            raise Refused(['%s result is %s, not pass' % (stage, result)
                           + ('; ' + env['reason'] if isinstance(env, dict) and env.get('reason') else '')])
        producer = (env.get('producer') or {}).get('runner', '') if isinstance(env, dict) else ''
        if stage == 'review':
            findings = env.get('findings') or []
            dispositions = (envelopes.get('plan') or {}).get('dispositions') or []
            lines.append('independent review (%s, pass, %d findings, %d dispositions)' % (producer, len(findings), len(dispositions)))
        else:
            lines.append('%s pass' % stage)
    return lines


def check_6(statement):
    envelopes = statement['predicate'].get('envelopes') or {}
    findings = (envelopes.get('review') or {}).get('findings') or []
    done = {row.get('finding') for row in (envelopes.get('plan') or {}).get('dispositions') or []}
    missing = [row.get('id') for row in findings if row.get('severity') == 'blocking' and row.get('id') not in done]
    if missing:
        raise Refused(['blocking finding without a disposition: ' + ', '.join(missing)])
    blocking = sum(1 for row in findings if row.get('severity') == 'blocking')
    return 'blocking findings dispositioned: %d of %d' % (blocking, blocking)


def check_7(statement):
    approved = []
    for entry in statement['predicate'].get('approvals') or []:
        if not entry.get('required'):
            continue
        by = entry.get('approved_by') or ''
        if not by or DELEGATED.match(by):
            raise Refused(['required gate %s has no human approval' % entry.get('gate'),
                           '  approved_by:  ' + (by or 'empty'),
                           '  delegated_by: ' + (entry.get('delegated_by') or 'empty')])
        approved.append(str(entry.get('gate')).lower().replace('_', ' '))
    if not approved:
        raise Refused(['no required human gate is recorded'])
    return 'human approvals: ' + ', '.join(approved)


def check_8(statement, tree, release):
    subject = digest_of(statement['subject'][0], 'gitTree')
    actual = artifact_of(tree)
    if actual != release or actual != subject:
        raise Refused(['head tree does not match the release artifact',
                       '  head tree (filtered): ' + actual, '  release artifact:     ' + release,
                       '  subject digest:       ' + subject])
    return 'head tree matches release artifact ' + short(actual)


# --- entry -------------------------------------------------------------------

def resolve_target(args):
    """(tree, attestation bytes, signature bytes or None)."""
    sig = None
    if args.pr:
        if not shutil.which('gh'):
            raise Usage('gh is not installed; pass --attestation and --tree instead of a PR')
        view = subprocess.run(['gh', 'pr', 'view', args.pr, '--json', 'headRefOid'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if view.returncode:
            raise Usage('gh pr view failed: ' + view.stderr.strip().split('\n')[0])
        head = json.loads(view.stdout)['headRefOid']
        if git('rev-parse', '--verify', '-q', head + '^{commit}', check=False).decode().strip() == '':
            raise Usage('PR head %s is not in this repository; fetch it first' % head)
        tree = git('rev-parse', head + '^{tree}').decode().strip()
        if args.attestation:
            raw = Path(args.attestation).read_bytes()
            sig_path = Path(args.attestation).with_suffix('.sig')
            sig = sig_path.read_bytes() if sig_path.exists() else None
        else:
            raw = git('show', head + ':.uncle/attestation.json')
            has_sig = git('rev-parse', '--verify', '-q', head + ':.uncle/attestation.sig', check=False).decode().strip()
            sig = git('show', head + ':.uncle/attestation.sig') if has_sig else None
        return tree, raw, sig
    tree = git('rev-parse', (args.tree or 'HEAD') + '^{tree}').decode().strip()
    path = Path(args.attestation or os.path.join('.uncle', 'attestation.json'))
    try:
        raw = path.read_bytes()
    except OSError:
        raise Usage('no attestation at ' + str(path))
    sig_path = path.with_suffix('.sig')
    sig = sig_path.read_bytes() if sig_path.exists() else None
    return tree, raw, sig


def main(argv):
    parser = argparse.ArgumentParser(prog='uncle verify', description='Verify an Uncle change attestation.')
    parser.add_argument('pr', nargs='?', help='PR URL or number (needs gh); default: the current checkout')
    parser.add_argument('--attestation', help='path to attestation.json (default .uncle/attestation.json)')
    parser.add_argument('--tree', help='commit or tree to verify (default HEAD)')
    parser.add_argument('--allowed-signers', help='SSH trust root (default .uncle/allowed_signers)')
    parser.add_argument('--certificate-identity')
    parser.add_argument('--certificate-oidc-issuer')
    args = parser.parse_args(argv)
    if not shutil.which('git'):
        print('git is not installed; uncle verify needs it.')
        return 2
    print('UNCLE CHANGE VERIFICATION')
    print()
    verdict = 'VERIFIED'
    try:
        tree, raw, sig = resolve_target(args)
        statement, line = check_1(raw)
        print('✓ ' + line)
        line, verdict = check_2(raw, statement, sig, args)
        print(('✓ ' if verdict == 'VERIFIED' else '○ ') + line)
        for line in check_3(statement, tree):
            print('✓ ' + line)
        line, release = check_4(statement)
        print('✓ ' + line)
        for line in check_5(statement):
            print('✓ ' + line)
        print('✓ ' + check_6(statement))
        print('✓ ' + check_7(statement))
        print('✓ ' + check_8(statement, tree, release))
    except Usage as error:
        print(str(error))
        print()
        print('NOT VERIFIED')
        return 2 if 'not installed' in str(error) else 1
    except Refused as error:
        print('✗ ' + error.args[0][0])
        for extra in error.args[0][1:]:
            print(extra)
        print()
        print('NOT VERIFIED')
        return 1
    print()
    print(verdict)
    return 0 if verdict == 'VERIFIED' else 3


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
