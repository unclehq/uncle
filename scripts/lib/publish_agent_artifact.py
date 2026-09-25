#!/usr/bin/env python3
"""Publish a parent agent's final JSON artifact for every runner.

Runner adapters intentionally only normalize their event streams.  This shared
driver boundary owns the operational contract: extract the final JSON object,
validate its stage schema, write `.uncle/workflow/documents/*.json`, and only
then render the human Markdown view.
"""
import json
import sys
from pathlib import Path


def module(name):
    import importlib.util
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


ARTIFACT = {
    'requirements': ('REQUIREMENTS_INTERPRETATION.md', 'requirements-interpretation'),
    'project-plan': ('PROJECT_PLAN.md', 'plan'),
    'updated-plan': ('UPDATED_PROJECT_PLAN.md', 'plan'),
    'updated-change-plan': ('CHANGE_PLAN.md', 'change-plan'),
}


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


def response(log, kind):
    artifact_json = module('artifact_json')
    candidates = []
    for line in Path(log).read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        candidates.extend(texts(event))
    for text in reversed(candidates):
        try:
            payload = artifact_json.loads_response_json(text)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get('schema') == 'uncle.artifact/v1' and payload.get('kind') == kind:
            return payload
    raise ValueError('stage did not return a canonical %s JSON artifact in its final runner output' % kind)


def legacy_raw_document(project, name, kind):
    """Recover an agent's valid JSON mistakenly written to the Markdown view.

    The normal contract is final-runner JSON -> canonical document -> rendered
    Markdown.  Some runners nevertheless let the agent use its Write tool and
    then return a prose status update.  Treat only an *unrendered*, schema-valid
    JSON object in the named view as a compatibility handoff.  A normal
    Markdown view is never parsed or made authoritative by this fallback.
    """
    view = Path(project) / '.uncle/docs' / name
    try:
        text = view.read_text(encoding='utf-8')
    except OSError as error:
        raise ValueError('stage did not return a canonical %s JSON artifact and %s is unavailable: %s'
                         % (kind, view, error)) from error
    artifact_json = module('artifact_json')
    try:
        payload = artifact_json.loads_response_json(text)
    except ValueError as error:
        raise ValueError('stage did not return a canonical %s JSON artifact; %s is a rendered Markdown view, not fallback JSON'
                         % (kind, view)) from error
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != kind:
        raise ValueError('stage did not return a canonical %s JSON artifact; %s has the wrong fallback schema'
                         % (kind, view))
    return payload


def publish(stage, log, project):
    if stage not in ARTIFACT:
        return False
    name, kind = ARTIFACT[stage]
    try:
        payload = response(log, kind)
    except ValueError:
        # Compatibility only.  Once published below, the view is immediately
        # overwritten with a deterministic rendering and cannot remain an
        # operational JSON input.
        payload = legacy_raw_document(project, name, kind)
    artifact_json = module('artifact_json')
    project = Path(project)
    if stage == 'requirements':
        rendered = artifact_json.render_requirements(payload)
    elif stage == 'updated-change-plan':
        rendered = artifact_json.render_change_plan(payload, require_dispositions=True)
    else:
        rendered = artifact_json.render_plan(payload, protected=stage == 'updated-plan')
    artifact_json.write(project, name, payload)
    path = project / '.uncle/docs' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + '\n', encoding='utf-8')
    return True


if __name__ == '__main__':
    try:
        if len(sys.argv) != 4:
            raise ValueError('usage: STAGE EVENT_LOG PROJECT')
        publish(*sys.argv[1:])
    except (OSError, ValueError) as error:
        print('canonical agent artifact: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
