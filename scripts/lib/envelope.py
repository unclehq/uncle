#!/usr/bin/env python3
"""Driver-written stage envelopes and the release attestation (Issue 59).

Every claim here is written by the driver from validator exit codes, gate
records and its own hashing; no stage model writes an envelope. Bytes are RFC
8785 (JCS) canonical, so a hash or signature over them is reproducible by the
standalone verifier, which carries its own copy of `canonical()` and
`ARTIFACT_EXCLUDES` (scripts/uncle-verify.py) and must stay byte-identical.

CLI (bash 3.2 callers pass one action and flags):
  write --state DIR --stage S --result R [--reason T] [--artifact SHA]
        [--input name=sha ...] [--evidence path ...] [--approval NAME ...]
        [--findings REVIEW.md] [--dispositions PLAN.md] [--reapprovals]
        [--producer-stage LOG_NAME --producer-kind agent|reviewer]
  plan-gate REVIEW.md PLAN.md
  invalidate --state DIR DOC|IMPLEMENT|FINAL_AUDIT
  snapshot --state DIR
  restore --state DIR
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

SCHEMA_VERSION = '1'
STATEMENT_TYPE = 'https://in-toto.io/Statement/v1'
PREDICATE_TYPE = 'https://uncle.dev/attestation/v1'
PAYLOAD_TYPE = 'application/vnd.in-toto+json'
SSH_NAMESPACE = 'uncle-attestation'
STAGES = ('requirements', 'review', 'plan', 'implementation', 'verification', 'audit', 'release')
RESULTS = ('pass', 'fail', 'unavailable')

# The blocking policy, fixed in v1 (CR §4). One definition; nothing reads a
# config or environment variable to change it. An audit override is recorded
# elsewhere and never consulted here.
BLOCKING = {
    'review': ('fail', 'unavailable'),
    'verification': ('fail', 'unavailable'),
    'audit': ('fail', 'unavailable'),
}

# Working files that are not the artifact: the workflow's own state and the
# documents listed in scripts/lib/workflow-artifacts.sh. Duplicated verbatim in
# scripts/uncle-verify.py; POST-4 diffs the two blocks.
ARTIFACT_EXCLUDES = (
    '.uncle/',
    'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md',
    'BASELINE_REPORT.md', 'CHANGE_REQUEST.md', 'CHANGE_SPEC.md', 'CHANGE_PLAN.md',
    'UPDATED_CHANGE_PLAN.md', 'ADVERSARIAL_REVIEW.md', 'IMPLEMENTATION_NOTES.md',
    'CHANGE_TEST_REPORT.md', 'AUTOMATED_TEST_REPORT.md', 'MANUAL_CHECKLIST.md',
    'VERIFICATION_REPORT.md', 'DEFECTS.md', 'FINAL_AUDIT.md', 'PREFLIGHT_REPORT.md', 'TEST_REVIEW.md',
)

# Every key an envelope or the Statement may carry. Domain words come from the
# CR vocabulary; the rest are structure. `tree`, `worker`, `reviewer` and `PR`
# are rendering words and are refused as keys.
VOCABULARY = frozenset((
    'artifact', 'producer', 'verifier', 'release', 'digest', 'approvals', 'findings',
    'dispositions', 'evidence', 'inputs', 'result', 'reason', 'source', 'authentication',
))
STRUCTURE = frozenset((
    'schema_version', 'stage', 'attempt', 'role', 'runner', 'model', 'uncle_version',
    'produced_at', 'gitTree', 'sha256', 'id', 'severity', 'blocking', 'finding', 'action',
    'gate', 'required', 'approved_by', 'delegated_by', 'timestamp', 'reapprovals', 'override',
    'path', '_type', 'subject', 'name', 'predicateType', 'predicate', 'run_id', 'envelopes',
    'repository', 'issue', 'signer',
))
FORBIDDEN_KEYS = frozenset(('tree', 'worker', 'reviewer', 'PR', 'pr'))

# Which stages a changed document (or a re-entered stage) invalidates.
DOWNSTREAM = {
    'BASELINE_REPORT': STAGES,
    'CHANGE_SPEC': STAGES,
    'ADVERSARIAL_REVIEW': ('plan', 'implementation', 'verification', 'audit', 'release'),
    'CHANGE_PLAN': ('plan', 'implementation', 'verification', 'audit', 'release'),
    'IMPLEMENT': ('implementation', 'verification', 'audit', 'release'),
    'FINAL_AUDIT': ('audit', 'release'),
}

BLOCKING_SEVERITY = re.compile(r'(?i)^(high|blocking)\b')
DELEGATED = re.compile(r'^(unattended|supervisor:.*|disabled:.*)$', re.S)
ABSOLUTE_PATH = re.compile(r'(?<![\w:/.])/(?:[\w.@+-]+/)+[\w.@+-]*')
# Rows of the revised plan's disposition table: | Finding | Disposition | ... |
DISPOSITION_ROW = re.compile(r'^\|\s*(AR-[A-Za-z0-9]+)\s*\|\s*([^|]+?)\s*\|', re.M)
FINDING_HEADING = re.compile(r'^##[ \t]+(AR-[A-Za-z0-9]+)(?:[ \t]+\([^\n)]+\))?[ \t]*(?::|—|–|-)[ \t]+\S[^\n]*$', re.M)
SEVERITY_FIELD = re.compile(r'^[ \t]*(?:[-*+][ \t]+)?(?:\*\*)?Severity(?:\*\*)?:[ \t]*(?:\*\*)?([^\n*]*)', re.M)


class EnvelopeError(ValueError):
    """A claim could not be produced or read; nothing is inferred."""


# --- canonical JSON (RFC 8785) ---------------------------------------------

def canonical(value):
    """JCS bytes. Floats are refused: nothing here has one, and the rules for
    ES6 number formatting would otherwise have to be reproduced in two files."""
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


def check_keys(value):
    """Refuse any key outside the vocabulary before bytes are written."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_KEYS or (key not in VOCABULARY and key not in STRUCTURE and key not in STAGES):
                raise EnvelopeError('key outside the vocabulary: ' + key)
            check_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            check_keys(item)


