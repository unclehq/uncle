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


def publish(stage, log, project):
    if stage not in ARTIFACT:
        return False
    name, kind = ARTIFACT[stage]
    payload = response(log, kind)
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
