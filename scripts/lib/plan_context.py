#!/usr/bin/env python3
"""JSON ingestion for the plan family: PROJECT_PLAN.md, UPDATED_PROJECT_PLAN.md,
CHANGE_SPEC.md, CHANGE_PLAN.md.

Unlike the reviewer-authored artifacts (ADVERSARIAL_REVIEW.md, FINAL_AUDIT.md,
TEST_REVIEW.md), these are written by an agent with Write-tool access and the
drivers have never run a structural validator against them beyond existence
and size -- there is no baseline to make stricter without risking a
currently-valid plan being rejected for a shape nobody has ever checked.

So this module is purely additive: it only acts when the document is JSON
(after stripping a possible fence), which never happens for a plan an agent
wrote directly with its Write tool. A Markdown plan -- the entire existing
population of them -- passes through untouched. Only a plan returned as chat
text (the self-hosted fallback path, or any runner a future prompt points at
this contract) takes the JSON route.
"""
import importlib.util
from pathlib import Path

_LIB = Path(__file__).resolve().parent


def _artifact_json():
    spec = importlib.util.spec_from_file_location('artifact_json', _LIB / 'artifact_json.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ingest_plan(path, project='.', protected=True):
    """PROJECT_PLAN.md / UPDATED_PROJECT_PLAN.md / CHANGE_PLAN.md. Returns
    True if the document was JSON (rendered and exported either way --
    ValueError propagates so the caller reports the real defect), False if
    it was left alone as ordinary Markdown."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise ValueError('Invalid plan JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'plan':
        raise ValueError('wrong plan JSON schema')
    rendered = module.render_plan(payload, protected=protected)
    Path(path).write_text(rendered, encoding='utf-8')
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='plan'))
    return True


def ingest_change_spec(path, project='.'):
    """CHANGE_SPEC.md. Same purely-additive contract as ingest_plan()."""
    import json
    module = _artifact_json()
    text = Path(path).read_text(encoding='utf-8')
    stripped = module.unfence_json(text)
    if not stripped.startswith('{'):
        return False
    try:
        payload = json.loads(stripped)
    except ValueError as error:
        raise ValueError('Invalid change-spec JSON response: ' + str(error)) from error
    if payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != 'change-spec':
        raise ValueError('wrong change-spec JSON schema')
    rendered = module.render_change_spec(payload)
    Path(path).write_text(rendered, encoding='utf-8')
    module.write(project, Path(path).name, dict(payload, schema='uncle.artifact/v1', kind='change-spec'))
    return True


if __name__ == '__main__':
    import sys
    action, path = sys.argv[1], sys.argv[2]
    project = sys.argv[3] if len(sys.argv) > 3 else '.'
    try:
        if action == 'plan':
            ingest_plan(path, project, protected=True)
        elif action == 'plan-unprotected':
            ingest_plan(path, project, protected=False)
        elif action == 'change-spec':
            ingest_change_spec(path, project)
        else:
            raise SystemExit('unknown action: ' + action)
    except ValueError as error:
        print(f'{path}: {error}. Correct the saved document and resume.', file=sys.stderr)
        raise SystemExit(1)
