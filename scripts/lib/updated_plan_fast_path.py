#!/usr/bin/env python3
"""Produce an updated plan locally only when there is nothing to resolve."""
import argparse
import json
from pathlib import Path


def read(path, kind):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema') != 'uncle.artifact/v1' or data.get('kind') != kind:
        raise ValueError('%s is not %s JSON' % (path, kind))
    return data


def protected_paths(plan):
    """Keep the updated-plan execution contract without another model call.

    Initial plans predate the dedicated field but carry the exact same list in
    the driver-owned frozen-path comment at the top of their command block.
    A clean review must preserve that contract deterministically.
    """
    paths = plan.get('protected_verification_paths')
    if isinstance(paths, str) and paths.strip():
        return paths
    commands = plan.get('verification_commands', '')
    for line in commands.splitlines():
        marker = '# Frozen verification paths:'
        if line.strip().lower().startswith(marker.lower()):
            paths = line.split(':', 1)[1].strip()
            if paths:
                return paths
    raise ValueError('project plan has no protected verification paths to preserve')


def render_view(payload, view, change=False):
    """Render the non-authoritative approval view from the JSON we just wrote."""
    import importlib.util
    artifact = Path(__file__).with_name('artifact_json.py')
    spec = importlib.util.spec_from_file_location('artifact_json', artifact)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rendered = (module.render_change_plan(payload, require_dispositions=True)
                if change else module.render_plan(payload, protected=True))
    Path(view).write_text(rendered + '\n', encoding='utf-8')


def build(project_plan, review, output, view=None):
    plan = read(project_plan, 'plan')
    assessment = read(review, 'adversarial-review')
    if assessment.get('findings'):
        return False
    result = dict(plan, dispositions=[], protected_verification_paths=protected_paths(plan))
    narrative = result.get('narrative', '')
    if narrative.startswith('# Project plan'):
        result['narrative'] = '# Updated project plan' + narrative[len('# Project plan'):]
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if view:
        render_view(result, view)
    return True


def build_change(change_plan, review, output, view=None):
    """Carry a clean change plan through its post-review revision locally.

    CHANGE_PLAN.md is rendered from this JSON by the normal ingest step.  The
    explicit empty dispositions list is meaningful: it records that the
    adversarial review had nothing to disposition, rather than omitting the
    post-review contract altogether.
    """
    plan = read(change_plan, 'change-plan')
    assessment = read(review, 'adversarial-review')
    if assessment.get('findings'):
        return False
    result = dict(plan, dispositions=[])
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if view:
        render_view(result, view, change=True)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--change', action='store_true',
                        help='copy a change-plan instead of an application plan')
    parser.add_argument('--render', metavar='MARKDOWN',
                        help='render this human approval view from the canonical JSON')
    parser.add_argument('project_plan'); parser.add_argument('review'); parser.add_argument('output')
    args = parser.parse_args()
    try:
        handler = build_change if args.change else build
        raise SystemExit(0 if handler(args.project_plan, args.review, args.output, args.render) else 1)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print('updated-plan fast path: ' + str(error))
        raise SystemExit(1)
