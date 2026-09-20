"""Focused final-audit evidence and format-only validation."""
import hashlib
import importlib.util
from pathlib import Path
import re
import sys


def normalize_findings_shape(text):
    """Coerce a close-but-malformed audit into the exact shape `findings()`
    requires, without touching a finding's content, evidence, or verdict.

    Seen twice on the same real audit: a well-formed table (six rows, real
    evidence citations) under a `# Final audit` heading instead of the
    required `## Findings`, and a `Correction` column instead of `Required
    correction`. Both retries this file already has -- the driver's own
    one-shot format retry, and self_hosted.py's generic invalid-document
    retry -- reproduced the identical wrong shape a second time: asking
    again does not fix a model that believes the top-level heading already
    satisfies the requirement. Returns the corrected text, or the original
    text unchanged when no recognizable table is found (validate() then
    reports the real problem).
    """
    lines = text.splitlines()
    table_start = None
    for i in range(len(lines) - 1):
        line = lines[i].strip()
        if not (line.startswith('|') and line.endswith('|')):
            continue
        header = [cell.strip().lower() for cell in line[1:-1].split('|')]
        if 'id' not in header or not any(cell in ('blocks', 'blocks completion') for cell in header):
            continue
        if re.fullmatch(r'\|(?:\s*:?-{3,}:?\s*\|)+', lines[i + 1].strip()):
            table_start = i
            break
    if table_start is None:
        return text
    # Independent of each other: a real audit has shown up missing the
    # heading with a correct column name, and -- reproduced on a separate
    # run -- with the heading present and only the column name wrong. An
    # early return on "heading already there" skipped the column check
    # entirely that second time and let this exact failure straight through.
    has_heading = re.search(r'^##\s+Findings\s*$', text, re.M)
    if not has_heading:
        lines[table_start:table_start] = ['## Findings', '']
        table_start += 2
    header_index = table_start
    cells = lines[header_index][1:-1].split('|')
    for i, cell in enumerate(cells):
        if cell.strip().lower() in ('correction', 'fix', 'required fix', 'suggested correction'):
            cells[i] = ' Required correction '
    lines[header_index] = '|' + '|'.join(cells) + '|'
    return '\n'.join(lines) + ('\n' if text.endswith('\n') else '')


def validate(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    last = text.strip().splitlines()[-1].strip().strip('#*_ ')
    last = re.sub(r'^Conclusion:[ \t]*', '', last).strip('*_ ')
    if last not in ('READY', 'READY WITH NON-BLOCKING ISSUES', 'NOT READY'):
        raise ValueError('Missing final audit verdict')
    spec = importlib.util.spec_from_file_location('audit_findings', Path(__file__).with_name('audit-findings.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Normalize only the verdict decoration accepted by the driver's classifier.
    body = text.strip().rsplit('\n', 1)[0] + '\n' + last + '\n'
    try:
        blockers = module.findings(body, require_blockers=last == 'NOT READY')
    except ValueError:
        normalized = normalize_findings_shape(body)
        if normalized == body:
            raise
        blockers = module.findings(normalized, require_blockers=last == 'NOT READY')
        # Only reached once the normalized shape actually parses: write the
        # corrected document back so downstream stages read the same text
        # this validation just accepted, exactly like the manual repair this
        # replaces.
        path.write_text(normalized, encoding='utf-8')
    if blockers and last != 'NOT READY':
        raise ValueError('Ready verdict contradicts blocking findings')


def render(project, state):
    project, state = Path(project).resolve(), Path(state).resolve()
    files = [(project / n, 3000) for n in ('VERIFICATION_REPORT.md', 'DEFECTS.md', 'MANUAL_CHECKLIST.md')]
    files += [(state / n, 3000) for n in ('delivery-summary.tsv', 'implementation-completion.txt', 'checklist-driver-checks/results.tsv')]
    files += [(state / 'change.diff', 0), (state / 'checklist-driver-checks/output.log', 0)]
    files += [(p, 1000) for p in sorted((state / 'waivers').glob('*')) if p.is_file()]
    lines = ['\n## Driver final-audit evidence packet',
             'Current inventory; hashes are identities, not PASS evidence.',
             'Excerpts may omit rows. Read required inputs and relevant evidence directly.']
    budget = 24000
    for path, limit in files:
        if not path.resolve().is_relative_to(project):
            continue
        try:
            digest, excerpt, size = hashlib.sha256(), b'', 0
            with path.open('rb') as stream:
                while chunk := stream.read(65536):
                    digest.update(chunk)
                    size += len(chunk)
                    excerpt += chunk[:max(0, min(limit, budget) - len(excerpt))]
            lines.append(f'\n{path}: {size} bytes; SHA-256 {digest.hexdigest()}')
            lines.append(excerpt.decode('utf-8', errors='replace'))
            budget -= len(excerpt)
            if len(excerpt) < size:
                lines.append('[Read remaining contents directly.]')
        except OSError:
            lines.append(f'{path}: unavailable; no evidence inferred.')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    if sys.argv[1] == '--validate':
        try:
            validate(sys.argv[2])
        except (OSError, ValueError, IndexError) as error:
            print(f'Audit format invalid: {error}. Correct FINAL_AUDIT.md and resume; no checks need rerunning.', file=sys.stderr)
            raise SystemExit(1)
    else:
        print(render(*sys.argv[1:3]), end='')
