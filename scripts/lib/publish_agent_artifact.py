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

try:
    from runner_events import texts
except ModuleNotFoundError:
    # Direct-file importlib callers need not put scripts/lib on sys.path.
    import importlib.util as _importlib_util
    _spec = _importlib_util.spec_from_file_location('runner_events', Path(__file__).with_name('runner_events.py'))
    _runner_events = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_runner_events)
    texts = _runner_events.texts


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


def preserve_updated_plan_fields(payload, project, stage):
    """Fill unchanged execution-contract fields after a compact patch delivery.

    The compiler owns dispositions and text edits.  Verification commands and
    protected test paths are driver-owned carry-forward data; asking a model
    to repeat them makes the response larger and turns an omitted legacy path
    list into an avoidable retry.  Explicit compiler edits still win.
    """
    if stage != 'updated-plan':
        return
    artifact_json = module('artifact_json')
    try:
        base = artifact_json.read(project, PATCH_BASE[stage])
    except (OSError, ValueError) as error:
        raise ValueError('updated plan: base execution contract is unavailable: %s' % error) from error
    commands = payload.get('verification_commands')
    if not isinstance(commands, str) or not commands.strip():
        payload['verification_commands'] = base.get('verification_commands') or ''
    paths = payload.get('protected_verification_paths')
    if isinstance(paths, str) and paths.strip():
        return
    from importlib.util import module_from_spec, spec_from_file_location
    source = Path(__file__).with_name('updated_plan_fast_path.py')
    spec = spec_from_file_location('updated_plan_fast_path', source)
    fast_path = module_from_spec(spec); spec.loader.exec_module(fast_path)
    # The compact compiler intentionally omits unchanged contract fields.  Do
    # not recover those fields from the old plan's prose, though: old prose
    # can mention a superseded filename beside the replacement (for example
    # ``tests/calc.test.js`` and ``tests/calc.test.mjs``).  The reconstructed
    # updated narrative is the current contract, and implementation-step
    # ownership tells us which of its candidate test/config files can actually
    # be created.  This keeps a driver-generated protected path from making an
    # otherwise valid updated plan fail the ownership gate before IMPLEMENT.
    paths = fast_path.derive_protected_paths(payload.get('narrative') or '', payload['verification_commands'])
    if not paths:
        try:
            paths = fast_path.protected_paths(base)
        except ValueError:
            paths = ''
    if paths:
        plan_model = module('plan_model').model_of(payload)
        step_groups = module('step_groups')
        owned = set()

        def collect(node):
            if isinstance(node, dict):
                values = node.get('owns')
                if isinstance(values, list):
                    owned.update(item for item in values if isinstance(item, str))
                for child in node.values():
                    collect(child)
            elif isinstance(node, list):
                for child in node:
                    collect(child)

        collect(plan_model)
        candidates = [line.strip() for line in paths.splitlines() if line.strip()]
        # Keep the broad legacy behavior if the plan has no explicit file
        # ownership at all.  Once it does, retain only paths covered by an
        # implementation step (including a declared directory or glob).
        matching = [path for path in candidates if any(step_groups.covers({token}, path) for token in owned)]
        if matching:
            paths = '\n'.join(matching)
    if not paths:
        raise ValueError('updated plan: no protected verification paths were supplied or derivable from the approved plan')
    payload['protected_verification_paths'] = paths


def publish(stage, log, project, delivery=None):
    if stage not in ARTIFACT:
        return False
    name, kind = ARTIFACT[stage]
    try:
        payload = delivered(delivery, kind) if delivery else response(log, kind)
    except ValueError as missing:
        if delivery:
            # Capture, don't regenerate: a complete packet the model already printed is
            # adopted through the same schema/kind check and the validators below, rather
            # than discarding it and paying for the whole document a second time.
            try:
                payload = response(log, kind)
            except (OSError, ValueError):
                raise missing
            print('Adopted the %s packet the runner printed instead of writing it.' % kind, file=sys.stderr)
        else:
            payload = None
    if payload is None:
        # Compatibility only.  Once published below, the view is immediately
        # overwritten with a deterministic rendering and cannot remain an
        # operational JSON input.
        payload = legacy_raw_document(project, name, kind)
    expand_patch(payload, project, stage)
    preserve_updated_plan_fields(payload, project, stage)
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
