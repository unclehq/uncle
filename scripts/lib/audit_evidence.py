"""Mechanical audit navigation. Reported claims are never independently verified here."""
import hashlib
from pathlib import Path
import re


def build(root, state, family):
    root, state = Path(root).resolve(), Path(state).resolve()
    names = ['VERIFICATION_REPORT.md', 'MANUAL_CHECKLIST.md', 'TEST_REVIEW.md',
             'DEFECTS.md', 'IMPLEMENTATION_NOTES.md',
             'CHANGE_TEST_REPORT.md' if family == 'change' else 'AUTOMATED_TEST_REPORT.md',
             '@green-check.commands', '@green-check.current.tsv', '@green-check.tsv',
             '@checklist-driver-checks/results.tsv', '@delivery-summary.tsv',
             '@verification.manifest', '@plan-executability/assessment.md', '@plan-recovery.json']
    waivers = state/'waivers'
    if waivers.is_dir() and not waivers.is_symlink():
        names += ['@waivers/'+p.name for p in sorted(waivers.iterdir()) if p.is_file()]
    result = {'schema': 1, 'family': family,
              'meaning': 'Reported claims and literal references only; no PASS or approval inferred.',
              'files': {}, 'claims': [], 'execution_records': [],
              'waivers_directory': 'present' if waivers.is_dir() else 'missing'}
    for name in names:
        path = state/name[1:] if name.startswith('@') else root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            result['files'][name] = {'status': 'outside project or symlink'}; continue
        try: raw = path.read_bytes()
        except OSError:
            result['files'][name] = {'status': 'missing or unreadable'}; continue
        text = raw.decode('utf-8', errors='replace')
        result['files'][name] = {'path': str(path), 'bytes': len(raw),
                                'sha256': hashlib.sha256(raw).hexdigest(),
                                'status': 'present' if text.strip() else 'empty'}
        meaningful = []
        for number, line in enumerate(text.splitlines(), 1):
            if name.endswith('.tsv') or name.endswith('.commands'):
                if line.strip():
                    result['execution_records'].append({'source': name, 'line': number, 'raw': line})
                continue
            if not line.lstrip().startswith('|'): continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if all(re.fullmatch(r'[-: ]*', c) for c in cells): continue
            if not cells or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.\-/]*', cells[0]): continue
            if not re.search(r'\d', cells[0]): continue
            meaningful.append(number)
            result['claims'].append({'id': cells[0], 'source': name, 'line': number,
                'raw': line, 'references': re.findall(r'`([^`]+)`', line),
                'mapping': 'UNRESOLVED: reviewer must associate exact assertions and fresh execution evidence'})
        if name == '@delivery-summary.tsv':
            result['files'][name]['header_only'] = len([l for l in text.splitlines() if l.strip()]) <= 1
    return result
