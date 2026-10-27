#!/usr/bin/env python3
"""JSON Schemas for the packets the plan-stage workers deliver, shared by every runner.

A worker that has to deliver structured text must not be trusted to format it.  These schemas are enforced
where the runner can enforce them:

- hosted Claude: `claude -p --json-schema` makes the model answer through a validated StructuredOutput call
  (run_claude reads `structured_output`, see structured_output.py);
- self-hosted models: the adapter sends the schema of the `"kind"` named in the prompt as a grammar
  (self_hosted.REVIEWER_SCHEMAS registers the static forms below).

A per-call schema is stricter than the static one: it lists the headings a worker may name, so a section
outside its lane, or an edit aimed at a section the plan does not have, cannot be written at all.  Only
keywords every server accepts are used (no `pattern`); ID shapes are checked by the driver, which validates
what it receives for runners with no schema support.

    worker_schemas.py section NAME OUTPUT       project-plan section worker
    worker_schemas.py edit PLAN.json OUTPUT [owner]   updated-plan edit writer
    worker_schemas.py resolve PLAN.json OUTPUT        updated-plan resolver
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENVELOPE = 'uncle.artifact/v1'
SECTION_KIND = 'project-plan-section-worker-packet'
EDIT_KIND = 'updated-plan-edit-worker-packet'
RESOLUTION_KIND = 'updated-plan-resolution-worker-packet'
BODY_MAX = 30000
EDIT_MAX = 12000
DISPOSITIONS = ('Accepted', 'Partially accepted', 'Rejected', 'Deferred')


def _text(maximum, minimum=1):
    return {'type': 'string', 'minLength': minimum, 'maxLength': maximum}


def _object(properties, required, ):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def _choice(values, maximum=300):
    return {'type': 'string', 'enum': list(values)} if values else _text(maximum)


def envelope(kind, properties, required):
    properties = dict({'schema': {'const': ENVELOPE}, 'kind': {'const': kind}}, **properties)
    return _object(properties, ['schema', 'kind'] + list(required))


def section_packet(headings=None, trace_kinds=''):
    """`headings`: the only headings this worker may write (None: any `## ` heading).
    `trace_kinds`: the traceability letters it reports, e.g. 'BM'; empty when it reports none."""
    heading = {'type': 'string', 'enum': list(headings)} if headings else _text(300)
    properties = {'sections': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                               'items': _object({'heading': heading, 'body': _text(BODY_MAX)}, ('heading', 'body'))}}
    if trace_kinds or headings is None:
        kinds = list(trace_kinds) if trace_kinds else ['B', 'I', 'C', 'T', 'M']
        properties['trace'] = {'type': 'array', 'maxItems': 300, 'items': _object({
            'kind': {'type': 'string', 'enum': kinds},
            'requirement': _text(40),
            'ids': {'type': 'array', 'minItems': 1, 'maxItems': 60, 'items': _text(40)}},
            ('kind', 'requirement', 'ids'))}
    required = ['sections'] + (['trace'] if trace_kinds and headings else [])
    return envelope(SECTION_KIND, properties, required)


def _patch(headings=None):
    heading = _choice(headings)
    return _object({
        'replace_text': {'type': 'array', 'maxItems': 80, 'items': _object(
            {'heading': heading, 'old': _text(EDIT_MAX), 'new': _text(EDIT_MAX, 0), 'all': {'type': 'boolean'}},
            ('heading', 'old', 'new'))},
        'edit_sections': {'type': 'array', 'maxItems': 40, 'items': _object(
            {'heading': heading, 'content': _text(EDIT_MAX, 0)}, ('heading', 'content'))},
        'insert_sections': {'type': 'array', 'maxItems': 20, 'items': _object(
            {'content': _text(EDIT_MAX), 'after': _choice(headings), 'before': _choice(headings),
             'position': {'type': 'string', 'enum': ['start', 'end']}}, ('content',))},
    }, ())


def _commands():
    return {'type': 'array', 'maxItems': 40,
            'items': _object({'old': _text(1000), 'new': _text(1000, 0)}, ('old', 'new'))}


def edit_packet(headings=None, owner=False):
    properties = {
        'dispositions': {'type': 'array', 'maxItems': 40, 'items': _object({
            'finding': _text(80), 'disposition': {'type': 'string', 'enum': list(DISPOSITIONS)},
            'reason': _text(300), 'plan_change': _text(300)}, ('finding', 'disposition', 'reason', 'plan_change'))},
        'patch': _patch(headings),
        'commands_replace': _commands(),
    }
    if owner:
        properties['protected_verification_paths'] = _text(4000)
    return envelope(EDIT_KIND, properties, ['dispositions', 'patch'] + (['protected_verification_paths'] if owner else []))


def resolution_packet(headings=None):
    return envelope(RESOLUTION_KIND, {'resolutions': {'type': 'array', 'minItems': 1, 'maxItems': 40, 'items': _object({
        'group': _text(40), 'patch': _patch(headings), 'commands_replace': _commands()}, ('group',))}},
        ['resolutions'])


# What a self-hosted adapter enforces when it knows only the kind named in the prompt.
STATIC = {SECTION_KIND: section_packet(), EDIT_KIND: edit_packet(), RESOLUTION_KIND: resolution_packet()}


def plan_headings(plan_json):
    from plan_patch import split_sections
    plan = json.loads(Path(plan_json).read_text(encoding='utf-8'))
    return [section['heading'] for section in split_sections(plan.get('narrative') or '')[1]]


def main(argv):
    try:
        if len(argv) == 3 and argv[0] == 'section':
            import project_plan_sections as sections
            schema = section_packet(sections.expected_headings(argv[1]), sections.trace_letters(argv[1]))
        elif len(argv) in (3, 4) and argv[0] == 'edit':
            schema = edit_packet(plan_headings(argv[1]), owner=len(argv) == 4)
        elif len(argv) == 3 and argv[0] == 'resolve':
            schema = resolution_packet(plan_headings(argv[1]))
        else:
            raise SystemExit(__doc__)
        Path(argv[2]).write_text(json.dumps(schema, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError) as error:
        print('worker schemas: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
