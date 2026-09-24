#!/usr/bin/env python3
"""IMPLEMENTATION_NOTES.md as JSON fragments, merged incrementally.

Every other artifact this migration converted is written by one model turn,
so "ask for JSON instead of Markdown" is purely additive: detect JSON, else
fall back to the existing Markdown parsing. IMPLEMENTATION_NOTES.md cannot
follow that pattern unmodified -- both drivers build it by literally
appending text across multiple cold invocations (one per plan step, or one
per parallel worker), and a single JSON object cannot be assembled by string
concatenation the way a Markdown table can.

Instead, each invocation writes its own small JSON *fragment* to its own
path. The driver accumulates fragments (recorded verbatim in the canonical
`.uncle/workflow/documents/IMPLEMENTATION_NOTES.json`) and re-renders
`.uncle/docs/IMPLEMENTATION_NOTES.md` from all of them after every step, so
the next cold invocation still finds a normal Markdown document to read.

A fragment that isn't valid JSON (a legacy handoff, or a driver-synthesized
fallback for a worker that produced nothing) is preserved as `raw_markdown`
rather than rejected -- losing a step's only record because of a format
mismatch would be strictly worse than the Markdown-only behavior this
replaces.
"""
import importlib.util
import json
import sys
from pathlib import Path


def _artifact_json():
    spec = importlib.util.spec_from_file_location(
        'artifact_json', str(Path(__file__).resolve().parent / 'artifact_json.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _esc(value):
    return str(value).replace('|', r'\|').replace('\n', ' ')


def _load_fragment(path):
    text = Path(path).read_text(encoding='utf-8')
    stripped = _artifact_json().unfence_json(text)
    try:
        payload = _artifact_json().loads_response_json(text)
    except ValueError:
        return {'raw_markdown': text}
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' \
            or payload.get('kind') not in ('implementation-notes', 'implementation-notes-fragment'):
        return {'raw_markdown': text}
    return payload


def render_fragment_body(payload):
    lines = []
    changed = payload.get('changed_files') or []
    if changed:
        lines += ['### Files changed', '']
        for entry in changed:
            if isinstance(entry, dict):
                extra = [entry[key] for key in ('purpose', 'plan_step', 'behavior_or_invariant') if entry.get(key)]
                extra_text = '; '.join(str(value) for value in extra)
                lines.append('- `%s`%s' % (entry['path'], ' — ' + extra_text if extra_text else ''))
            else:
                lines.append('- ' + str(entry))
        lines.append('')
    deviations = payload.get('deviations') or []
    if deviations:
        lines += ['### Deviations', '']
        for entry in deviations:
            if isinstance(entry, dict):
                lines.append('- `%s`: %s' % (entry.get('file', ''), entry.get('reason', '')))
            else:
                lines.append('- ' + str(entry))
        lines.append('')
    unresolved = payload.get('unresolved_concerns') or []
    if unresolved:
        lines += ['### Unresolved concerns', ''] + ['- ' + str(entry) for entry in unresolved] + ['']
    raw = payload.get('raw_markdown')
    if raw and raw.strip():
        lines += [raw.strip(), '']
    return lines


def render_deliveries_table(deliveries):
    seen = {}
    order = []
    for entry in deliveries:
        identifier = entry['id']
        if identifier not in seen:
            order.append(identifier)
        seen[identifier] = entry
    lines = ['## Acceptance delivery', '', '| ID | Status | Changed code | Observed targeted verification |', '|---|---|---|---|']
    for identifier in order:
        entry = seen[identifier]
        lines.append('| %s | %s | %s | %s |' % (
            identifier, _esc(entry.get('status', '')), _esc(entry.get('changed_code', '')),
            _esc(entry.get('observed_verification', ''))))
    lines.append('')
    return lines


def merge_and_render(fragments):
    if not fragments:
        raise ValueError('no implementation-notes fragments to render')
    lines = ['# Implementation notes', '']
    multi = len(fragments) > 1
    all_deliveries, all_blockers = [], []
    for index, fragment in enumerate(fragments, 1):
        if multi:
            lines += ['## %s' % (fragment.get('_label') or ('Step %d' % index)), '']
        lines += render_fragment_body(fragment)
        all_deliveries += fragment.get('deliveries') or []
        all_blockers += fragment.get('plan_blockers') or []
    if all_deliveries:
        lines += render_deliveries_table(all_deliveries)
    if all_blockers:
        lines += ['```plan-blockers', json.dumps(all_blockers, indent=2), '```', '']
    return '\n'.join(lines)


def _accumulator_path(project):
    return Path(project) / '.uncle/workflow/documents/IMPLEMENTATION_NOTES.json'


def _load_accumulator(project):
    path = _accumulator_path(project)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            return []
        if isinstance(data, dict) and isinstance(data.get('fragments'), list):
            return data['fragments']
    return []


def _write_accumulator(project, fragments):
    path = _accumulator_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'schema': 'uncle.artifact/v1', 'kind': 'implementation-notes',
                                 'fragments': fragments}, indent=2) + '\n', encoding='utf-8')


