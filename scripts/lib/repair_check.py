#!/usr/bin/env python3
"""Judge a repair pass by the files it changed, not by what its report says.

A repair agent can write "TR-2 fixed" without touching a file; on one build it
did exactly that, and the run spent a review cycle and a repair attempt to learn
what a hash comparison would have said for free. So the driver snapshots the
files each blocking finding names before the pass and compares afterwards.

    snapshot <report> <out.json>            hash the files the blocking findings name
    judge    <snapshot.json> <notes.md>     print the IDs still unrepaired;
                                            exit 0 all changed, 4 some, 1 none
    brief    <report> <snapshot.json> <out.md> ID...   write the retry brief

A finding is repaired when one of the files it names changed, or a file the
agent names in that finding's disposition row (IMPLEMENTATION_NOTES.md, a
backticked repository-relative path on a line mentioning the ID) changed. A
finding that names no file -- an aggregate row such as COVERAGE, or a report
with no findings table -- is judged by the source tree as a whole: something
outside the reports and driver state must differ.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPORTS = {'IMPLEMENTATION_NOTES.md', 'AUTOMATED_TEST_REPORT.md', 'CHANGE_TEST_REPORT.md',
           'TEST_REVIEW.md', 'VERIFICATION_REPORT.md', 'MANUAL_CHECKLIST.md', 'DEFECTS.md',
           'FINAL_AUDIT.md', 'PREFLIGHT_REPORT.md', 'REQUIREMENTS.md', 'REQUIREMENTS_INTERPRETATION.md',
           'PROJECT_PLAN.md', 'UPDATED_PROJECT_PLAN.md', 'ADVERSARIAL_REVIEW.md', 'CHANGE_REQUEST.md',
           'CHANGE_SPEC.md', 'CHANGE_PLAN.md', 'BASELINE_REPORT.md'}
SKIP_DIRS = {'.git', '.uncle', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build',
             '.pw-browsers', '.pytest_cache'}
# A repository-relative path: directories and a file, or a bare file with a
# source-like extension. Optional `:12` / `:12-20` line references are dropped.
PATH_TOKEN = re.compile(
    r'(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+|[\w-]+\.(?:js|mjs|cjs|ts|tsx|jsx|py|sh|bash|html|htm|css|scss|json|ya?ml|toml|'
    r'txt|go|rs|java|rb|php|c|h|cpp|hpp|swift|kt|sql|vue|svelte))(?::\d+(?:-\d+)?)?(?![\w/])')
TREE_FALLBACK = '(source tree)'


def sha(path):
    try:
        with open(path, 'rb') as stream:
            return hashlib.sha256(stream.read()).hexdigest()
    except OSError:
        return None


def tree_digest(root):
    digest = hashlib.sha256()
    for base, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            if rel in REPORTS or path.is_symlink():
                continue
            digest.update(rel.encode('utf-8', 'replace'))
            digest.update((sha(path) or '').encode())
    return digest.hexdigest()


def paths_in(text, root):
    found = []
    for match in PATH_TOKEN.finditer(text):
        token = match.group(1).strip('`').lstrip('./')
        if not token or token in found or token.startswith('.uncle/') or token in REPORTS:
            continue
        if token.endswith('/') or '..' in token.split('/'):
            continue
        # A path that exists, or one the correction says to create -- but a
        # slash alone does not make something a path. A decision/invariant
        # citation like "DEC-9/I-5" matches the same shape as a real
        # repository path and is never a file; tracking it as one leaves a
        # finding waiting on a file that can never be written, stuck open
        # forever. Require either the file to already exist, or its last
        # segment to look file-shaped (has an extension), so a real
        # not-yet-created file is still tracked while a bare ID
        # cross-reference is not.
        last = token.rsplit('/', 1)[-1]
        file_shaped = '.' in last and not last.startswith('.')
        if (root / token).is_file() or ('/' in token and file_shaped):
            found.append(token)
    return found


def cells(line):
    line = line.strip()
    if not (line.startswith('|') and line.endswith('|')):
        return None
    return [c.strip() for c in line[1:-1].split('|')]


def findings(text):
    """{id: row text} for blocking findings, plus FAIL rows of the acceptance gate."""
    out = {}
    header = None
    in_gate = False
    for line in text.splitlines():
        if re.match(r'^## Acceptance gate\s*$', line):
            in_gate, header = True, None
            continue
        if line.startswith('#'):
            in_gate, header = False, None
            continue
        row = cells(line)
        if row is None:
            header = None
            continue
        if all(re.fullmatch(r':?-{3,}:?', c) for c in row if c):
            continue
        if in_gate:
            if len(row) >= 4 and row[1].upper() == 'YES' and row[2].upper() == 'FAIL' and row[0] != 'ID':
                out.setdefault(row[0], ' | '.join(row))
            continue
        lowered = [c.lower() for c in row]
        if 'id' in lowered and 'blocks' in lowered:
            header = {'id': lowered.index('id'), 'blocks': lowered.index('blocks')}
            continue
        if header and len(row) > max(header.values()):
            if row[header['blocks']].upper() == 'YES':
                out[row[header['id']]] = ' | '.join(row)
    return out


def snapshot(report, out):
    root = Path.cwd()
    text = Path(report).read_text(errors='replace') if Path(report).is_file() else ''
    rows = findings(text)
    if not rows:
        rows = {TREE_FALLBACK: ''}
    data = {'report': report, 'findings': {}, 'hashes': {}, 'tree': tree_digest(root)}
    for ident, row in rows.items():
        paths = paths_in(row, root)
        data['findings'][ident] = {'row': row, 'paths': paths}
        for path in paths:
            data['hashes'][path] = sha(root / path)
    Path(out).write_text(json.dumps(data, indent=1))
    return 0


def named_in_notes(notes, ident, root):
    if not Path(notes).is_file() or ident == TREE_FALLBACK:
        return []
    pattern = re.compile(r'(?<![\w-])' + re.escape(ident) + r'(?![\w-])')
    found = []
    for line in Path(notes).read_text(errors='replace').splitlines():
        if pattern.search(line):
            found += [p for p in paths_in(line, root) if p not in found]
    return found


def judge(snapshot_path, notes):
    root = Path.cwd()
    data = json.loads(Path(snapshot_path).read_text())
    tree_changed = tree_digest(root) != data['tree']
    unrepaired, repaired = [], []
    for ident, finding in data['findings'].items():
        candidates = list(finding['paths'])
        candidates += [p for p in named_in_notes(notes, ident, root) if p not in candidates]
        if not candidates:
            changed = tree_changed
        else:
            changed = any(sha(root / p) != data['hashes'].get(p) for p in candidates)
        if changed:
            repaired.append(ident)
            print('%s: changed %s' % (ident, ', '.join(candidates) or 'the source tree'), file=sys.stderr)
        else:
            unrepaired.append(ident)
    for ident in unrepaired:
        print(ident)
    if not unrepaired:
        return 0
    return 4 if repaired else 1


def brief(report, snapshot_path, out, ids):
    data = json.loads(Path(snapshot_path).read_text())
    text = Path(report).read_text(errors='replace') if Path(report).is_file() else ''
    lines = ['# Repair brief', '',
             'Written by the driver after a repair pass that changed none of the files the',
             'findings below name. The dispositions already recorded for these IDs in',
             'IMPLEMENTATION_NOTES.md and AUTOMATED_TEST_REPORT.md describe work the tree does',
             'not contain: treat them as wrong, not as evidence. A finding stays open until a',
             'file it names -- or a file you name in its disposition row -- actually changes.',
             '', 'Source report: ' + report, '', '## Still open', '']
    for ident in ids:
        finding = data['findings'].get(ident)
        if finding is None:
            continue
        row = finding['row'] or 'Judged by the source tree as a whole: nothing outside the reports changed.'
        lines.append('- **%s**: %s' % (ident, row))
        if finding['paths']:
            lines.append('  Files named: ' + ', '.join('`%s`' % p for p in finding['paths']))
    gate = re.search(r'^## Acceptance gate\s*$.*?(?=^## |\Z)', text, re.M | re.S)
    if gate:
        failing = [l for l in gate.group(0).splitlines() if (cells(l) or [''])[0] in ids]
        if failing:
            lines += ['', '## Acceptance rows failing', '', '| ID | Required | Status | Evidence |', '|---|---|---|---|'] + failing
    Path(out).write_text('\n'.join(lines) + '\n')
    return 0


def main(argv):
    if len(argv) >= 3 and argv[0] == 'snapshot':
        return snapshot(argv[1], argv[2])
    if len(argv) == 3 and argv[0] == 'judge':
        return judge(argv[1], argv[2])
    if len(argv) >= 4 and argv[0] == 'brief':
        return brief(argv[1], argv[2], argv[3], argv[4:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
