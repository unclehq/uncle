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
    worker_schemas.py section-model NAME OUTPUT   project-plan section worker, writing typed blocks (NAME outline: the outline)
    worker_schemas.py edit PLAN.json OUTPUT [owner]   updated-plan edit writer
    worker_schemas.py resolve PLAN.json OUTPUT        updated-plan resolver
    worker_schemas.py edit-ops PLAN.json OUTPUT [owner] [--scope IDS.json]   the same writer, editing the plan model by id
    worker_schemas.py resolve-ops PLAN.json OUTPUT [--scope IDS.json]        the same resolver, for ops
    worker_schemas.py requirements OUTPUT                     the requirements interpretation
    worker_schemas.py synthesis KIND protected|plain OUTPUT   the single-call updated plan (KIND plan or change-plan)
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENVELOPE = 'uncle.artifact/v1'
SECTION_KIND = 'project-plan-section-worker-packet'
EDIT_KIND = 'updated-plan-edit-worker-packet'
RESOLUTION_KIND = 'updated-plan-resolution-worker-packet'
SECTION_MODEL_KIND = 'project-plan-section-model-packet'    # a section worker's sections as typed blocks, not Markdown
OUTLINE_KIND = 'project-plan-outline-packet'                 # the outline every section worker is bound to, as data
EDIT_OPS_KIND = 'updated-plan-edit-ops-packet'              # the same writers, editing the plan model by id
RESOLUTION_OPS_KIND = 'updated-plan-resolution-ops-packet'
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
        properties['trace'] = {'type': 'array', 'minItems': 1 if (trace_kinds and headings) else 0, 'maxItems': 300, 'items': _object({
            'kind': {'type': 'string', 'enum': kinds},
            'requirement': _text(40),
            'ids': {'type': 'array', 'minItems': 1, 'maxItems': 60, 'items': _text(40)}},
            ('kind', 'requirement', 'ids'))}
    required = ['sections'] + (['trace'] if trace_kinds and headings else [])
    return envelope(SECTION_KIND, properties, required)


def _flat_block(row_kinds=None, steps=True):
    """One block a section worker writes: every value a string (a list field is one comma-separated string).
    `row_kinds` limits the table kinds it may use (None: all; empty: no typed table); `steps` allows a steps block."""
    from plan_model import BLOCK_KINDS, FIELD_NAMES, ROW_KINDS
    kinds = [k for k in BLOCK_KINDS if (k != 'rows' or row_kinds is None or row_kinds) and (k != 'steps' or steps)]
    row_kinds = list(ROW_KINDS) if row_kinds is None else [k for k in row_kinds if k in ROW_KINDS] or list(ROW_KINDS)
    row = _strings(['id'] + FIELD_NAMES, 4000)
    step = _strings(['number', 'title', 'text', 'owns', 'depends_on'], 4000)
    return _object({
        'kind': {'type': 'string', 'enum': kinds}, 'text': _text(BODY_MAX, 0), 'level': _text(2, 0),
        'lang': _text(30, 0), 'ordered': {'type': 'boolean'},
        'items': {'type': 'array', 'maxItems': 80, 'items': _text(4000)},
        'row_kind': {'type': 'string', 'enum': row_kinds},
        'rows': {'type': 'array', 'maxItems': 150, 'items': row},
        'columns': {'type': 'array', 'maxItems': 12, 'items': _text(200)},
        'cells': {'type': 'array', 'maxItems': 150, 'items': {'type': 'array', 'maxItems': 12, 'items': _text(4000, 0)}},
        'steps': {'type': 'array', 'maxItems': 40, 'items': step},
    }, ('kind',))