def sha256_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ''


def utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


# --- envelopes ---------------------------------------------------------------

def envelope_dir(state):
    return Path(state) / 'envelopes'


def envelope_path(state, stage):
    return envelope_dir(state) / (stage + '.json')


def read_envelope(state, stage):
    """The envelope, or None when absent. Bytes that do not re-serialize to
    themselves are a tampered or foreign file, and raise."""
    path = envelope_path(state, stage)
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        value = json.loads(raw.decode('utf-8'))
    except ValueError as error:
        raise EnvelopeError(stage + ' envelope is not JSON') from error
    if canonical(value) != raw:
        raise EnvelopeError(stage + ' envelope is not canonical')
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA_VERSION or value.get('stage') != stage:
        raise EnvelopeError(stage + ' envelope has an unsupported shape')
    return value


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix='.envelope-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _attempts(state):
    path = Path(state) / 'envelopes.attempts'
    rows = {}
    for line in (path.read_text().splitlines() if path.exists() else []):
        name, _, count = line.partition('\t')
        if count.isdigit():
            rows[name] = int(count)
    return path, rows


def _record_attempt(state, name):
    path, rows = _attempts(state)
    rows[name] = rows.get(name, 0) + 1
    path.write_text(''.join('%s\t%d\n' % item for item in sorted(rows.items())))
    return rows[name]


