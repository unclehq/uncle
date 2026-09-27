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
    'change-plan': ('CHANGE_PLAN.md', 'change-plan'),
    'updated-plan': ('UPDATED_PROJECT_PLAN.md', 'plan'),
    'updated-change-plan': ('CHANGE_PLAN.md', 'change-plan'),
}

# The base document each synthesis stage's `patch` (see
# updated_plan_synthesis_prompt.py) applies against. 'updated-change-plan'
# revises CHANGE_PLAN.md in place, so its base and its own target are the
# same name -- read here, before this publish() call's write() overwrites it.
PATCH_BASE = {
    'updated-plan': 'PROJECT_PLAN.md',
    'updated-change-plan': 'CHANGE_PLAN.md',
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


def delivered(path, kind):
    """Read the sole authoritative agent handoff, never conversational text."""
    artifact_json = module('artifact_json')
    try:
        payload = artifact_json.loads_response_json(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('canonical %s JSON delivery is missing or invalid at %s: %s' % (kind, path, error)) from error
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' or payload.get('kind') != kind:
        raise ValueError('canonical %s JSON delivery has the wrong schema at %s' % (kind, path))
    return payload


def expand_patch(payload, project, stage):
    """Reconstruct `payload['narrative']` from `payload['patch']` in place.

    updated_plan_synthesis_prompt.py asks the synthesis stage for a small
    patch -- only the sections a review actually requires changing -- instead
    of the plan's whole text, since reproducing every unaffected section made
    a self-hosted model's output (and time) proportional to the plan's size
    rather than to the review's. `patch` takes precedence over any stray
    `narrative` the model included alongside it: the contract asked for one
    or the other, and a patch is what this stage's prompt actually requests.
    A model that ignores the new instructions and returns `narrative`
    directly, with no `patch` key, is unaffected -- used exactly as before.
    """
    if 'patch' not in payload or stage not in PATCH_BASE:
        return
    artifact_json = module('artifact_json')
    plan_patch = module('plan_patch')
    base_name = PATCH_BASE[stage]
    try:
        base = artifact_json.read(project, base_name)
    except (OSError, ValueError) as error:
        raise ValueError('patch: base document %s is missing or invalid: %s' % (base_name, error)) from error
    payload['narrative'] = plan_patch.apply_patch(base.get('narrative') or '', payload['patch'])


def publish(stage, log, project, delivery=None):
    if stage not in ARTIFACT:
        return False
    name, kind = ARTIFACT[stage]
    try:
        payload = delivered(delivery, kind) if delivery else response(log, kind)
    except ValueError:
        if delivery:
            raise
        # Compatibility only.  Once published below, the view is immediately
        # overwritten with a deterministic rendering and cannot remain an
        # operational JSON input.
        payload = legacy_raw_document(project, name, kind)
    expand_patch(payload, project, stage)
    artifact_json = module('artifact_json')
    project = Path(project)
    if stage == 'requirements':
        rendered = artifact_json.render_requirements(payload)
    elif stage in ('change-plan', 'updated-change-plan'):
        # Initial planning precedes adversarial review, so dispositions are
        # required only for the revised plan.  Requiring them here made a
        # perfectly valid first change plan impossible to publish.
        rendered = artifact_json.render_change_plan(payload, require_dispositions=stage == 'updated-change-plan')
    else:
        rendered = artifact_json.render_plan(payload, protected=stage == 'updated-plan')
    artifact_json.write(project, name, payload)
    path = project / '.uncle/docs' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + '\n', encoding='utf-8')
    return True


if __name__ == '__main__':
    try:
        if len(sys.argv) not in (4, 5):
            raise ValueError('usage: STAGE EVENT_LOG PROJECT [DELIVERY_JSON]')
        publish(*sys.argv[1:])
    except (OSError, ValueError) as error:
        print('canonical agent artifact: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
