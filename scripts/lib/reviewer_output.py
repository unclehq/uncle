#!/usr/bin/env python3
"""Is a reviewer's reply the document it was asked for, or a note about it?

Every runner checked that the model replied: non-empty text, a result event,
`is_error` false, a clean finish reason. None checked that the reply was a
document. A model that ends its turn saying "I will now produce
.uncle/docs/ADVERSARIAL_REVIEW.md with concrete findings" satisfies all of those, and the
announcement gets written to the artifact as though it were the review.

That happened on unclehq/uncle#59: the reviewer's log ended with a to-do list
whose last item was "Produce .uncle/docs/ADVERSARIAL_REVIEW.md with concrete findings", the
runner reported success, and the artifact was a 31-line chat summary with no
findings. The stage then failed three checks later on a format error, which
described a symptom and hid what actually went wrong.

Weak models make this likely; nothing in any runner makes it impossible, so the
check belongs in one place that all four use.

The test is deliberately shallow: a reviewer artifact is structured markdown, so
it carries at least one heading or one table row. Judging content is the job of
the stage validators, which know what each document must contain. This only
separates "a document" from "a sentence about a document".
"""
import importlib.util
import json
from pathlib import Path
import re
import sys

_HEADING = re.compile(r'^#{1,6}\s+\S', re.M)
_TABLE_ROW = re.compile(r'^\s*\|.*\|', re.M)
_PLACEHOLDER_ID = re.compile(r'^\s*(?:no\s+finding|none|n/?a|tbd)(?:\s|$|[-_:])', re.I)