def _records(state):
    try:
        saved = json.loads((Path(state) / 'session-totals.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    rows = saved.get('records') if isinstance(saved, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def producer(state, stage, log_name='', kind=''):
    role = {'review': 'verifier', 'verification': 'verifier', 'audit': 'verifier',
            'release': 'release'}.get(stage, 'producer')
    runner = model = 'driver'
    if log_name:
        rows = [r for r in _records(state) if r.get('kind') == kind and r.get('stage') == log_name
                and not r.get('speculative')]
        if rows:
            row = max(enumerate(rows), key=lambda pair: (pair[1].get('ended_at') or 0, pair[0]))[1]
            runner = str(row.get('runner') or '').replace('\\', '/').rsplit('/', 1)[-1] or 'unavailable'
            model = str(row.get('model') or '') or 'unavailable'
        else:
            runner = model = 'unavailable'
    return {'role': role, 'runner': runner, 'model': model,
            'uncle_version': os.environ.get('UNCLE_VERSION', '') or version_from(state)}


def version_from(state):
    try:
        return (Path(__file__).resolve().parents[2] / 'VERSION').read_text().strip() or 'unavailable'
    except OSError:
        return 'unavailable'


def findings(review_text):
    """`AR-*` headings with their severity; `blocking` is the CR's word for
    High (or a literal Blocking) severity."""
    matches = list(FINDING_HEADING.finditer(review_text))
    rows = []
    for index, match in enumerate(matches):
        body = review_text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(review_text)]
        body = re.split(r'^##[ \t]+', body, maxsplit=1, flags=re.M)[0]
        severity = SEVERITY_FIELD.search(body)
        severity = severity.group(1).strip().strip('*').strip() if severity else ''
        rows.append({'id': match.group(1), 'severity': 'blocking' if BLOCKING_SEVERITY.match(severity) else 'advisory'})
    return rows


def dispositions(plan_text):
    rows = []
    seen = set()
    for match in DISPOSITION_ROW.finditer(plan_text):
        finding, action = match.group(1), match.group(2).strip()
        if finding in seen or action.lower() in ('disposition', '---') or not action:
            continue
        seen.add(finding)
        rows.append({'finding': finding, 'action': action})
    return rows


def undispositioned(review_text, plan_text):
    done = {row['finding'] for row in dispositions(plan_text)}
    return [row['id'] for row in findings(review_text) if row['severity'] == 'blocking' and row['id'] not in done]


def approval_entry(state, name):
    """One `approvals[]` entry from the driver's gate record for NAME."""
    approvals = Path(state) / 'approvals'

    def read(suffix):
        try:
            return (approvals / (name + suffix)).read_text(encoding='utf-8', errors='replace').strip()
        except OSError:
            return ''

    digest = read('.sha256')
    action = read('.gate-action')
    approved = read('.approved-by')
    delegated = read('.delegated-by')
    if not delegated and DELEGATED.match(approved):
        # Legacy `.approved-by` values carried the delegation themselves.
        approved, delegated = '', approved
    if action:
        required = action in ('APPROVE', 'ACKNOWLEDGE', 'SKIPPED')
    else:
        required = name != 'FINAL_AUDIT_OVERRIDE'
    if not delegated and action != 'SKIPPED' and (digest or action):
        approved = approved or 'operator'
    timestamp = ''
    try:
        stamp = (approvals / (name + '.sha256')).stat().st_mtime
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(stamp))
    except OSError:
        pass
    return {'gate': name, 'required': required, 'approved_by': approved,
            'delegated_by': delegated, 'digest': digest, 'timestamp': timestamp}


