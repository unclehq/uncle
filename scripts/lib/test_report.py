#!/usr/bin/env python3
"""JSON-authoritative implementation test reports with Markdown views."""
import importlib.util
import json
import sys
from pathlib import Path


def artifact_json():
    spec = importlib.util.spec_from_file_location(
        'artifact_json', str(Path(__file__).resolve().parent / 'artifact_json.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _esc(value):
    return str(value).replace('|', r'\|').replace('\n', ' ')


def _validate(payload, kind):
    expected = 'change-test-report' if kind == 'change' else 'automated-test-report'
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != expected:
        # Observed (canopy issue #4): the agent delivered a well-formed JSON
        # object shaped like a different artifact entirely (a checklist-style
        # {title, checks, regressions_or_gaps, required_follow_up}), not this
        # one's {schema, kind, commands}. A bare "wrong schema" gave it
        # nothing to fix from; naming the required kind/schema pair and what
        # was actually found lets a retry correct the one thing that matters.
        found_kind = payload.get('kind') if isinstance(payload, dict) else None
        found_keys = ', '.join(sorted(payload.keys())) if isinstance(payload, dict) else 'not an object'
        raise ValueError(
            'wrong %s JSON schema: need {"schema":"uncle.artifact/v1","kind":"%s",...}; '
            'found kind=%r, top-level keys: %s' % (expected, expected, found_kind, found_keys)
        )
    commands = payload.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('%s requires at least one command result' % expected)
    # implement-change.md's own "Output economy" section (still written for
    # the pre-JSON Markdown report) tells the agent N/A and NOT RUN are
    # deliberately not interchangeable -- N/A means the check does not apply
    # to this change, NOT RUN means it applies and was skipped -- and to
    # never collapse that distinction. The JSON contract a few lines above it
    # in the same prompt never had N/A in its status enum, so every report
    # that correctly followed the first instruction failed this one
    # (canopy issue #4, command results 9-11: "Migration tests"/"Rollback
    # test"/"Performance checks", genuinely inapplicable to this change).
    # Widening the enum to match the deliberate distinction the prompt asks
    # for, rather than asking the prompt to give it up.
    allowed = {'PASS', 'FAIL', 'BLOCKED', 'NOT RUN', 'DRIVER PENDING', 'N/A'}
    for index, row in enumerate(commands, 1):
        if not isinstance(row, dict) or not row.get('command'):
            raise ValueError('command result %d is missing command' % index)
        if row.get('status') not in allowed:
            raise ValueError('command result %d has invalid status' % index)
        if not row.get('output'):
            raise ValueError('command result %d is missing output' % index)
        requirements = row.get('requirements', [])
        if isinstance(requirements, str):
            # Observed (canopy issue #4): every command result wrote this as
            # a natural comma-joined string ("AC-4, AC-5, I-3", or "None
            # stated" for an empty one) instead of the required array --
            # not a one-off slip, every row in the report did it the same
            # way, which reads as the obvious way to write "the requirements
            # for this row" in prose. Normalizing here, the same tolerant
            # spirit as the dispositions/change_impact_table aliases, means
            # a report that is otherwise complete and correct is not thrown
            # away for a type this common wording gets wrong.
            stripped = requirements.strip()
            if not stripped or stripped.lower() in ('none', 'none stated', 'n/a', 'na'):
                requirements = []
            else:
                requirements = [item.strip() for item in stripped.split(',') if item.strip()]
            row['requirements'] = requirements
        if not isinstance(requirements, list):
            raise ValueError('command result %d requirements must be an array' % index)
    if not isinstance(payload.get('coverage_gaps', []), list):
        raise ValueError('coverage_gaps must be an array')
    if not isinstance(payload.get('next_action', ''), str):
        raise ValueError('next_action must be a string')


def render(payload, kind):
    _validate(payload, kind)
    title = 'Change test report' if kind == 'change' else 'Automated test report'
    lines = ['# ' + title, '', '## Command results', '',
             '| Command | Status | Meaningful output | Requirements |',
             '|---|---|---|---|']
    for row in payload['commands']:
        lines.append('| %s | %s | %s | %s |' % (
            _esc(row['command']), row['status'], _esc(row['output']),
            _esc(', '.join(str(item) for item in row.get('requirements', [])) or 'None stated')))
    lines += ['', '## Coverage gaps', '']
    lines += ['- ' + str(item) for item in payload.get('coverage_gaps', [])] or ['- None stated']
    lines += ['', '## Next action', '', payload.get('next_action') or 'None.', '']
    return '\n'.join(lines)


def ingest(project, kind, source):
    name = 'CHANGE_TEST_REPORT.md' if kind == 'change' else 'AUTOMATED_TEST_REPORT.md'
    target = Path(project) / source
    raw = artifact_json().unfence_json(target.read_text(encoding='utf-8'))
    canonical_path = artifact_json().path(project, name)
    view = Path(project) / '.uncle/docs' / name
    # New contract: reviewers write this exact canonical path. Validate it in
    # place, then render a disposable Markdown view.
    if target.resolve() == canonical_path.resolve():
        payload = json.loads(raw)
        _validate(payload, kind)
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        view.parent.mkdir(parents=True, exist_ok=True)
        view.write_text(render(payload, kind), encoding='utf-8')
        return
    if not raw.startswith('{'):
        if canonical_path.is_file():
            # This is an already-rendered review view from a prior JSON
            # ingestion, not an unstructured model output.
            _validate(artifact_json().read(project, name), kind)
            return
        raise ValueError('%s must be JSON; Markdown is a rendered view only' % name)
    payload = json.loads(raw)
    _validate(payload, kind)
    artifact_json().write(project, name, payload)
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text(render(payload, kind), encoding='utf-8')


if __name__ == '__main__':
    try:
        if sys.argv[1] != 'validate':
            raise ValueError('unknown action')
        ingest(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else (
            '.uncle/docs/CHANGE_TEST_REPORT.md' if sys.argv[3] == 'change' else '.uncle/docs/AUTOMATED_TEST_REPORT.md'))
    except (IndexError, OSError, ValueError, json.JSONDecodeError) as error:
        print('%s: %s. Correct the saved JSON artifact and resume.' % (sys.argv[2] if len(sys.argv) > 2 else '?', error), file=sys.stderr)
        raise SystemExit(1)