def reset(project):
    _accumulator_path(project).unlink(missing_ok=True)


def append(project, fragment_path, target='.uncle/docs/IMPLEMENTATION_NOTES.md', label=None):
    """Add one step's fragment to the running accumulator and re-render the
    merged document. Never raises on a malformed fragment -- it degrades to
    raw_markdown -- so one bad step cannot lose every other step's record."""
    fragment = _load_fragment(fragment_path)
    if label:
        fragment = dict(fragment, _label=label)
    fragments = _load_accumulator(project) + [fragment]
    _write_accumulator(project, fragments)
    rendered = merge_and_render(fragments)
    (Path(project) / target).write_text(rendered, encoding='utf-8')
    return rendered


def validate(project, path='.uncle/docs/IMPLEMENTATION_NOTES.md', require_json=False):
    """Single-invocation ingestion: the whole document is one model turn's
    output, so it is exactly one fragment. Returns True and rewrites the file
    in canonical rendered form when the response was JSON; returns False,
    unchanged, when it's legacy Markdown."""
    full_path = Path(project) / path
    text = full_path.read_text(encoding='utf-8')
    stripped = _artifact_json().unfence_json(text)
    if not stripped.startswith('{'):
        if require_json:
            # A prior JSON ingestion has already rendered this file into its
            # human review view.  Its canonical source remains authoritative;
            # do not mistake that generated Markdown for a fresh model reply.
            canonical = _accumulator_path(project)
            if canonical.is_file():
                _load_accumulator(project)
                return True
            raise ValueError('IMPLEMENTATION_NOTES.md must be JSON; Markdown is a rendered view only')
        return False
    payload = json.loads(stripped)
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'implementation-notes':
        raise ValueError('wrong implementation-notes JSON schema')
    _write_accumulator(project, [payload])
    # A model writes the canonical packet. Never overwrite that transport
    # with the Markdown review view.
    if full_path.resolve() != _accumulator_path(project).resolve():
        full_path.write_text(merge_and_render([payload]), encoding='utf-8')
    return True


def render(project, target='.uncle/docs/IMPLEMENTATION_NOTES.md'):
    fragments = _load_accumulator(project)
    if not fragments:
        raise ValueError('canonical implementation-notes JSON is missing')
    path = Path(project) / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merge_and_render(fragments), encoding='utf-8')


if __name__ == '__main__':
    try:
        action = sys.argv[1]
        if action == 'append':
            project, fragment_path = sys.argv[2], sys.argv[3]
            target = sys.argv[4] if len(sys.argv) > 4 else '.uncle/docs/IMPLEMENTATION_NOTES.md'
            label = sys.argv[5] if len(sys.argv) > 5 else None
            append(project, fragment_path, target, label)
        elif action == 'validate':
            project = sys.argv[2]
            path = sys.argv[3] if len(sys.argv) > 3 else '.uncle/docs/IMPLEMENTATION_NOTES.md'
            validate(project, path, '--require-json' in sys.argv[4:])
        elif action == 'reset':
            reset(sys.argv[2])
        elif action == 'render':
            render(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else '.uncle/docs/IMPLEMENTATION_NOTES.md')
        else:
            raise ValueError('unknown action: ' + action)
    except (OSError, ValueError, KeyError) as error:
        print(f'{sys.argv[2] if len(sys.argv) > 2 else "?"}: {error}. Correct the saved document and resume.', file=sys.stderr)
        raise SystemExit(1)