def write_envelope(state, stage, result, reason='', artifact='', inputs=None, evidence=(), root='.',
                   approvals=(), findings_path='', dispositions_path='', reapprovals=False,
                   producer_stage='', producer_kind='', extra=None):
    if stage not in STAGES:
        raise EnvelopeError('unknown stage: ' + stage)
    if result not in RESULTS:
        raise EnvelopeError('unknown result: ' + result)
    body = {
        'schema_version': SCHEMA_VERSION,
        'stage': stage,
        'attempt': _record_attempt(state, stage),
        'producer': producer(state, stage, producer_stage, producer_kind),
        'inputs': {},
        'result': result,
        'evidence': [],
        'produced_at': utc_now(),
    }
    if reason:
        body['reason'] = reason
    if artifact:
        body['artifact'] = {'digest': {'gitTree': artifact}}
    for name, value in (inputs or {}).items():
        if name == 'artifact':
            body['inputs']['artifact'] = {'digest': {'gitTree': value}}
        else:
            body['inputs'][name] = {'digest': {'sha256': value}}
    for path in evidence:
        digest = sha256_file(Path(root) / path)
        body['evidence'].append({'path': path, 'digest': {'sha256': digest or 'unavailable'}})
    if approvals:
        body['approvals'] = [approval_entry(state, name) for name in approvals]
    if findings_path:
        digest = sha256_file(Path(root) / findings_path)
        body['findings'] = [dict(row, evidence={'sha256': digest}) for row in findings(_read(Path(root) / findings_path))]
    if dispositions_path:
        body['dispositions'] = dispositions(_read(Path(root) / dispositions_path))
    if reapprovals:
        body['reapprovals'] = _record_attempt(state, 'CHANGE_PLAN-approval') - 1
    for key, value in (extra or {}).items():
        body[key] = value
    check_keys(body)
    _atomic_write(envelope_path(state, stage), canonical(body))
    return body


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def invalidate(state, name):
    """Delete every envelope downstream of NAME (a document or a re-entered
    stage) and make sure the directory exists: its presence is what turns
    attestation enforcement on at handoff."""
    stages = DOWNSTREAM.get(name, ())
    envelope_dir(state).mkdir(parents=True, exist_ok=True)
    for stage in stages:
        try:
            envelope_path(state, stage).unlink()
        except OSError:
            pass
    return stages


# --- protection around the implementation stage -----------------------------

def _manifest(state):
    directory = envelope_dir(state)
    rows = {'.': 'present' if directory.is_dir() else 'absent'}
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if path.is_file():
                rows[path.name] = sha256_file(path)
    return rows


def snapshot(state):
    state = Path(state)
    keep = state / 'envelopes.snapshot'
    if keep.exists():
        shutil.rmtree(keep)
    if envelope_dir(state).is_dir():
        shutil.copytree(envelope_dir(state), keep)
    manifest = _manifest(state)
    (state / 'envelopes.manifest').write_text(json.dumps(manifest, sort_keys=True) + '\n')
    return manifest


def restore(state):
    """Compare with the snapshot, put the snapshot back, log every difference.
    Returns the list of logged rows; the CLI exits 1 when it is non-empty."""
    state = Path(state)
    try:
        before = json.loads((state / 'envelopes.manifest').read_text())
    except (OSError, ValueError) as error:
        raise EnvelopeError('no envelope snapshot to restore from') from error
    after = _manifest(state)
    rows = []
    for name in sorted(set(before) | set(after)):
        if before.get(name, '') != after.get(name, ''):
            rows.append('\t'.join([utc_now(), 'envelopes/' + name if name != '.' else 'envelopes/',
                                   before.get(name, 'absent'), after.get(name, 'absent')]))
    if rows:
        directory = envelope_dir(state)
        if directory.exists():
            shutil.rmtree(directory)
        keep = state / 'envelopes.snapshot'
        if before.get('.') == 'present':
            if keep.is_dir():
                shutil.copytree(keep, directory)
            else:
                directory.mkdir(parents=True)
        with (state / 'envelope-tamper.log').open('a') as log:
            log.write(''.join(row + '\n' for row in rows))
    return rows


# --- secrets -----------------------------------------------------------------

def _filters():
    lib = str(Path(__file__).resolve().parent)
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import attestation
    import supervisor
    return attestation.SECRET, supervisor._SECRET_LINE


