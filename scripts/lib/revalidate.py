#!/usr/bin/env python3
"""uncle revalidate: say which stages of a finished build still hold, and which must be redone.

The baseline is the project's own attestation (`.uncle/attestation.json`): each stage recorded the digest of the approved
documents it produced and the filtered git tree its verification and audit judged. This compares that recorded state with
the project now, and reports, per stage, `reused` (its inputs are byte-identical) or `re-run` (an input changed, the stage
did not pass last time, or Uncle cannot tell).

It plans; it does not yet execute. Re-running a stage means running the driver, so the report ends with the command that does it.

Rules (issue #243):
  R-1  A stage is reused only if every input it reads is identical to the last passing run. When unsure, re-run.
  R-2  A changed test or other protected verification file is reported as a change needing review, never as reusable.
  R-3  A stage that did not pass last time is never reused.
  R-4  A changed input re-runs that stage and every stage after it.
  R-5  Nothing is written: no approval, no attestation, no state.

usage: revalidate.py [--attestation PATH] [--tree TREE] [--dry-run]
  --tree TREE   compare this commit or tree instead of the working tree
  --dry-run     accepted for forward compatibility; this version never executes a stage
Exit: 0 every stage reusable; 1 at least one stage must be re-run; 2 no baseline or bad usage.
"""
import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGES = ('requirements', 'plan', 'review', 'implementation', 'verification', 'audit')
LABEL = {'requirements': 'requirements', 'plan': 'plan', 'review': 'adversarial review',
         'implementation': 'implementation', 'verification': 'verification (build and tests)',
         'audit': 'final audit and manual checks'}

# The approved documents each stage produces; a changed one means that stage's output is no longer what was approved.
DOC_STAGE = {
    'REQUIREMENTS.md': 'requirements', 'REQUIREMENTS_INTERPRETATION.md': 'requirements', 'BASELINE_REPORT.md': 'requirements',
    'CHANGE_REQUEST.md': 'requirements', 'CHANGE_SPEC.md': 'requirements',
    'PROJECT_PLAN.md': 'plan', 'UPDATED_PROJECT_PLAN.md': 'plan', 'CHANGE_PLAN.md': 'plan', 'UPDATED_CHANGE_PLAN.md': 'plan',
    'ADVERSARIAL_REVIEW.md': 'review',
    'IMPLEMENTATION_NOTES.md': 'implementation',
    'AUTOMATED_TEST_REPORT.md': 'verification', 'CHANGE_TEST_REPORT.md': 'verification', 'TEST_REVIEW.md': 'verification',
    'PREFLIGHT_REPORT.md': 'verification', 'MANUAL_CHECKLIST.md': 'audit', 'VERIFICATION_REPORT.md': 'audit',
    'DEFECTS.md': 'audit', 'FINAL_AUDIT.md': 'audit',
}

DOC_EXTENSIONS = ('.md', '.markdown', '.rst')
DOC_ASSETS = ('.png', '.jpg', '.jpeg', '.gif', '.svg')
DOC_NAMES = ('README', 'LICENSE', 'LICENCE', 'NOTICE', 'CHANGELOG', 'CONTRIBUTING', 'CODE_OF_CONDUCT', 'AUTHORS')
TEST_DIRS = {'tests', 'test', '__tests__', 'e2e', 'spec', 'specs'}
TEST_GLOBS = ('*.test.*', '*.spec.*', 'test_*.py', '*_test.py', '*_test.go', 'playwright.config.*', 'vitest.config.*',
              'jest.config.*', 'conftest.py')


