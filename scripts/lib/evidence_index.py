"""Content-addressed evidence navigation shared by workflow stages.

Cached excerpts are never acceptance results. Files are rehashed on every call.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import os

VERSION = 1
STAGES = {
    'requirements': ['REQUIREMENTS.md'],
    'project-plan': ['REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md'],
    'change-plan': ['CHANGE_SPEC.md', 'BASELINE_REPORT.md'],
    'adversarial-review': ['REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md'],
    'updated-plan': ['REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md', 'PROJECT_PLAN.md', 'ADVERSARIAL_REVIEW.md'],
    'updated-change-plan': ['CHANGE_SPEC.md', '@CHANGE_PLAN.pre-review.md', 'ADVERSARIAL_REVIEW.md'],
    'manual-checklist-base': ['CHANGE_SPEC.md', 'CHANGE_PLAN.md'],
    # Not IMPLEMENTATION_NOTES.md or AUTOMATED_TEST_REPORT.md: those are the
    # repairing agent's own earlier claims, and quoting their PASS lines back
    # is how a pass came to report findings fixed without touching a file.
    'repair': ['UPDATED_PROJECT_PLAN.md', 'TEST_REVIEW.md', 'VERIFICATION_REPORT.md', 'DEFECTS.md',
               '@green-check.md', '@green-check.tsv', '@TEST_CHANGES.diff', '@verification.manifest',
               '@REPAIR_BRIEF.md'],
}
REPORTS = ['MANUAL_CHECKLIST.md', 'VERIFICATION_REPORT.md', 'DEFECTS.md',
           '@checklist-driver-checks/README.md', '@checklist-driver-checks/results.tsv',
           '@delivery-summary.tsv', '@verification.manifest', '@TEST_CHANGES.diff', '@green-check.md', '@green-check.tsv',
           'TEST_REVIEW.md', 'AUTOMATED_TEST_REPORT.md', 'CHANGE_TEST_REPORT.md']
CONFIG = ['package.json', 'pyproject.toml', 'requirements.txt', 'package-lock.json',
          '@green-check.commands', '@green-check.groups']


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.index-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def packet(project, state, stage, family='app'):
    root, state = Path(project).resolve(), Path(state).resolve()
    if not state.is_relative_to(root):
        raise ValueError('Evidence state must be inside the project')
    # Driver-owned workers are execution slices, not independently configured
    # workflow stages. Every runner consumes the parent stage's evidence.
    if '-review-worker-' in stage:
        stage = stage.split('-review-worker-', 1)[0]
    elif '-worker-' in stage:
        stage = stage.split('-worker-', 1)[0]
    if not re.fullmatch(r'[a-z0-9-]+', stage):
        raise ValueError('Invalid stage name')
    names = list(STAGES.get(stage, ['REQUIREMENTS.md', 'UPDATED_PROJECT_PLAN.md', 'CHANGE_SPEC.md', 'CHANGE_PLAN.md'] + REPORTS))
    if stage == 'adversarial-review' and family == 'change':
        names = ['CHANGE_SPEC.md', 'CHANGE_PLAN.md', 'BASELINE_REPORT.md']
    if stage != 'manual-checklist-base':
        names += CONFIG
    if stage == 'final-audit':
        names += ['@change.diff', '@implementation-completion.txt']
        names += ['@waivers/' + p.name for p in sorted((state/'waivers').glob('*')) if p.is_file()]
    cache = state/'evidence-index'
    if cache.is_symlink() or any((cache/part).is_symlink() for part in ('objects', 'stages')):
        raise ValueError('Refusing symlinked evidence cache')
    previous = read_json(cache/'stages'/f'{stage}-{family}.json')
    previous_files = previous.get('files', {}) if isinstance(previous, dict) else {}
    records, excerpts = {}, {}
    hits = 0
    for name in dict.fromkeys(names):
        path = state/name[1:] if name.startswith('@') else root/name
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            records[name] = {'status': 'outside project or symlink'}
            continue
        try:
            digest, head, size = hashlib.sha256(), b'', 0
            with path.open('rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
                    size += len(chunk)
                    head += chunk[:max(0, 65536-len(head))]
            sha = digest.hexdigest()
            key = hashlib.sha256(f'{VERSION}:{sha}'.encode()).hexdigest()
            objpath = cache/'objects'/f'{key}.json'
            obj = read_json(objpath)
            if not isinstance(obj, dict) or obj.get('sha256') != sha or obj.get('version') != VERSION:
                text = head.decode('utf-8', errors='replace')
                selected = []
                for number, line in enumerate(text.splitlines(), 1):
                    if re.search(r'\b(?:REQ|AC|FR|AR|MC|D|S|I)-\d+\b|^#{1,4} |PASS|FAIL|BLOCKED|NOT RUN', line, re.I):
                        selected.append(f'{number}: {line[:250]}')
                obj = {'version': VERSION, 'sha256': sha,
                       'excerpt': ('\n'.join(selected) if selected else text)[:1800]}
                save(objpath, obj)
            else:
                hits += 1
            records[name] = {'path': str(path), 'sha256': sha, 'bytes': size}
            excerpts[name] = obj['excerpt']
        except OSError:
            records[name] = {'status': 'missing or unreadable'}
    changed = [name for name, row in records.items() if previous_files.get(name) != row]
    removed = sorted(set(previous_files)-set(records))
    snapshot = {'version': VERSION, 'stage': stage, 'family': family, 'files': records,
                'changed': changed, 'removed': removed, 'excerpt_cache_hits': hits}
    save(cache/'stages'/f'{stage}-{family}.json', snapshot)
    # Structured handoff for downstream tools; Markdown is only its presentation.
    handoff = {'schema': 1, 'stage': stage, 'family': family, 'inputs': records,
               'changed_inputs': changed, 'removed_inputs': removed,
               'evidence_references': {name: value.splitlines() for name, value in excerpts.items()}}
    save(state/'handoffs'/f'{stage}-{family}.json', handoff)

    audit_note = ''
    if stage == 'final-audit':
        from audit_evidence import build
        audit = build(root, state, family)
        audit_path = state/'handoffs'/f'audit-evidence-{family}.json'
        save(audit_path, audit)
        inventory = {name: row.get('status') + ('; header only' if row.get('header_only') else '')
                     for name, row in audit['files'].items()}
        audit_note = ('\n## Dedicated audit evidence index\nRead ' + str(audit_path) +
                      ' for all extracted claim rows and command/result records with source line numbers. '
                      'Literal references are navigation, not proven mappings. Resolve each claim against '
                      'actual assertions and execution evidence once. Do not infer PASS.\nFile availability: ' +
                      json.dumps(inventory) + '\nWaivers directory: ' + audit['waivers_directory'] + '\n')

    lines = ['\n## Shared driver evidence index',
             'Current files were rehashed. Cached excerpts are navigation only, never PASS or approval evidence.',
             'Read omitted input and exact assertion evidence directly. Missing files do not imply satisfied requirements.',
             'Changes since this stage last prepared inputs: ' + (', '.join(changed + removed) or 'none'),
             'Independent reviewers must challenge conclusions even when input hashes are unchanged.']
    budget = 16000
    for name, row in records.items():
        entry = '\n' + name + ': ' + json.dumps(row) + '\n' + excerpts.get(name, '')
        raw = entry.encode('utf-8')
        if len(raw) > budget:
            lines.append('[Packet limit reached; complete inventory: ' + str(cache/'stages'/f'{stage}-{family}.json') + ']')
            break
        lines.append(entry)
        budget -= len(raw)
    lines.append('All excerpts are bounded; read source documents for complete requirements and command blocks.')
    return audit_note + '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project'); parser.add_argument('state'); parser.add_argument('stage')
    parser.add_argument('--family', choices=['app', 'change'], default='app')
    args = parser.parse_args()
    print(packet(args.project, args.state, args.stage, args.family), end='')