def filter_strings(value, root='.', known=()):
    """Every string field checked against the supervisor and attestation secret
    patterns and for absolute paths; matches are replaced, never passed."""
    secret, secret_line = _filters()
    roots = {str(Path(root).resolve()), str(Path(root).absolute())}

    def inside(path):
        return any(path == r or path.startswith(r + '/') for r in roots)

    def clean(text):
        if secret.search(text) or secret_line.search(text) or any(k and k in text for k in known):
            return '[redacted]'
        for match in ABSOLUTE_PATH.finditer(text):
            if not inside(match.group(0)):
                return '[redacted]'
        return text

    def walk(item):
        if isinstance(item, str):
            return clean(item)
        if isinstance(item, list):
            return [walk(x) for x in item]
        if isinstance(item, dict):
            return {key: walk(x) for key, x in item.items()}
        return item

    return walk(value)


# --- Statement and signing ---------------------------------------------------

def blocking_reason(envelopes, artifact):
    """The first reason release is refused, or ''. Policy is BLOCKING plus the
    artifact identity (I-3); nothing else is consulted."""
    for stage, results in BLOCKING.items():
        env = envelopes.get(stage)
        if env is None:
            return stage + ' result unavailable; envelope missing'
        if env.get('result') in results:
            reason = env.get('reason') or ''
            return stage + ' result ' + env['result'] + ('; ' + reason if reason else '')
    implementation = envelopes.get('implementation') or {}
    recorded = {
        'implementation.artifact': ((implementation.get('artifact') or {}).get('digest') or {}).get('gitTree', ''),
        'verification.inputs.artifact': (((envelopes.get('verification') or {}).get('inputs') or {}).get('artifact') or {}).get('digest', {}).get('gitTree', ''),
        'audit.inputs.artifact': (((envelopes.get('audit') or {}).get('inputs') or {}).get('artifact') or {}).get('digest', {}).get('gitTree', ''),
    }
    for name, value in recorded.items():
        if value != artifact:
            return 'artifact mismatch: %s %s != release %s' % (name, value or 'missing', artifact)
    return ''


def load_envelopes(state):
    return {stage: read_envelope(state, stage) for stage in STAGES if stage != 'release'}


def statement(subject_name, artifact, envelopes, approvals, source, authentication, version, run_id):
    predicate = {
        'schema_version': SCHEMA_VERSION,
        'uncle_version': version or 'unavailable',
        'run_id': run_id or 'unavailable',
        'source': source,
        'approvals': list(approvals),
        'envelopes': {stage: env for stage, env in envelopes.items() if env is not None},
        'release': {'artifact': {'digest': {'gitTree': artifact}}},
        'authentication': authentication,
    }
    body = {
        '_type': STATEMENT_TYPE,
        'subject': [{'name': subject_name, 'digest': {'gitTree': artifact}}],
        'predicateType': PREDICATE_TYPE,
        'predicate': predicate,
    }
    check_keys(body)
    return body


def pae(payload_type, payload):
    return b' '.join([b'DSSEv1', str(len(payload_type)).encode(), payload_type.encode(),
                      str(len(payload)).encode(), payload])


