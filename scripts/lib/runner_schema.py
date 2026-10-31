"""Codex's strict final-answer schema, mapped back to the workflow's artifact shape."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Constraints omitted from the wire are checked locally before delivery. This
# conservative subset also works with Codex providers that reject string bounds.
BOUNDS = {'minLength', 'maxLength', 'minItems', 'maxItems', 'minimum', 'maximum'}
KEYS = {'type', 'properties', 'required', 'additionalProperties', 'items', 'enum',
        'const', 'anyOf', 'description', 'title', '$schema', 'default'} | BOUNDS
KINDS = {'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'}


def enabled(stage=None):
    from self_hosted import config_stage
    from self_hosted_http import _config_values, stage_names
    stage = os.environ.get('UNCLE_STATUS_STAGE', '') if stage is None else stage
    config = _config_values()
    names = list(dict.fromkeys(stage_names(stage) + [config_stage(stage, config)]))
    for name in names + ['']:
        key = 'WORKFLOW_RUNNER_SCHEMA_ENFORCE' + ('_' + re.sub(r'[^A-Z0-9]', '_', name.upper()) if name else '')
        if os.environ.get(key, '').strip():
            return os.environ[key].strip().lower() not in ('0', 'off', 'false', 'no')
    for name in names + ['runner']:
        if name + '.schema-enforce' in config:
            return config[name + '.schema-enforce'].lower() not in ('0', 'off', 'false', 'no')
    return True


def strict_schema(schema, root=True):
    if not isinstance(schema, dict) or set(schema) - KEYS:
        raise ValueError('unsupported schema keywords')
    result = {k: copy.deepcopy(v) for k, v in schema.items() if k not in BOUNDS | {'$schema', 'default', 'const'}}
    if 'const' in schema:
        result['enum'] = [schema['const']]
    kind = schema.get('type')
    if kind is None and 'enum' in result:
        kinds = {('null' if v is None else 'boolean' if isinstance(v, bool) else
                  'string' if isinstance(v, str) else 'integer' if isinstance(v, int) else
                  'number' if isinstance(v, float) else 'unsupported') for v in result['enum']}
        if len(kinds) != 1 or 'unsupported' in kinds:
            raise ValueError('unsupported enum type')
        kind = result['type'] = kinds.pop()
    if 'anyOf' in schema:
        if root or kind is not None or set(schema) - {'anyOf', 'description', 'title'}:
            raise ValueError('unsupported union schema')
        result['anyOf'] = [strict_schema(s, False) for s in schema['anyOf']]
        return result
    kinds = kind if isinstance(kind, list) else [kind]
    if not kinds or any(k not in KINDS for k in kinds) or (root and kind != 'object'):
        raise ValueError('schema needs an explicit type and an object root')
    if 'object' in kinds:
        if schema.get('additionalProperties', False) is not False:
            raise ValueError('open-ended object schema')
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        if not isinstance(properties, dict) or not isinstance(required, list) or set(required) - set(properties):
            raise ValueError('invalid object schema')
        result['properties'] = {}
        for key, sub in properties.items():
            strict = strict_schema(sub, False)
            if key not in required:
                strict = {'anyOf': [strict, {'type': 'null'}]}
            result['properties'][key] = strict
        result['required'] = list(properties)
        result['additionalProperties'] = False
    if 'array' in kinds:
        result['items'] = strict_schema(schema.get('items'), False)
    return result


def validate(value, schema):
    """Check the supported source schema as well as the provider's reduced one."""
    if 'anyOf' in schema:
        for sub in schema['anyOf']:
            try:
                validate(value, sub)
                return
            except ValueError:
                pass
        raise ValueError('answer matches no schema alternative')
    kinds = schema.get('type', [])
    kinds = kinds if isinstance(kinds, list) else [kinds]
    matches = {'object': isinstance(value, dict), 'array': isinstance(value, list),
               'string': isinstance(value, str), 'integer': type(value) is int,
               'number': type(value) in (int, float), 'boolean': type(value) is bool, 'null': value is None}
    if kinds and not any(matches.get(k, False) for k in kinds):
        raise ValueError('answer has the wrong schema type')
    if 'const' in schema and json.dumps(value, sort_keys=True) != json.dumps(schema['const'], sort_keys=True):
        raise ValueError('answer differs from schema constant')
    if 'enum' in schema and not any(type(value) is type(v) and value == v for v in schema['enum']):
        raise ValueError('answer is outside schema enum')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - set(value):
            raise ValueError('answer is missing required fields')
        if schema.get('additionalProperties') is False and set(value) - set(props):
            raise ValueError('answer has unexpected fields')
        for key in value.keys() & props.keys():
            validate(value[key], props[key])
    if isinstance(value, list):
        for item in value:
            validate(item, schema['items'])
    for low, high, size in [('minLength', 'maxLength', len(value) if isinstance(value, str) else None),
                            ('minItems', 'maxItems', len(value) if isinstance(value, list) else None),
                            ('minimum', 'maximum', value if type(value) in (int, float) else None)]:
        if size is not None and (size < schema.get(low, size) or size > schema.get(high, size)):
            raise ValueError('answer is outside schema bounds')


