#!/usr/bin/env python3
"""Publish the three canonical artifacts produced by combined change planning.

The combined baseline/specification/plan pass used to write three Markdown
files and then re-parse them. That made human approval views an operational
handoff. Its one file-backed JSON delivery instead carries all three packets;
this boundary validates each packet and renders the views only after all three
have been accepted.
"""
import importlib.util
import json
import sys
from pathlib import Path


def artifact_json():
    spec = importlib.util.spec_from_file_location('artifact_json', Path(__file__).with_name('artifact_json.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ARTIFACTS = (
    ('baseline_report', 'BASELINE_REPORT.md', 'baseline-report', 'render_baseline_report'),
    ('change_spec', 'CHANGE_SPEC.md', 'change-spec', 'render_change_spec'),
    ('change_plan', 'CHANGE_PLAN.md', 'change-plan', 'render_change_plan'),
)


def publish(project, delivery):
    try:
        payload = json.loads(Path(delivery).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('canonical change-planning bundle is missing or invalid at %s: %s' % (delivery, error)) from error
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' \
            or payload.get('kind') != 'change-planning-bundle':
        raise ValueError('canonical change-planning bundle has the wrong schema at ' + delivery)
    module = artifact_json()
    prepared = []
    for key, name, kind, renderer_name in ARTIFACTS:
        item = payload.get(key)
        if not isinstance(item, dict) or item.get('schema') != 'uncle.artifact/v1':
            raise ValueError('change-planning bundle is missing a canonical %s packet' % key)
        if item.get('kind') != kind:
            raise ValueError('change-planning bundle has wrong kind for %s: expected %s' % (key, kind))
        try:
            rendered = getattr(module, renderer_name)(item)
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError('invalid %s packet: %s' % (key, error)) from error
        prepared.append((name, item, rendered))
    # Do not publish a partial bundle: validation of every packet precedes all
    # writes, so a retry has one precise error rather than mixed old/new state.
    root = Path(project)
    for name, item, rendered in prepared:
        module.write(root, name, item)
        view = root / '.uncle/docs' / name
        view.parent.mkdir(parents=True, exist_ok=True)
        view.write_text(rendered + '\n', encoding='utf-8')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('usage: PROJECT DELIVERY_JSON')
        publish(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as error:
        print('canonical change-planning bundle: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
