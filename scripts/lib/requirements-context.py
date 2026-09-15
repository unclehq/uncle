"""Focused requirements inputs and deterministic document checks."""
import hashlib
from pathlib import Path
import re
import sys

SECTIONS = ('Required functionality', 'Optional functionality', 'Constraints',
            'User-visible behaviors', 'System behaviors', 'Failure behaviors',
            'Ambiguities', 'Assumptions', 'Explicit non-goals', 'Definition of done')


def validate(path):
    text = Path(path).read_text(encoding='utf-8')
    sections = {}
    current = None
    fence = None
    ids = set()
    for line in text.splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r'^##\s+(?:\d+[.)]\s*)?(.+?)\s*#*$', line)
        if heading:
            current = heading[1].strip('* ').lower()
            if current in sections:
                raise ValueError('Duplicate section: ' + current)
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line)
        # Only definitions in the first table column; repeated citations are valid.
        row = re.match(r'^\s*\|\s*((?:REQ|FR|BR|AC)-\d+)\s*\|', line)
        if row and current == 'user-visible behaviors':
            if row[1] in ids:
                raise ValueError('Duplicate behavior ID: ' + row[1])
            ids.add(row[1])
    if fence:
        raise ValueError('Unclosed Markdown fence')
    missing = [name for name in SECTIONS if not sections.get(name.lower())]
    if missing:
        raise ValueError('Missing or empty sections: ' + ', '.join(missing))


def render(project):
    root = Path(project).resolve()
    lines = ['\n## Driver requirements inputs',
             'Start with the brief below and this shallow inventory. No recursive discovery unless a concrete requirement needs it.',
             'This packet is not a substitute for omitted source requirements.']
    path = root / 'REQUIREMENTS.md'
    if path.resolve().is_relative_to(root) and path.is_file():
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            excerpt = stream.read(12000)
            digest.update(excerpt)
            while chunk := stream.read(65536):
                digest.update(chunk)
        lines += ['REQUIREMENTS.md SHA-256 ' + digest.hexdigest(), excerpt.decode('utf-8', errors='replace')]
        if path.stat().st_size > len(excerpt):
            lines.append('[Brief truncated; read remaining REQUIREMENTS.md directly.]')
    else:
        lines.append('REQUIREMENTS.md unavailable; do not invent its contents.')
    lines.append('\nTop-level entries (at most 80; no directory traversal):')
    for index, item in enumerate(sorted(root.iterdir(), key=lambda p: p.name)):
        if index == 80:
            lines.append('[Inventory truncated.]')
            break
        lines.append(item.name + ('/' if item.is_dir() else ''))
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    if sys.argv[1] == '--validate':
        try:
            validate(sys.argv[2])
        except (OSError, ValueError) as error:
            print(f'Requirements format invalid: {error}. Correct the saved interpretation and resume.', file=sys.stderr)
            raise SystemExit(1)
    else:
        print(render(sys.argv[1]), end='')