def restore(value, schema):
    if 'anyOf' in schema:
        for sub in schema['anyOf']:
            try:
                validate(value, strict_schema(sub, False))
                candidate = restore(value, sub)
                validate(candidate, sub)
                return candidate
            except ValueError:
                pass
        raise ValueError('answer matches no schema alternative')
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            sub = schema.get('properties', {}).get(key)
            if sub is None:
                result[key] = item
                continue
            if item is None and key not in schema.get('required', []):
                try:
                    validate(None, sub)
                except ValueError:
                    continue  # Only nulls introduced to represent absence disappear.
            result[key] = restore(item, sub)
        return result
    if isinstance(value, list):
        return [restore(item, schema['items']) for item in value]
    return value


def note(reason):
    print('Codex schema enforcement unavailable; using file delivery: ' + ' '.join(str(reason).split()), file=sys.stderr)


def prepare(path=None, stage=None):
    path = path or os.environ.get('UNCLE_OUTPUT_SCHEMA_FILE')
    if not path or not enabled(stage):
        return None
    try:
        schema = json.loads(Path(path).read_text(encoding='utf-8'))
        return schema, strict_schema(schema)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        note(exc)
        return None


def supported():
    try:
        done = subprocess.run([os.environ.get('WORKFLOW_CODEX_CMD', 'codex'), 'exec', '--help'],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        return done.returncode == 0 and '--output-schema' in done.stdout and '--output-last-message' in done.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def deliver(text, schema, destination=None):
    value = json.loads(text)
    json.dumps(value, allow_nan=False)
    validate(value, strict_schema(schema))
    value = restore(value, schema)
    validate(value, schema)
    if destination:
        Path(destination).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return value


def main(args):
    if args[0] == 'enabled':
        return 0 if enabled(args[1]) else 1
    if args[0] == 'prepare':
        prepared = prepare()
        if prepared is None:
            return 1
        if not supported():
            note('CLI does not advertise --output-schema and --output-last-message')
            return 1
        Path(args[1]).write_text(json.dumps(prepared[1]), encoding='utf-8')
        return 0
    if args[0] == 'deliver':
        try:
            schema = json.loads(Path(os.environ['UNCLE_OUTPUT_SCHEMA_FILE']).read_text(encoding='utf-8'))
            value = deliver(Path(args[1]).read_text(encoding='utf-8'), schema, os.environ.get('UNCLE_STRUCTURED_OUTPUT_PATH'))
            print(json.dumps(value))
            return 0
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            print('Codex structured output rejected: ' + str(exc), file=sys.stderr)
            return 1
    raise ValueError('unknown runner schema command')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
