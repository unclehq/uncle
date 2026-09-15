"""Current inputs for targeted plan revision, without repository discovery."""
import hashlib
from pathlib import Path
import sys


def render(project, state, family):
    root, state = Path(project).resolve(), Path(state).resolve()
    paths = [root/'ADVERSARIAL_REVIEW.md']
    if family == 'change':
        paths += [state/'CHANGE_PLAN.pre-review.md', root/'CHANGE_SPEC.md']
    else:
        paths += [root/'PROJECT_PLAN.md', root/'REQUIREMENTS.md', root/'REQUIREMENTS_INTERPRETATION.md']
    lines = ['\n## Driver plan revision packet',
             'Revise the existing plan against the findings. Hashes identify current inputs, not approval or correctness.',
             'Preserve unaffected decisions and IDs; read omitted content before revising.']
    for path in paths:
        if not path.resolve().is_relative_to(root):
            continue
        try:
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                excerpt = stream.read(8000)
                digest.update(excerpt)
                while chunk := stream.read(65536):
                    digest.update(chunk)
            lines += [f'\n{path}: SHA-256 {digest.hexdigest()}', excerpt.decode('utf-8', errors='replace')]
            if path.stat().st_size > len(excerpt):
                lines.append('[Truncated; read the remaining input directly.]')
        except OSError:
            lines.append(f'{path}: unavailable; read the required input directly before proceeding.')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    print(render(*sys.argv[1:4]), end='')
