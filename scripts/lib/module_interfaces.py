#!/usr/bin/env python3
"""A shared, binding contract for the exports each plan file must have.

Parallel implementation steps are written in isolation -- a worker writing
src/keymap.js never sees what src/engine.js's worker writes, and cannot read
it (that would multiply the plan's token cost by every worker, and files
other steps own may not exist yet when this one runs). Each worker has
guessed its own shape for the files it imports from, and the guesses
disagree: an object vs. a function initialState, an `op` vs. `operator`
action field, a `keyToAction(event)` vs. `keyToAction(key)` signature. The
merged result then fails to build or test, and the actual fix a human
developer would reach for first -- write down the exact interface everyone
implements against, before anyone writes code against it -- was missing.

This module validates and renders that one shared contract, derived once
from the approved plan before the parallel fan-out starts, so every worker's
prompt carries the identical, exact text instead of each guessing alone.

usage:
  module_interfaces.py --validate-json PAYLOAD.json
  module_interfaces.py --render-section PAYLOAD.json
"""
import json
import sys


def validate(payload):
    if not isinstance(payload, dict) or payload.get('schema') != 'uncle.artifact/v1' \
            or payload.get('kind') != 'module-interfaces':
        raise ValueError('Invalid module-interfaces JSON: wrong schema/kind')
    modules = payload.get('modules')
    contract = payload.get('ui_contract')
    if contract is not None:
        validate_ui_contract(contract)
    # A plan whose only shared surface is the page (no JS export crosses a file boundary) has an empty module list.
    if not isinstance(modules, list) or (not modules and not contract):
        raise ValueError('module-interfaces: "modules" must be a non-empty list')
    seen = set()
    for entry in modules:
        if not isinstance(entry, dict):
            raise ValueError('module-interfaces: each module entry must be an object')
        file = entry.get('file')
        if not isinstance(file, str) or not file.strip():
            raise ValueError('module-interfaces: a module entry is missing "file"')
        if file in seen:
            raise ValueError('module-interfaces: duplicate file entry: ' + file)
        seen.add(file)
        exports = entry.get('exports')
        if not isinstance(exports, list) or not exports:
            raise ValueError('module-interfaces: %s has no "exports"' % file)
        export_names = set()
        for item in exports:
            if not isinstance(item, dict):
                raise ValueError('module-interfaces: %s has a non-object export' % file)
            name = item.get('name')
            kind = item.get('kind')
            signature = item.get('signature')
            if not all(isinstance(v, str) and v.strip() for v in (name, kind, signature)):
                raise ValueError(
                    'module-interfaces: %s export %r needs non-empty name, kind, and signature'
                    % (file, name))
            if name in export_names:
                raise ValueError('module-interfaces: %s has a duplicate export: %s' % (file, name))
            export_names.add(name)
    return payload


UI_KINDS = ('class', 'data-attribute', 'test-id', 'id', 'aria', 'key')


def validate_ui_contract(contract):
    """Names the page's files share by string: set in a component, styled in a stylesheet, selected in a test."""
    if not isinstance(contract, list):
        raise ValueError('module-interfaces: "ui_contract" must be a list')
    seen = set()
    for item in contract:
        if not isinstance(item, dict):
            raise ValueError('module-interfaces: each ui_contract entry must be an object')
        kind, name = item.get('kind'), item.get('name')
        if kind not in UI_KINDS:
            raise ValueError('module-interfaces: ui_contract kind must be one of %s, not %r' % (', '.join(UI_KINDS), kind))
        if not isinstance(name, str) or not name.strip():
            raise ValueError('module-interfaces: a ui_contract entry is missing "name"')
        used_by = item.get('used_by')
        if not isinstance(used_by, list) or not used_by or not all(isinstance(f, str) and f.strip() for f in used_by):
            raise ValueError('module-interfaces: ui_contract %s %r needs a non-empty "used_by" list of files' % (kind, name))
        if (kind, name) in seen:
            raise ValueError('module-interfaces: duplicate ui_contract entry: %s %s' % (kind, name))
        seen.add((kind, name))


def render_ui_contract(contract):
    lines = [
        '',
        '## Fixed UI contract (binding)',
        '',
        'These names are shared by string between files that different steps write: the component sets them, '
        'the stylesheet styles them, the tests select them. Nothing checks them until the merged page is run, '
        'and a mismatch there reads as a broken screen, not a bad name. Use exactly these names and no others '
        'for the things listed: a component applies every one it is listed for, a stylesheet defines a rule '
        'for every `class` listed (and for no class this contract does not list or the component does not set), '
        'and a test selects by these names only. Do not rename one, and do not invent a second name for the same element.',
        '',
    ]
    for item in contract:
        note = ' -- %s' % item['note'] if isinstance(item.get('note'), str) and item['note'].strip() else ''
        element = ' on %s' % item['element'] if isinstance(item.get('element'), str) and item['element'].strip() else ''
        lines.append('- %s `%s`%s; used by %s%s' % (item['kind'], item['name'], element,
                                                  ', '.join('`%s`' % f for f in item['used_by']), note))
    lines.append('')
    return '\n'.join(lines)


def render_section(payload):
    """The exact text embedded, unchanged, into every parallel worker's prompt."""
    lines = [
        '',
        '## Fixed module interfaces (binding)',
        '',
        'Every file below is implemented or imported by more than one isolated step. '
        'These are the exact, final exports -- implement them from your owned files exactly '
        'as given, and when you import from a file a different step owns, use exactly this '
        'name, kind, and call signature. Do not invent a different shape, field name, or '
        'calling convention for anything listed here, even if it looks more natural to you.',
    ]
    for module in payload['modules']:
        lines.append('')
        lines.append('### `%s`' % module['file'])
        for item in module['exports']:
            lines.append('- `%s` (%s): %s' % (item['name'], item['kind'], item['signature']))
    lines.append('')
    text = '\n'.join(lines) if payload['modules'] else ''
    if payload.get('ui_contract'):
        text += render_ui_contract(payload['ui_contract'])
    return text


def main(argv):
    if len(argv) != 2 or argv[0] not in ('--validate-json', '--render-section'):
        print(__doc__, file=sys.stderr)
        return 2
    action, path = argv
    try:
        with open(path, encoding='utf-8') as stream:
            payload = json.load(stream)
        validate(payload)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if action == '--render-section':
        print(render_section(payload))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