def section_model_packet(headings=None, trace_kinds='', row_kinds=None, steps=True):
    """`section_packet`, with each section's body written as typed blocks.  `headings` are titles without the `##`."""
    heading = {'type': 'string', 'enum': list(headings)} if headings else _text(300)
    properties = {'sections': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                               'items': _object({'heading': heading,
                                                 'blocks': {'type': 'array', 'minItems': 1, 'maxItems': 60, 'items': _flat_block(row_kinds, steps)}},
                                                ('heading', 'blocks'))}}
    if trace_kinds or headings is None:
        kinds = list(trace_kinds) if trace_kinds else ['B', 'I', 'C', 'T', 'M']
        properties['trace'] = {'type': 'array', 'minItems': 1 if (trace_kinds and headings) else 0, 'maxItems': 300, 'items': _object({
            'kind': {'type': 'string', 'enum': kinds}, 'requirement': _text(40),
            'ids': {'type': 'array', 'minItems': 1, 'maxItems': 60, 'items': _text(40)}}, ('kind', 'requirement', 'ids'))}
    return envelope(SECTION_MODEL_KIND, properties, ['sections'] + (['trace'] if trace_kinds and headings else []))


def outline_packet():
    """The outline: the one thing every section worker reads, so it is data and not a Markdown file to parse."""
    def rows(fields, maximum=80):
        return {'type': 'array', 'minItems': 0, 'maxItems': maximum, 'items': _strings(fields, 1000)}
    required = _object({
        'stack': _text(500),
        'components': {'type': 'array', 'minItems': 1, 'maxItems': 80, 'items': _object({
            'id': _text(20), 'name': _text(200), 'responsibility': _text(500), 'files': _text(1000, 0)},
            ('id', 'name', 'files'))},
        'steps': {'type': 'array', 'minItems': 1, 'maxItems': 60, 'items': _object({
            'number': _text(4), 'title': _text(300), 'owns': _text(2000), 'depends_on': _text(100, 0)},
            ('number', 'title', 'owns', 'depends_on'))},
        'decisions': {'type': 'array', 'maxItems': 80, 'items': _object({'id': _text(20), 'text': _text(500)}, ('id', 'text'))},
        'restrictions': {'type': 'array', 'maxItems': 80, 'items': _object({
            'id': _text(20), 'text': _text(500),
            'source_kind': {'type': 'string', 'enum': ['USER', 'REPOSITORY', 'PLATFORM', 'DESIGN']}},
            ('id', 'text', 'source_kind'))},
        'tests': {'type': 'array', 'maxItems': 40, 'items': _object({
            'runner': _text(200), 'files': _text(2000, 0)}, ('runner', 'files'))},
        'requirement_map': {'type': 'array', 'minItems': 1, 'maxItems': 300, 'items': _object({
            'requirement': _text(40), 'components': _text(500)}, ('requirement', 'components'))},
    }, ('stack', 'components', 'steps', 'requirement_map'))      # decisions, restrictions and tests are written by their own workers
    return envelope(OUTLINE_KIND, required['properties'], required['required'])


