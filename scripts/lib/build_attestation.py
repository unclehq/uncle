#!/usr/bin/env python3
"""Attest a finished new-application build.

The change driver writes each stage envelope as the stage ends. The build driver
(stagegate.sh) does not, so at completion this reads what the build recorded --
approval records, the canonical review/plan documents, the green-check results
and the audit verdict -- and writes the same envelopes, the release envelope,
and the signed Statement to .uncle/attestation.json (and .sig). The merge that
ends the build then commits them, where `uncle verify` reads them from main.

A stage with no record is written `unavailable`, never `pass`. Nothing here
approves anything: gate approvals are copied from the driver's approval records.

Usage: build_attestation.py --state DIR --artifact TREE --verdict CLASS
           [--green-enabled 0|1] [--run-id ID] [--subject NAME]
Exit: 0 attestation written; 1 refused (the reason is printed and nothing is
written to .uncle/attestation.*).
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envelope as env  # noqa: E402

READY = ('READY', 'READY_WITH_NON_BLOCKING_ISSUES')
DOCS = Path('.uncle/docs')


def gate_names(state):
    names = set()
    for path in (Path(state) / 'approvals').glob('*'):
        if path.suffix in ('.sha256', '.gate-action'):
            names.add(path.name[:-len(path.suffix)])
    return sorted(names)


def exists(path):
    return Path(path).is_file() and Path(path).stat().st_size > 0


def green_result(state, enabled):
    """(result, reason) from the driver's green-check rows."""
    rows = Path(state) / 'green-check.tsv'
    if enabled != '1':
        return 'unavailable', 'WORKFLOW_GREEN_CHECK=0: the driver did not re-run the checks'
    if not exists(rows):
        return 'unavailable', 'no green-check results'
    firsts = [line.split('\t', 1)[0] for line in rows.read_text(errors='replace').splitlines() if line.strip()]
    regressed = firsts.count('REGRESSION')
    reason = '%d commands: %d pass, %d pre-existing, %d regressed' % (
        len(firsts), firsts.count('PASS') + firsts.count('FIXED'), firsts.count('PREEXISTING'), regressed)
    if regressed:  # the driver's own rule (green_regressions): only REGRESSION fails the check
        return 'fail', reason
    return 'pass', reason


def write_stages(state, artifact, verdict, green_enabled):
    plan = DOCS / 'UPDATED_PROJECT_PLAN.md'
    review = DOCS / 'ADVERSARIAL_REVIEW.md'
    approvals = set(gate_names(state))

    def present(*paths):
        return [str(p) for p in paths if exists(p)]

    def stage(name, ok, reason_missing, **kwargs):
        env.write_envelope(state, name, 'pass' if ok else 'unavailable',
                           reason='' if ok else reason_missing, **kwargs)

    stage('requirements', exists(DOCS / 'REQUIREMENTS_INTERPRETATION.md'), 'no requirements interpretation',
          evidence=present(DOCS / 'REQUIREMENTS_INTERPRETATION.md'))
    stage('review', exists(review), 'no adversarial review',
          evidence=present(review), findings_path=str(review) if exists(review) else '',
          producer_stage='adversarial-review', producer_kind='reviewer')
    stage('plan', exists(plan), 'no updated project plan', evidence=present(plan),
          dispositions_path=str(plan) if exists(plan) else '')
    implementation_gates = sorted(a for a in approvals if 'IMPLEMENT' in a)
    stage('implementation', exists(DOCS / 'IMPLEMENTATION_NOTES.md'), 'no implementation notes',
          artifact=artifact, approvals=implementation_gates,
          evidence=present(DOCS / 'IMPLEMENTATION_NOTES.md', DOCS / 'AUTOMATED_TEST_REPORT.md'),
          producer_stage='implementation', producer_kind='agent')
    result, reason = green_result(state, green_enabled)
    env.write_envelope(state, 'verification', result, reason=reason, inputs={'artifact': artifact},
                       evidence=present(Path(state) / 'green-check.tsv', DOCS / 'AUTOMATED_TEST_REPORT.md'))
    audit = 'pass' if verdict in READY else 'fail'
    env.write_envelope(state, 'audit', audit, reason=verdict or 'no verdict', inputs={'artifact': artifact},
                       evidence=present(DOCS / 'FINAL_AUDIT.md', DOCS / 'VERIFICATION_REPORT.md'),
                       producer_stage='final-audit', producer_kind='reviewer')


def attest(state, artifact, verdict, green_enabled, run_id, subject):
    write_stages(state, artifact, verdict, green_enabled)
    envelopes = env.load_envelopes(state)

    def gate_entry(name):
        entry = env.approval_entry(state, name)
        view = env.sha256_file(DOCS / (name + '.md'))
        if view:
            entry['view_digest'] = view
        return entry

    approvals = [gate_entry(name) for name in gate_names(state)]
    reason = env.blocking_reason(envelopes, artifact)
    release = env.write_envelope(state, 'release', 'fail' if reason else 'pass', reason=reason, artifact=artifact,
                                 inputs={'artifact': artifact}, evidence=['.uncle/docs/FINAL_AUDIT.md'],
                                 extra={'approvals': approvals})
    print('Envelope: release ' + release['result'])
    if reason:
        print('Attestation not written: ' + reason)
        return 1
    envelopes['release'] = release
    method, detail = env.select_signer()
    import supervisor
    known = supervisor.known_secret_values()

    def build(authentication):
        stmt = env.statement(subject, artifact, envelopes, approvals, {'repository': '', 'issue': ''},
                             authentication, __import__('os').environ.get('UNCLE_VERSION', ''), run_id)
        return env.filter_strings(stmt, '.', known=known)

    stmt = build(method)
    payload = env.canonical(stmt)
    sig = None
    if method != 'none':
        sig, failure = env.sign(payload, method, detail)
        if sig is None:
            print('Signing failed: ' + failure + '; attestation written unauthenticated')
            method = 'none'
            stmt = build(method)
            payload = env.canonical(stmt)
    Path('.uncle').mkdir(exist_ok=True)
    Path('.uncle/attestation.json').write_bytes(payload)
    sig_path = Path('.uncle/attestation.sig')
    if sig is None:
        if sig_path.exists():
            sig_path.unlink()
    else:
        sig_path.write_bytes(env.canonical(sig))
    print('Attestation: %s %s' % (method, artifact[:12]))
    return 0


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', required=True)
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--verdict', default='')
    parser.add_argument('--green-enabled', default='1')
    parser.add_argument('--run-id', default='')
    parser.add_argument('--subject', default='build')
    args = parser.parse_args(argv)
    try:
        return attest(args.state, args.artifact, args.verdict, args.green_enabled, args.run_id, args.subject)
    except env.EnvelopeError as error:
        print('Attestation not written: ' + str(error))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
