#!/usr/bin/env python3
"""Recover a JSON worker packet from a runner's durable event log."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


def artifact_json():
    spec = importlib.util.spec_from_file_location(
        'artifact_json', str(Path(__file__).resolve().parent / 'artifact_json.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def texts(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('text', 'result', 'content') and isinstance(child, str):
                yield child
            else:
                yield from texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from texts(child)


def json_candidates(text):
    """Yield JSON objects embedded in an LLM response.

    Runners are instructed to return a bare packet, but some OpenCode models
    put the otherwise complete packet after a short summary and wrap it in a
    ``json`` fence.  Treating that as a missing packet makes a successfully
    completed checklist fail.  This deliberately recovers only complete JSON
    objects; schema/kind validation below remains the authority.
    """
    yield text
    for fenced in re.findall(r'```(?:json)?\s*(.*?)\s*```', text,
                              flags=re.IGNORECASE | re.DOTALL):
        yield fenced
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', text):
        try:
            value, _end = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield json.dumps(value)


def recover(log, output, kind):
    candidates = []
    for line in Path(log).read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        priority = 1 if event.get('type') == 'result' else 0
        for text in texts(event):
            for candidate in json_candidates(text):
                try:
                    payload = artifact_json().loads_response_json(candidate)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(payload, dict) and payload.get('schema') == 'uncle.artifact/v1' and payload.get('kind') == kind:
                    candidates.append((priority, payload))
    if not candidates:
        raise ValueError('no valid %s in final worker response' % kind)
    # A result event is the runner's final response; otherwise use the last
    # matching assistant event. Never manufacture a packet from narration.
    _, payload = sorted(candidates, key=lambda item: item[0])[-1]
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


_STATUS = {'PASS', 'FAIL', 'BLOCKED-SETUP', 'BLOCKED-HUMAN',
           'BLOCKED-IMPOSSIBLE', 'NOT RUN'}


def _assigned_ids(prompt):
    """Return the IDs the driver assigned to one checklist worker."""
    return re.findall(r'^- Execute `([^`]+)`\.',
                      Path(prompt).read_text(encoding='utf-8', errors='replace'), re.M)


def _checklist_rows(checklist):
    payload = json.loads(Path(checklist).read_text(encoding='utf-8'))
    return {row.get('id'): row for row in payload.get('checks', []) if isinstance(row, dict)}


def _summary_statuses(text, assigned):
    """Recover only explicit per-ID statuses from a nonconforming final reply.

    This is intentionally a very narrow escape hatch for agent workers (which
    do not have an output-file boundary like reviewers).  It never treats a
    successful process exit, an unqualified "all done", or an omitted row as
    PASS.  A model must state a status beside the assigned check ID, or use a
    small JSON results map naming that ID.
    """
    found = {}
    for candidate in json_candidates(text):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        results = value.get('results') if isinstance(value, dict) else None
        if isinstance(results, dict):
            for identifier in assigned:
                item = results.get(identifier)
                if not isinstance(item, dict):
                    continue
                status = str(item.get('status', item.get('result', ''))).upper()
                if status in _STATUS:
                    found[identifier] = (status, str(item.get('reasoning', item.get('evidence', ''))))
    for identifier in assigned:
        # Handles both Markdown tables ("| **MC-1** | PASS | …") and the
        # terse summaries local models commonly produce ("MC-1 FAIL — …").
        match = re.search(r'(?:\*\*)?' + re.escape(identifier) +
                          r'(?:\*\*)?\s*(?:\||:|—|-)?\s*(?:\*\*)?'
                          r'(PASS|FAIL|BLOCKED-SETUP|BLOCKED-HUMAN|BLOCKED-IMPOSSIBLE|NOT RUN)\b'
                          r'(?:\*\*)?\s*([^\n]*)', text, re.I)
        if match:
            found[identifier] = (match.group(1).upper(), match.group(2).strip())
    return found


def recover_checklist_summary(log, output, checklist, prompt):
    """Convert an explicit checklist-worker summary into a canonical packet.

    The canonical checklist supplies action and expected-result fields; the
    worker supplies only its observed status/evidence.  Missing statuses are
    represented as NOT RUN rather than invented as PASS, preserving the
    workflow's fail-closed evidence semantics while avoiding a pointless
    whole-stage restart caused solely by JSON envelope noncompliance.
    """
    assigned = _assigned_ids(prompt)
    checks = _checklist_rows(checklist)
    if not assigned or any(identifier not in checks for identifier in assigned):
        raise ValueError('assigned checklist IDs are unavailable for summary recovery')
    final_text = ''
    for line in Path(log).read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') == 'result':
            values = list(texts(event))
            if values:
                final_text = '\n'.join(values)
    if not final_text:
        raise ValueError('no final worker response available for checklist summary recovery')
    statuses = _summary_statuses(final_text, assigned)
    if not statuses:
        raise ValueError('final worker response names no explicit checklist result')
    results = []
    for identifier in assigned:
        check = checks[identifier]
        status, detail = statuses.get(identifier, ('NOT RUN', 'Worker did not state a result for this assigned check.'))
        note = detail or 'Explicit status recovered from the worker final response.'
        results.append({
            'id': identifier,
            'action': str(check.get('exact_action', '')).strip(),
            'expected_result': str(check.get('expected_result', '')).strip(),
            'actual_result': note,
            'evidence': 'Driver-normalized from an explicit worker status: ' + note,
            'status': status,
            'defect_reference': 'None' if status == 'PASS' else note,
        })
    payload = {'schema': 'uncle.artifact/v1', 'kind': 'checklist-execution-worker-packet',
               'results': results}
    Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('log')
    parser.add_argument('output')
    parser.add_argument('--kind', required=True)
    parser.add_argument('--checklist')
    parser.add_argument('--prompt')
    args = parser.parse_args(argv)
    try:
        recover(args.log, args.output, args.kind)
    except (OSError, ValueError) as error:
        if (args.kind == 'checklist-execution-worker-packet' and args.checklist
                and args.prompt):
            try:
                recover_checklist_summary(args.log, args.output, args.checklist, args.prompt)
                print('worker packet recovery: normalized explicit checklist summary', file=sys.stderr)
                return 0
            except (OSError, ValueError) as summary_error:
                print('worker packet recovery: %s; checklist summary recovery: %s' %
                      (error, summary_error), file=sys.stderr)
                return 1
        print('worker packet recovery: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
