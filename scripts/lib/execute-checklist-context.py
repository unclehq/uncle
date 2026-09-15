"""Bounded, current inputs for checklist execution; never infer acceptance."""
import hashlib
from pathlib import Path
import sys


def render(project, state):
    project, state = Path(project).resolve(), Path(state).resolve()
    lines = ['\n## Driver execution evidence packet',
             'Excerpts are navigation aids, not coverage conclusions. Read omitted rows directly.',
             'Use only checklist-driver-checks for fresh driver execution evidence.',
             'Match exact assertions before reusing results; human observations require a human.']
    files = [(project / 'MANUAL_CHECKLIST.md', 12000),
             (state / 'checklist-groups/README.md', 4000),
             (state / 'checklist-groups/groups.txt', 4000),
             (state / 'checklist-driver-checks/README.md', 4000),
             (state / 'checklist-driver-checks/results.tsv', 8000),
             (state / 'checklist-driver-checks/output.log', 0),
             (project / 'DEFECTS.md', 2000)]
    for path, limit in files:
        lines.append('\n### ' + str(path))
        if not path.resolve().is_relative_to(project):
            lines.append('Outside project; not loaded.')
            continue
        try:
            digest = hashlib.sha256()
            size = 0
            excerpt = b''
            with path.open('rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
                    size += len(chunk)
                    if len(excerpt) < limit:
                        excerpt += chunk[:limit-len(excerpt)]
        except OSError:
            lines.append('Missing or unreadable; no result inferred.')
            continue
        lines.append(f'{size} bytes; SHA-256 {digest.hexdigest()}')
        if limit:
            lines.append(excerpt.decode('utf-8', errors='replace'))
        if size > limit:
            lines.append('[Read remaining evidence directly at this path.]')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    print(render(*sys.argv[1:3]), end='')
