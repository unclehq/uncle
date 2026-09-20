"""Deterministic, no-model-call shape repair for the Acceptance gate table
shared by TEST_REVIEW.md, VERIFICATION_REPORT.md, and PREFLIGHT_REPORT.md.

acceptance.sh's parser requires a table headed exactly `| ID | Required |
Status | Evidence |` directly under a literal `## Acceptance gate` heading.
A model has repeatedly produced the same real, complete per-check table --
right IDs, right statuses, nothing to disagree with -- under a different
heading ("## Summary") and/or a different column set (e.g. `Check ID |
Description | Required | Status`, with each check's real evidence sentences
left in a separate "Status per Group" narrative instead of a per-row Evidence
cell). Asking again does not fix a model that believes its shape already
satisfies the requirement, and the driver's own one-shot retry reproduced
the identical wrong shape a second time on a real run.

This never invents a status or drops a row. It only relocates a heading and,
where the source table lacks a distinct Evidence column, copies each row's
own existing description text into one (the model's own words, not
manufactured), or missing that, keys evidence off a same-ID line in a
"## Status per Group"-style narrative section elsewhere in the document.
"""
import re

ID_NAMES = ('id', 'check id', 'check')
REQUIRED_NAMES = ('required',)
STATUS_NAMES = ('status', 'result')
EVIDENCE_NAMES = ('evidence',)
DESCRIPTION_NAMES = ('description', 'notes', 'summary', 'action')


def _role(cell, names):
    return cell.strip().lower() in names


def _table_at(lines, i):
    """(header_cells, row_start) if a Markdown table's header+separator sits
    at line i, else None."""
    line = lines[i].strip()
    if not (line.startswith('|') and line.endswith('|')):
        return None
    if i + 1 >= len(lines):
        return None
    header = [cell.strip() for cell in line[1:-1].split('|')]
    if not re.fullmatch(r'\|(?:\s*:?-{3,}:?\s*\|){%d}' % len(header), lines[i + 1].strip()):
        return None
    return header


def _row_cells(line, width):
    line = line.strip()
    if not (line.startswith('|') and line.endswith('|')):
        return None
    cells = [cell.strip() for cell in line[1:-1].split('|')]
    return cells if len(cells) == width else None


def _narrative_evidence(text):
    """{id: evidence sentence} from a "## Status per Group"-shaped section:
    numbered/bulleted lines naming a check ID in bold, then its result and
    supporting text after the LAST dash/arrow separator on the line (an
    early one is typically part of "->" or the bold status itself, e.g.
    "**MC-1** (keyboard) -> **PASS** - decimal input works"). Best-effort;
    missing entries simply leave that row without a narrative fallback."""
    out = {}
    id_pattern = re.compile(r'\*\*([A-Za-z0-9][A-Za-z0-9_./-]*)\*\*')
    for raw in text.splitlines():
        line = raw.strip()
        match = id_pattern.search(line)
        if not match:
            continue
        cut = max(line.rfind(sep) for sep in ('—', '--', ' - '))
        if cut == -1:
            continue
        evidence = line[cut:].lstrip('—- ').strip()
        if evidence:
            out[match[1]] = evidence
    return out


def normalize_acceptance_shape(text):
    """The corrected text, or the original text unchanged when no single
    unambiguous acceptance-shaped table exists (acceptance_problem then
    reports the real defect)."""
    if re.search(r'^## Acceptance gate[ \t\r]*$', text, re.M):
        return text
    lines = text.splitlines()
    narrative = _narrative_evidence(text)
    candidates = []
    for i in range(len(lines) - 1):
        header = _table_at(lines, i)
        if header is None:
            continue
        lowered = [cell.lower() for cell in header]
        id_col = next((idx for idx, cell in enumerate(lowered) if cell in ID_NAMES), None)
        required_col = next((idx for idx, cell in enumerate(lowered) if cell in REQUIRED_NAMES), None)
        status_col = next((idx for idx, cell in enumerate(lowered) if cell in STATUS_NAMES), None)
        if id_col is None or required_col is None or status_col is None:
            continue
        evidence_col = next((idx for idx, cell in enumerate(lowered) if cell in EVIDENCE_NAMES), None)
        description_col = next((idx for idx, cell in enumerate(lowered) if cell in DESCRIPTION_NAMES), None)
        candidates.append((i, len(header), id_col, required_col, status_col, evidence_col, description_col))
    if len(candidates) != 1:
        # Zero: no recognizable table. More than one: which is the real
        # answer is not this function's call to make -- never guess between
        # competing tables the way acceptance_result never picks a verdict.
        return text
    i, width, id_col, required_col, status_col, evidence_col, description_col = candidates[0]
    rows = ['| ID | Required | Status | Evidence |', '|---|---|---|---|']
    j = i + 2
    while j < len(lines):
        cells = _row_cells(lines[j], width)
        if cells is None:
            break
        identifier = cells[id_col]
        if evidence_col is not None:
            evidence = cells[evidence_col]
        elif description_col is not None:
            evidence = cells[description_col]
        else:
            evidence = narrative.get(identifier, '')
        rows.append('| %s | %s | %s | %s |' % (identifier, cells[required_col], cells[status_col], evidence))
        j += 1
    if len(rows) <= 2:
        return text
    lines[i:j] = ['## Acceptance gate', ''] + rows
    return '\n'.join(lines) + ('\n' if text.endswith('\n') else '')


def main(path):
    from pathlib import Path
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    normalized = normalize_acceptance_shape(text)
    if normalized != text:
        p.write_text(normalized, encoding='utf-8')
        return True
    return False


if __name__ == '__main__':
    import sys
    sys.exit(0 if main(sys.argv[1]) else 1)