def _git_config(key):
    result = subprocess.run(['git', 'config', '--get', key], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    return result.stdout.strip() if result.returncode == 0 else ''


def select_signer():
    """('sigstore'|'ssh'|'none', detail). No new key material: cosign with a
    gitsign configuration, else git's own SSH signing key, else nothing."""
    if shutil.which('cosign') and _git_config('gpg.x509.program') == 'gitsign':
        return 'sigstore', 'cosign'
    if _git_config('gpg.format') == 'ssh':
        key = os.path.expanduser(_git_config('user.signingkey'))
        if key and Path(key).is_file():
            return 'ssh', key
    return 'none', ''


def sign(payload, method, detail):
    """DSSE signature block over the PAE of PAYLOAD, or (None, error text)."""
    data = pae(PAYLOAD_TYPE, payload)
    import base64
    with tempfile.TemporaryDirectory(prefix='uncle-sign-') as tmp:
        blob = Path(tmp) / 'pae'
        blob.write_bytes(data)
        if method == 'ssh':
            result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-n', SSH_NAMESPACE, '-f', detail, str(blob)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                return None, (result.stderr.strip().split('\n') or ['ssh-keygen failed'])[0]
            sig = (Path(tmp) / 'pae.sig').read_bytes()
            keyid = 'ssh'
            if Path(detail + '.pub').exists():
                keyid = hashlib.sha256(Path(detail + '.pub').read_bytes()).hexdigest()[:16]
        elif method == 'sigstore':
            bundle = Path(tmp) / 'bundle.json'
            result = subprocess.run(['cosign', 'sign-blob', '--yes', '--bundle', str(bundle), str(blob)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode or not bundle.exists():
                return None, (result.stderr.strip().split('\n') or ['cosign failed'])[0]
            sig = bundle.read_bytes()
            keyid = 'sigstore'
        else:
            return None, 'no signer'
    return {'payloadType': PAYLOAD_TYPE, 'payload': base64.b64encode(payload).decode(),
            'signatures': [{'keyid': keyid, 'sig': base64.b64encode(sig).decode(), 'signer': method}]}, ''


# --- CLI ---------------------------------------------------------------------

def _flag_values(argv, flag):
    values = []
    i = 0
    while i < len(argv):
        if argv[i] == flag:
            i += 1
            while i < len(argv) and not argv[i].startswith('--'):
                values.append(argv[i])
                i += 1
        else:
            i += 1
    return values


def _flag(argv, flag, default=''):
    values = _flag_values(argv, flag)
    return values[0] if values else default


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    action, rest = argv[0], argv[1:]
    state = _flag(rest, '--state', '.uncle/workflow')
    if action == 'write':
        inputs = {}
        for item in _flag_values(rest, '--input'):
            name, _, value = item.partition('=')
            if value:
                inputs[name] = value
        body = write_envelope(
            state, _flag(rest, '--stage'), _flag(rest, '--result'), reason=_flag(rest, '--reason'),
            artifact=_flag(rest, '--artifact'), inputs=inputs, evidence=_flag_values(rest, '--evidence'),
            approvals=_flag_values(rest, '--approval'), findings_path=_flag(rest, '--findings'),
            dispositions_path=_flag(rest, '--dispositions'), reapprovals='--reapprovals' in rest,
            producer_stage=_flag(rest, '--producer-stage'), producer_kind=_flag(rest, '--producer-kind'))
        print('Envelope: %s %s' % (body['stage'], body['result']))
        return 0
    if action == 'plan-gate':
        review, plan = rest[0], rest[1]
        missing = undispositioned(_read(review), _read(plan))
        if missing:
            print('Plan gate refused: blocking finding%s without a disposition row in %s: %s'
                  % ('s' if len(missing) > 1 else '', plan, ', '.join(missing)))
            return 1
        return 0
    if action == 'invalidate':
        names = [a for a in rest if not a.startswith('--') and a != state]
        for name in names:
            stages = invalidate(state, name)
            if stages:
                print('Envelopes invalidated by %s: %s' % (name, ', '.join(stages)))
        return 0
    if action == 'snapshot':
        snapshot(state)
        return 0
    if action == 'restore':
        rows = restore(state)
        for row in rows:
            print('Envelope write reverted: ' + row.split('\t')[1])
        if rows:
            print('The implementation stage wrote under envelopes/; the pre-stage copy was restored'
                  ' and the write logged in %s/envelope-tamper.log.' % state)
            return 1
        return 0
    print('Unknown action: ' + action, file=sys.stderr)
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except EnvelopeError as error:
        print('Envelope error: ' + str(error), file=sys.stderr)
        sys.exit(1)