def _patch(headings=None):
    heading = _choice(headings)
    return _object({
        'replace_item': {'type': 'array', 'maxItems': 80, 'items': _object(
            {'heading': heading, 'item': _text(40), 'new': _text(EDIT_MAX, 0)}, ('heading', 'item', 'new'))},
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
    owner = owner and os.environ.get('UNCLE_PLAN_KIND') != 'change-plan'   # a change plan has no protected paths
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


def _strings(names, maximum=8000):
    return _object({name: _text(maximum, 0) for name in names}, ())


def _op(ids=None):
    """One flat edit of the plan model (docs/plan-model.md): every value a string, so any grammar accepts it.
    `ids`, when given, are the only ids the edit may name."""
    from plan_model import FIELD_NAMES, OP_NAMES
    pick = (lambda extra=(): {'type': 'string', 'enum': sorted(ids) + list(extra)}) if ids else (lambda extra=(): _text(120, 0))
    step = ['title', 'text', 'owns', 'depends_on']
    block = _object({'kind': {'type': 'string', 'enum': ['prose', 'heading', 'code', 'list']},
                     'text': _text(EDIT_MAX, 0), 'level': _text(2, 0), 'lang': _text(30, 0),
                     'items': {'type': 'array', 'maxItems': 60, 'items': _text(2000)}}, ('kind',))
    generic = _object({
        'op': {'type': 'string', 'enum': [name for name in OP_NAMES if name != 'insert_step']},
        'id': pick(), 'target': pick(), 'after': pick(['']),
        'fields': _strings(FIELD_NAMES + step), 'text': _text(EDIT_MAX, 0),
        'new': _strings(['id'] + FIELD_NAMES + step, EDIT_MAX),
        'block': block, 'heading': _text(300, 0), 'blocks': {'type': 'array', 'maxItems': 20, 'items': block},
    }, ('op',))
    return {'anyOf': [generic, _new_step(ids)]}


def _new_step(ids=None):
    steps = [key for key in ids if key.startswith('step-')] if ids is not None else None
    anchor = _choice(steps) if steps else _text(120)
    strings = {'type': 'array', 'maxItems': 150, 'items': _text(4000)}
    return _object({'op': {'const': 'insert_step'}, 'after': _choice(steps + ['end']) if steps else _text(120),
                    'before': anchor,
                    'new': _object({'title': _text(EDIT_MAX, 0), 'text': _text(EDIT_MAX, 0), 'owns': strings,
                                    'depends_on': strings}, ('title', 'text', 'owns', 'depends_on'))}, ('op', 'new'))


def scoped_ids(model, targets):
    """Explicit containers include their contents; ancestors supply insertion targets only."""
    from plan_model import index, parent_of
    where, parents = index(model), parent_of(model)
    selected = set(targets) & set(where)
    for key in where:
        parent = parents.get(key)
        while parent:
            if parent in targets:
                selected.add(key)
                break
            parent = parents.get(parent)
    for key in list(selected):
        parent = parents.get(key)
        while parent:
            selected.add(parent)
            parent = parents.get(parent)
    return sorted(selected)


def model_op(model, ids=None):
    """Closed operation variants, grouped by actual row kind instead of by individual id."""
    from plan_model import ROW_KINDS, index, steps_of
    allowed = set(index(model))
    if ids is not None:
        allowed.intersection_update(ids)
    variants, rows, texts, steps = [], {}, [], []
    step_blocks = False
    strings = {'type': 'array', 'maxItems': 150, 'items': _text(4000)}
    references = _choice([step['id'] for step in steps_of(model)] + ['new:%d' % n for n in range(1, 121)])
    step_fields = {'title': _text(EDIT_MAX, 0), 'text': _text(EDIT_MAX, 0), 'owns': strings,
                   'depends_on': {'type': 'array', 'maxItems': 150,
                                  'items': {'anyOf': [{'type': 'integer', 'minimum': 0}, references]}}}

    def fields(kind, new=False):
        properties = {name: strings if is_list else _text(EDIT_MAX, 0)
                      for name, _, is_list, _ in ROW_KINDS[kind] if new or name != 'id'}
        if new:
            properties['id'] = _text(120)
        return _object(properties, ('id',) if new else ())

    def add(op, properties, required):
        variants.append(_object(dict(op={'const': op}, **properties), ['op'] + list(required)))

    def pick(values):
        return {'type': 'string', 'enum': sorted(values)}

    block = {'anyOf': [
        _object({'kind': {'const': 'prose'}, 'text': _text(EDIT_MAX, 0)}, ('kind', 'text')),
        _object({'kind': {'const': 'heading'}, 'text': _text(EDIT_MAX, 0),
                 'level': {'type': 'string', 'enum': ['3', '4', '5', '6']}}, ('kind', 'text')),
        _object({'kind': {'const': 'code'}, 'text': _text(EDIT_MAX, 0), 'lang': _text(30, 0)}, ('kind', 'text')),
        _object({'kind': {'const': 'list'}, 'items': strings}, ('kind', 'items'))]}
    sections = []
    for section in model['sections']:
        if section['id'] in allowed:
            sections.append(section['id'])
            add('insert_block', {'target': pick([section['id']]),
                                'after': pick([''] + [b['id'] for b in section['blocks'] if b['id'] in allowed]),
                                'block': block}, ('target', 'block'))
        for node in section['blocks']:
            members = node.get('rows') or node.get('items') or []
            member_ids = [r['id'] for r in members if r['id'] in allowed]
            kind = node['kind']
            if kind == 'rows':
                rows.setdefault(node['row_kind'], []).extend(member_ids)
            elif kind == 'steps':
                steps.extend(member_ids)
                step_blocks = step_blocks or node['id'] in allowed
            elif kind == 'list':
                texts.extend(member_ids)
            if node['id'] not in allowed:
                continue
            if kind in ('prose', 'heading', 'code'):
                texts.append(node['id'])
            if kind in ('rows', 'list'):
                new = (fields(node['row_kind'], new=True) if kind == 'rows' else
                       _object({'id': _text(120), 'text': _text(EDIT_MAX, 0)}, ('text',)))
                add('insert_row' if kind == 'rows' else 'insert_item',
                    {'target': pick([node['id']]), 'after': pick([''] + member_ids), 'new': new}, ('target', 'new'))
    for kind, keys in rows.items():
        if keys:
            add('set_fields', {'id': pick(keys), 'fields': fields(kind)}, ('id', 'fields'))
    if steps:
        add('set_step', {'id': pick(steps), 'fields': _object(step_fields, ())}, ('id', 'fields'))
    if steps or step_blocks:
        variants.append(_new_step(steps))
    if texts:
        add('set_text', {'id': pick(texts), 'text': _text(EDIT_MAX, 0)}, ('id', 'text'))
    deletable = []
    for key, (node, _, _) in index(model).items():
        if key in allowed and 'blocks' not in node and all(
                child['id'] in allowed for child in node.get('rows') or node.get('items') or []):
            deletable.append(key)
    if deletable:
        add('delete', {'id': pick(deletable)}, ('id',))
    if sections:
        add('insert_section', {'after': pick(sections), 'heading': _text(300),
                               'blocks': {'type': 'array', 'maxItems': 20, 'items': block}}, ('after', 'heading', 'blocks'))
    return {'anyOf': variants} if variants else {}


def _minimal(schema):
    """Omit redundant keywords while retaining the inline subset accepted by every runner."""
    if isinstance(schema, list):
        return [_minimal(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _minimal(value) for key, value in schema.items()}
    if result.get('minLength') == 0:
        del result['minLength']
    if result.get('required') == []:
        del result['required']
    if result.get('type') == 'string' and result.get('enum') and all(isinstance(v, str) for v in result['enum']):
        del result['type']
        if len(result['enum']) == 1:
            result['const'] = result.pop('enum')[0]
    return result


def _ops(ids, model, maximum):
    item = model_op(model, ids) if model is not None else _op(ids)
    return {'type': 'array', 'maxItems': maximum if item else 0, 'items': item}


def edit_ops_packet(ids=None, owner=False, model=None):
    owner = owner and os.environ.get('UNCLE_PLAN_KIND') != 'change-plan'
    properties = {
        'dispositions': {'type': 'array', 'maxItems': 40, 'items': _object({
            'finding': _text(80), 'disposition': {'type': 'string', 'enum': list(DISPOSITIONS)},
            'reason': _text(300), 'plan_change': _text(300)}, ('finding', 'disposition', 'reason', 'plan_change'))},
        'ops': _ops(ids, model, 120),
        'commands_replace': _commands(),
    }
    if owner or os.environ.get('UNCLE_UPDATED_PLAN_STRUCTURE_REPAIR') == '1':
        properties['protected_verification_paths'] = _text(4000)
    packet = envelope(EDIT_OPS_KIND, properties, ['dispositions', 'ops'] + (['protected_verification_paths'] if owner else []))
    return _minimal(packet) if model is not None else packet


def resolution_ops_packet(ids=None, model=None):
    packet = envelope(RESOLUTION_OPS_KIND, {'resolutions': {'type': 'array', 'minItems': 1, 'maxItems': 40, 'items': _object({
        'group': _text(40), 'ops': _ops(ids, model, 60), 'commands_replace': _commands()},
        ('group',))}}, ['resolutions'])
    return _minimal(packet) if model is not None else packet


# What a self-hosted adapter enforces when it knows only the kind named in the prompt.
STATIC = {SECTION_KIND: section_packet(), SECTION_MODEL_KIND: section_model_packet(), OUTLINE_KIND: outline_packet(), EDIT_KIND: edit_packet(), RESOLUTION_KIND: resolution_packet(),
          EDIT_OPS_KIND: edit_ops_packet(), RESOLUTION_OPS_KIND: resolution_ops_packet()}


def plan_headings(plan_json):
    from plan_patch import split_sections
    plan = json.loads(Path(plan_json).read_text(encoding='utf-8'))
    return [section['heading'] for section in split_sections(plan.get('narrative') or '')[1]]


def plan_ids(plan_json):
    """Every section, block, row, item and step id of the plan, which is what an edit may name."""
    import plan_model
    model = plan_model.load_model(plan_json)
    return list(plan_model.index(model))


def main(argv):
    argv = list(argv)
    scope = None
    attempt = None
    if '--attempt' in argv:
        at = argv.index('--attempt')
        attempt = argv[at + 1]
        del argv[at:at + 2]
    if '--scope' in argv:
        at = argv.index('--scope')
        scope = json.loads(Path(argv[at + 1]).read_text(encoding='utf-8'))
        scope = scope['ids'] if isinstance(scope, dict) else scope
        del argv[at:at + 2]
    output = argv[2] if len(argv) > 2 else None
    try:
        if len(argv) == 3 and argv[0] == 'section':
            import project_plan_sections as sections
            schema = section_packet(sections.expected_headings(argv[1]), sections.trace_letters(argv[1]))
        elif len(argv) in (3, 4) and argv[0] == 'edit':
            schema = edit_packet(plan_headings(argv[1]), owner=len(argv) == 4)
        elif len(argv) == 4 and argv[0] == 'synthesis':
            # The single-call updated plan: the same patch object the local grammar holds a self-hosted model to
            import self_hosted
            schema = self_hosted.artifact_schema(argv[1], protected=argv[2] == 'protected', require_dispositions=True,
                                                 synthesis=True)
            if schema is None:
                raise ValueError('no synthesis schema for %s' % argv[1])
            output = argv[3]
        elif len(argv) == 2 and argv[0] == 'requirements':
            # The requirements interpretation, delivered through a schema-checked call (hosted Claude) instead of a Write tool call
            import self_hosted
            schema = self_hosted.artifact_schema('requirements-interpretation')
            output = argv[1]
        elif len(argv) == 3 and argv[0] == 'section-model':
            import project_plan_sections as sections
            if argv[1] == 'outline':
                schema = outline_packet()
            else:
                schema = section_model_packet([h[3:] for h in sections.expected_headings(argv[1])], sections.trace_letters(argv[1]),
                                              sections.row_kinds_of(argv[1]), sections.allows_steps(argv[1]))
        elif len(argv) in (3, 4) and argv[0] == 'edit-ops':
            from plan_model import load_model
            from updated_plan_ops import strict_schema_attempt
            model = load_model(argv[1]) if strict_schema_attempt(attempt) else None
            schema = edit_ops_packet(scope if scope is not None else plan_ids(argv[1]), owner=len(argv) == 4, model=model)
        elif len(argv) == 3 and argv[0] == 'resolve-ops':
            from plan_model import load_model
            from updated_plan_ops import strict_schema_attempt
            model = load_model(argv[1]) if strict_schema_attempt(attempt) else None
            schema = resolution_ops_packet(scope if scope is not None else plan_ids(argv[1]), model=model)
        elif len(argv) == 3 and argv[0] == 'resolve':
            schema = resolution_packet(plan_headings(argv[1]))
        else:
            raise SystemExit(__doc__)
        formatting = {'separators': (',', ':')} if argv[0] in ('edit-ops', 'resolve-ops') else {'indent': 2}
        Path(output).write_text(json.dumps(schema, **formatting) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError) as error:
        print('worker schemas: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