def load_verifier():
    """The attestation verifier owns the definition of the filtered tree; use it rather than copy it."""
    spec = importlib.util.spec_from_file_location('uncle_verify', HERE.parent / 'uncle-verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify(path, protected):
    """'docs', 'tests' or 'source' for one changed project file. Unknown files are source: when unsure, re-run (R-1)."""
    if path in protected:
        return 'tests'
    parts = path.split('/')
    name = parts[-1]
    stem = name.split('.')[0].upper()
    if name.lower().endswith(DOC_EXTENSIONS) or stem in DOC_NAMES:
        return 'docs'
    if parts[0] == 'docs' and name.lower().endswith(DOC_ASSETS):
        return 'docs'
    if any(part in TEST_DIRS for part in parts[:-1]) or any(fnmatch.fnmatch(name, g) for g in TEST_GLOBS):
        return 'tests'
    return 'source'


def protected_paths(root):
    path = Path(root) / '.uncle' / 'workflow' / 'verification.paths'
    try:
        return {line.strip().rstrip('/') for line in path.read_text(encoding='utf-8').splitlines() if line.strip()}
    except OSError:
        return set()


def sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ''


def working_tree(verifier):
    """The tree of the project as it is now, uncommitted edits included, built through a throwaway index."""
    fd, index = tempfile.mkstemp(prefix='uncle-revalidate-index-')
    os.close(fd)
    os.unlink(index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        verifier.git('add', '-A', env=env)
        return verifier.git('write-tree', env=env).decode().strip()
    finally:
        for name in (index, index + '.lock'):
            if os.path.exists(name):
                os.unlink(name)


def changed_files(verifier, baseline, current):
    """Paths that differ between two trees, or None when the baseline tree is gone and nothing can be compared."""
    try:
        out = verifier.git('diff', '--name-only', '-z', '--no-renames', baseline, current)
    except Exception:
        return None
    return [p for p in out.decode('utf-8').split('\0') if p]


def stage_records(predicate):
    """stage -> {'result', 'reason', 'docs': {relative doc path: recorded sha256}} from the attestation."""
    records = {}
    for stage, envelope in (predicate.get('envelopes') or {}).items():
        if stage not in STAGES or not isinstance(envelope, dict):
            continue
        docs = {}
        for row in envelope.get('evidence') or []:
            path = str(row.get('path') or '')
            digest = (row.get('digest') or {}).get('sha256', '')
            if path.startswith('.uncle/docs/') and digest:
                docs[path] = digest
        records[stage] = {'result': envelope.get('result'), 'reason': envelope.get('reason'), 'docs': docs}
    return records


def plan(root, attestation_path, tree=None):
    verifier = load_verifier()
    data = json.loads(Path(attestation_path).read_text(encoding='utf-8'))
    predicate = data.get('predicate') or {}
    records = stage_records(predicate)
    baseline = verifier.digest_of((predicate.get('release') or {}).get('artifact'), 'gitTree')
    if not records or not baseline:
        raise ValueError('the attestation records no stage results or release tree to compare against')

    reasons = {stage: [] for stage in STAGES}      # why a stage cannot be reused (its own cause)
    notes = []

    # R-3: a stage that did not pass last time cannot be reused.
    for stage in STAGES:
        record = records.get(stage)
        if record is None:
            reasons[stage].append('no recorded result')
        elif record['result'] != 'pass':
            why = record['reason'] or record['result']
            reasons[stage].append('did not pass last time (%s)' % why)

    # Approved documents: a changed one invalidates the stage that wrote it.
    for stage, record in records.items():
        for doc, recorded in sorted(record['docs'].items()):
            owner = DOC_STAGE.get(Path(doc).name, stage)
            if sha256(Path(root) / doc) != recorded:
                reasons[owner].append('%s changed since it was approved' % doc)

    # Project files: compare the filtered tree now with the one the verification and audit judged.
    current_raw = tree or working_tree(verifier)
    current = verifier.artifact_of(current_raw)
    changed = None
    if current != baseline:
        changed = changed_files(verifier, baseline, current)
    files = {'docs': [], 'tests': [], 'source': []}
    if current != baseline:
        if changed is None:
            for stage in ('verification', 'audit'):
                reasons[stage].append('the attested tree %s is not in this repository, so nothing can be compared' % verifier.short(baseline))
        else:
            protected = protected_paths(root)
            for path in changed:
                files[classify(path, protected)].append(path)
            if files['source']:
                reasons['implementation'].append('changed outside a run: %s' % ', '.join(files['source'][:4])
                                                 + (' and %d more' % (len(files['source']) - 4) if len(files['source']) > 4 else ''))
                for stage in ('verification', 'audit'):
                    reasons[stage].append('source changed')
            if files['tests']:
                # R-2: say it is a protected verification change, not just a changed file.
                for stage in ('verification', 'audit'):
                    reasons[stage].append('protected verification file changed, needs review: %s' % ', '.join(files['tests'][:4]))
    # R-4: a changed or failed stage re-runs everything after it.
    first = next((i for i, stage in enumerate(STAGES) if reasons[stage]), None)
    rows = []
    for i, stage in enumerate(STAGES):
        if reasons[stage]:
            rows.append((stage, 'rerun', '; '.join(dict.fromkeys(reasons[stage]))))
        elif first is not None and i > first:
            rows.append((stage, 'rerun', 'follows %s, which must be re-run' % LABEL[STAGES[first]]))
        else:
            rows.append((stage, 'reused', 'inputs unchanged; last passed'))
    return {'rows': rows, 'files': files, 'changed': changed, 'baseline': baseline, 'current': current,
            'stale': current != baseline, 'run_id': predicate.get('run_id'), 'notes': notes, 'short': verifier.short}


def render(result):
    short = result['short']
    out = ['UNCLE REVALIDATION', '']
    if result['stale']:
        if result['changed'] is None:
            out.append('changed since the attestation: cannot be listed (the attested tree is not in this repository)')
        elif result['changed']:
            files = result['files']
            out.append('changed since the attestation: %s' % ', '.join(result['changed'][:8])
                       + (' and %d more' % (len(result['changed']) - 8) if len(result['changed']) > 8 else ''))
            if not files['source'] and not files['tests']:
                out.append('%d of %d changed file(s) are documentation that no stage reads as an input' %
                           (len(files['docs']), len(result['changed'])))
            else:
                out.append('%d source, %d test, %d documentation file(s) changed' %
                           (len(files['source']), len(files['tests']), len(files['docs'])))
        else:
            out.append('changed since the attestation: files match; only metadata differs')
    else:
        out.append('no project file changed since the attestation')
    out.append('')
    for stage, status, why in result['rows']:
        mark = '✓' if status == 'reused' else '✗'
        word = 'reused ' if status == 'reused' else 're-run '
        out.append('%s %-32s %s %s' % (mark, LABEL[stage], word, why))
    out.append('')
    reused = sum(1 for _, status, _ in result['rows'] if status == 'reused')
    rerun = len(result['rows']) - reused
    if result['stale']:
        out.append('○ attestation is stale: it covers tree %s and the project is now %s. Refresh it or record the change;'
                   % (short(result['baseline']), short(result['current'])))
        out.append('  this does not by itself re-run any stage.')
    if rerun:
        out.append('%d stage(s) must be re-run, %d reused.' % (rerun, reused))
        out.append('This version reports the plan and does not run stages. `uncle --audit` re-runs only the final audit;')
        out.append('`uncle --change-request --attended` re-runs the full change flow.')
    else:
        out.append('%d stage(s) reused, none re-run.' % reused)
    return '\n'.join(out)


def main(argv):
    parser = argparse.ArgumentParser(prog='uncle revalidate', description='Plan a revalidation of a finished build.')
    parser.add_argument('--attestation', help='path to attestation.json (default .uncle/attestation.json)')
    parser.add_argument('--tree', help='commit or tree to compare instead of the working tree')
    parser.add_argument('--dry-run', action='store_true', help='accepted; this version never executes a stage')
    args = parser.parse_args(argv)
    path = args.attestation or os.path.join('.uncle', 'attestation.json')
    if not os.path.isfile(path):
        print('No recorded passing run: %s does not exist.' % path)
        print('Revalidation compares a project with its attestation; build it with `uncle` first.')
        return 2
    try:
        result = plan('.', path, args.tree)
    except Exception as error:      # noqa: BLE001 - a CLI: any failure here is "cannot compare", never a traceback
        detail = error.args[0] if error.args else error
        if isinstance(detail, (list, tuple)):
            detail = ' '.join(str(line).strip() for line in detail)
        print('Cannot revalidate: %s' % detail)
        return 2
    print(render(result))
    return 1 if any(status == 'rerun' for _, status, _ in result['rows']) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
