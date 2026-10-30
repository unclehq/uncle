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
    if not isinstance(modules, list) or not modules:
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
    return '\n'.join(lines)


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