def _unfence_json():
    spec = importlib.util.spec_from_file_location('artifact_json', Path(__file__).with_name('artifact_json.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.unfence_json


def _loads_response_json(text):
    spec = importlib.util.spec_from_file_location('artifact_json', Path(__file__).with_name('artifact_json.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.loads_response_json(text)


def looks_like_document(text):
    if _HEADING.search(text) or _TABLE_ROW.search(text):
        return True
    # A structured artifact response (Issue: JSON-first agent output):
    # the reviewer's whole reply is one JSON object naming its own schema,
    # never a heading or a table row. Models fence a bare-JSON response in
    # ```/```json out of habit as often as not, and just as often add a
    # sentence of narration before or after it despite being told not to --
    # unfence_json() extracts the object from either, tolerating both, the
    # same way every other JSON-detection site in this codebase does.
    stripped = _unfence_json()(text)
    if stripped.startswith('{'):
        try:
            payload = json.loads(stripped)
        except ValueError:
            return False
        return isinstance(payload, dict) and payload.get('schema') == 'uncle.artifact/v1'
    return False


def _validate_manual_checklist_json(text, runner):
    """Reject a status update before it can masquerade as a checklist artifact."""
    try:
        payload = _loads_response_json(text)
    except ValueError as error:
        raise ValueError('%s did not return a manual-checklist JSON object: %s' % (runner, error))
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'manual-checklist':
        raise ValueError('%s returned the wrong manual-checklist JSON schema' % runner)
    checks = payload.get('checks')
    if not isinstance(checks, list) or not checks:
        raise ValueError('%s manual-checklist JSON requires a nonempty checks array' % runner)
    for index, check in enumerate(checks, 1):
        if (not isinstance(check, dict) or not isinstance(check.get('id'), str) or not check['id'].strip()
                or not isinstance(check.get('exact_action'), str) or not check['exact_action'].strip()
                or not isinstance(check.get('expected_result'), str) or not check['expected_result'].strip()):
            raise ValueError('%s manual-checklist check %d requires id, exact_action, and expected_result'
                             % (runner, index))
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


def worker_packet(text, runner='reviewer'):
    """Extract and canonicalize one JSON worker packet from a reviewer reply.

    Unlike a Markdown review, a packet must never retain narration around the
    JSON object: the panel collator reads the saved file as JSON.  Every
    reviewer runner, including the direct Codex path, uses this function.
    """
    payload_text = _unfence_json()(text)
    try:
        payload = _loads_response_json(text)
    except ValueError as error:
        raise ValueError('%s response is not a valid JSON worker packet: %s' % (runner, error))
    if (not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1'
            or not str(payload.get('kind', '')).endswith('-worker-packet')):
        raise ValueError('%s response is not an uncle JSON worker packet' % runner)
    if payload.get('kind') == 'test-review-worker-packet':
        rows = payload.get('rows')
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('status'), str) or not isinstance(row.get('evidence'), str) for row in rows):
            raise ValueError('%s JSON test-review worker packet rows must be an array of id/status/evidence objects' % runner)
        for index, row in enumerate(rows, 1):
            if _PLACEHOLDER_ID.match(row['id']):
                raise ValueError('%s JSON test-review row %d needs a stable finding ID, not placeholder %r'
                                 % (runner, index, row['id'].strip()))
        return json.dumps(payload, indent=2, sort_keys=True) + '\n'
    if payload.get('kind') == 'manual-checklist-worker-packet':
        checks = payload.get('checks')
        if not isinstance(checks, list) or any(not isinstance(check, dict) or not isinstance(check.get('id'), str) or not isinstance(check.get('exact_action'), str) or not isinstance(check.get('expected_result'), str) for check in checks):
            raise ValueError('%s JSON manual-checklist worker packet checks must be an array of id/exact_action/expected_result objects' % runner)
        return json.dumps(payload, indent=2, sort_keys=True) + '\n'
    if not isinstance(payload.get('findings'), list):
        raise ValueError('%s JSON worker packet findings must be an array' % runner)
    required = ('id', 'gap', 'evidence', 'risk', 'required_correction') \
        if payload.get('kind') == 'updated-plan-worker-packet' else ('id', 'summary')
    for index, finding in enumerate(payload['findings'], 1):
        if (not isinstance(finding, dict) or any(not isinstance(finding.get(field), str)
                or not finding[field].strip() for field in required)):
            raise ValueError('%s JSON worker packet finding %d requires nonempty %s' %
                             (runner, index, ' and '.join(required)))
        if _PLACEHOLDER_ID.match(finding['id']):
            raise ValueError('%s JSON worker packet finding %d needs a stable finding ID, not placeholder %r'
                             % (runner, index, finding['id'].strip()))
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


def check(text, runner='reviewer', artifact=None):
    """Return the text, or raise ValueError naming the real failure."""
    if artifact and Path(artifact).name == 'MANUAL_CHECKLIST.md':
        return _validate_manual_checklist_json(text, runner)
    extracted = _unfence_json()(text)
    if extracted.startswith('{'):
        try:
            payload = _loads_response_json(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and str(payload.get('kind', '')).endswith('-worker-packet'):
            return worker_packet(text, runner)
        if isinstance(payload, dict) and payload.get('schema') == 'uncle.artifact/v1':
            # Stream clients can wrap the actual reply in an assistant event.
            # Persist the normalized artifact, never the transport envelope.
            return json.dumps(payload, indent=2, sort_keys=True) + '\n'
    if looks_like_document(text):
        return text
    preview = ' '.join(text.split())[:120]
    raise ValueError(
        '%s returned no document: the response has no heading or table row. '
        'It reads as a summary, a plan, or a promise to write the artifact '
        'rather than the artifact. First words: %s'
        % (runner, preview or '(empty)'))


if __name__ == '__main__':
    # Filter: document on stdin, same document on stdout, or exit 1 with the
    # reason on stderr so the shim can fail before writing the artifact.
    packet = '--packet' in sys.argv[1:]
    args = [arg for arg in sys.argv[1:] if arg != '--packet']
    artifact = None
    if '--artifact' in args:
        position = args.index('--artifact')
        try:
            artifact = args[position + 1]
        except IndexError:
            print('--artifact requires a path', file=sys.stderr)
            raise SystemExit(2)
        del args[position:position + 2]
    runner = args[0] if args else 'reviewer'
    # Windows text mode would translate LF to CRLF on the way to the artifact.
    sys.stdout.reconfigure(newline='\n')
    body = sys.stdin.read()
    try:
        sys.stdout.write(worker_packet(body, runner) if packet else check(body, runner, artifact))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
