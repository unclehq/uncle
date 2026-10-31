#!/usr/bin/env python3
"""The plan as data: sections of typed blocks addressed by id.  See docs/plan-model.md.

    plan_model.py report PLAN.json...     import each plan, render it back, and say what was lost
    plan_model.py view PLAN.json OUT.json       the plan as an agent reads it (the model, no Markdown narrative)
    plan_model.py attach PLAN.json MODEL.json   store an authored model beside the plan (PLAN.model.json) when it matches the narrative

Agents exchange this model as JSON; `render` produces the Markdown people read.  `import_markdown` exists
for plans written before the model did (and for none written after).  Nothing here calls a model.
"""
import copy
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_patch import split_sections

# row_kind -> [(field, rendered column title, is_list, aliases)].  The first field is the row's key.
# An alias is a column title with everything but letters and digits removed, lowercased.
ROW_KINDS = {
    'behavior': [('id', 'ID', False, ('id',)), ('trigger', 'Trigger', False, ('trigger',)),
                 ('result', 'Observable result', False, ('observableresult', 'expectedresult', 'result', 'behavior')),
                 ('failure', 'Failure behavior', False, ('failurebehavior', 'failure')),
                 ('requirements', 'Requirement IDs', True, ('requirementids', 'requirementid', 'requirements', 'reqs', 'req')),
                 ('verification', 'Verification', False, ('verification',))],
    'invariant': [('id', 'ID', False, ('id',)), ('statement', 'Invariant', False, ('invariant', 'statement')),
                  ('scope', 'Scope', False, ('scope',)),
                  ('enforcement', 'Enforcement point', False, ('enforcementpoint', 'enforcement')),
                  ('test', 'Automated test', False, ('automatedtest', 'test')),
                  ('impact', 'Violation impact', False, ('violationimpact', 'consequence', 'impact'))],
    'failure': [('id', 'ID', False, ('id',)), ('scenario', 'Failure scenario', False, ('failurescenario', 'scenario')),
                ('symptom', 'Observable symptom', False, ('observablesymptom', 'symptom')),
                ('handling', 'Handling', False, ('handling',)),
                ('requirements', 'Requirement IDs', True, ('requirementids', 'requirements', 'reqs'))],
    'concurrency': [('id', 'ID', False, ('id',)), ('concern', 'Concern', False, ('concern',)),
                    ('mechanism', 'Mechanism', False, ('mechanism',)),
                    ('rationale', 'Rationale', False, ('rationale',))],
    'component': [('id', 'ID', False, ('id',)), ('name', 'Name', False, ('name', 'component')),
                  ('files', 'File(s)', True, ('files', 'file', 'filess')),
                  ('responsibility', 'Responsibility', False, ('responsibility',)),
                  ('interface', 'Interface', False, ('interface',)),
                  ('state', 'Key props/state', False, ('keypropsstate', 'state')),
                  ('depends_on', 'Dependencies', True, ('dependencies', 'dependson'))],
    'state_field': [('field', 'Field', False, ('field',)), ('type', 'Type', False, ('type',)),
                    ('initial', 'Initial value', False, ('initialvalue', 'initial')),
                    ('description', 'Description', False, ('description',))],
    'automated_test': [('id', 'ID', False, ('id',)), ('name', 'Test name', False, ('testname', 'name')),
                       ('assertion', 'Assertion', False, ('assertion',)),
                       ('requirements', 'Requirements', True, ('requirements', 'requirementids', 'reqs'))],
    'obligation': [('id', 'ID', False, ('id',)), ('obligation', 'Obligation', False, ('obligation',)),
                   ('assertion', 'Observable assertion and independent oracle', False,
                    ('observableassertionandindependentoracle', 'assertion')),
                   ('evidence', 'Evidence', False, ('evidence',))],
    'manual_check': [('id', 'ID', False, ('id',)), ('check', 'Check', False, ('check',)),
                     ('assertion', 'Observable assertion', False, ('observableassertion', 'assertion')),
                     ('prerequisites', 'Prerequisites', False, ('prerequisites', 'prerequisite')),
                     ('evidence', 'Evidence to retain', False, ('evidencetoretain', 'evidence')),
                     ('requirements', 'Requirement IDs', True, ('requirementids', 'requirements', 'reqs'))],
    'mutation': [('id', 'ID', False, ('id',)), ('mutation', 'Mutation', False, ('mutation',)),
                 ('test', 'Targeted test', False, ('targetedtest', 'test')),
                 ('expected', 'Expected result', False, ('expectedresult', 'expected'))],
    'restriction': [('id', 'ID', False, ('id', 'rid')), ('source_kind', 'source_kind', False, ('sourcekind',)),
                    ('source', 'Source', False, ('source', 'sourcelocation')),
                    ('requirements', 'Reqs', True, ('reqs', 'req', 'requirementids', 'requirements')),
                    ('property', 'Property', False, ('property', 'requiredproperty')),
                    ('mechanism', 'Mechanism', False, ('mechanism', 'selectedmechanism')),
                    ('rationale', 'Rationale', False, ('rationale',)),
                    ('cap', 'CAP', False, ('cap', 'capids')),
                    ('binding', 'Runner/config binding', False, ('runnerconfigbinding', 'binding')),
                    ('evidence', 'Feasibility evidence', False, ('evidence', 'feasibilityevidence', 'feasibility',
                                                                'observedfeasibilityevidence')),
                    ('phase', 'Phase', False, ('phase',))],
    'decision': [('id', 'ID', False, ('id',)), ('decision', 'Decision', False, ('decision',)),
                 ('reason', 'Reason', False, ('reason', 'shortreason'))],
    'traceability': [('requirement', 'Requirement', False, ('requirement',)),
                     ('behaviors', 'Behavior', True, ('behavior', 'behaviors')),
                     ('invariants', 'Invariant', True, ('invariant', 'invariants')),
                     ('components', 'Component', True, ('component', 'components')),
                     ('tests', 'Automated test', True, ('automatedtest', 'tests')),
                     ('manual', 'Manual check', True, ('manualcheck', 'manual'))],
    'change_impact': [('component', 'Component', False, ('component',)),
                      ('change', 'Planned change', False, ('plannedchange', 'change')),
                      ('reason', 'Reason', False, ('reason',)),
                      ('risk', 'Regression risk', False, ('regressionrisk', 'risk')),
                      ('coverage', 'Test coverage', False, ('testcoverage', 'coverage'))],
}
ID_VALUE = re.compile(r'^[A-Z]{1,4}-?\d+[A-Za-z]?$')
TABLE_SEPARATOR = re.compile(r'^\|?[\s:|-]+\|[\s:|-]*$')
LIST_ITEM = re.compile(r'^(\s*)([-*+]|\d+\.)\s+(.*)$')
STEP_HEAD = re.compile(r'^\*\*(.+?)\*\*\s*(?:[—–:-]+\s*)?(.*)$', re.S)
OWNS = re.compile(r'^\s*(?:[-*+]\s*)?\**Owns\**(?:\s*\([^)]*\))?\**\s*:?\**\s*(.*)$', re.I)
DEPENDS = re.compile(r'^\s*(?:[-*]\s*)?\**Depends on\**\s*:?\**\s*(.*)$', re.I)
INLINE_OWNS = re.compile(r'(?:^|\s)\**Owns\**(?:\s*\([^)]*\))?\**\s*:\**\s+((?:`[^`]+`(?:,\s*)?)+)(?:\s*\**Depends on\**\s*:\**\s*([\w ,]*?))?\s*\.?$')     # a step on one line: "... Owns: `a`, `b` Depends on: 2"


class PlanError(ValueError):
    pass


def norm(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def strip_ticks(text):
    text = text.strip()
    return text[1:-1].strip() if len(text) > 2 and text[0] == text[-1] == '`' and '`' not in text[1:-1] else text


def owned_path(text):
    """One `Owns:` entry without its backticks or a trailing sentence period.

    Only the trailing period goes. `strip('`. ')` also ate the leading dot of
    `.gitignore` and `.uncle/launch.json`, so a step's declared files no longer
    matched what its worker wrote and the whole parallel implementation fan-out
    was discarded for an "ownership mismatch" (live, calculator).
    """
    return strip_ticks(text.strip().rstrip('.')).strip('` ')


def cells_of(line):
    parts = re.split(r'(?<!\\)\|(?=(?:[^`]*`[^`]*`)*[^`]*$)', line.strip())   # not a | inside a `code span`
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [part.strip().replace('\\|', '|') for part in parts]


def detect_kind(headers):
    """(row_kind, [field or None per header]) when a table's headers are a typed row kind, else (None, None)."""
    best = None
    names = [norm(h) for h in headers]
    for kind, fields in ROW_KINDS.items():
        mapping, used = [], set()
        for name in names:
            hit = next((f[0] for f in fields if f[0] not in used and (name in f[3] or any(len(a) >= 9 and name.startswith(a) for a in f[3]))), None)
            if hit:
                used.add(hit)
            mapping.append(hit)
        matched = len(used)
        if fields[0][0] not in used or matched < 2 or matched * 2 < len(headers):
            continue
        if best is None or matched > best[0]:
            best = (matched, kind, mapping)
    return (best[1], best[2]) if best else (None, None)


def fit(cells, width):
    """Exactly `width` cells: a row with too many (a bare | inside a cell) keeps the overflow in the last cell."""
    if len(cells) > width > 0:
        cells = cells[:width - 1] + [' | '.join(cells[width - 1:])]
    return cells + [''] * (width - len(cells))


def make_row(kind, mapping, headers, cells, serial):
    cells = fit(cells, len(headers))
    fields = {f[0]: f for f in ROW_KINDS[kind]}
    row, extra = {}, {}
    for header, field, cell in zip(headers, mapping, cells):
        if field is None:
            extra[header] = cell
        elif fields[field][2]:
            row[field] = [strip_ticks(part) for part in re.split(r'[,;]\s*', cell) if part.strip()]
        else:
            row[field] = cell
    for field in fields:
        row.setdefault(field, [] if fields[field][2] else '')
    key = ROW_KINDS[kind][0][0]
    value = row[key]
    if key == 'id':
        row['id'] = value or serial
    else:
        row['id'] = value if isinstance(value, str) and ID_VALUE.match(value) else serial
    if extra:
        row['extra'] = extra
    return row


def parse_blocks(body, section_id):
    lines = body.split('\n')
    blocks, i, count = [], 0, [0]

    def new_id():
        count[0] += 1
        return '%s.%d' % (section_id, count[0])

    def prose(text):
        if blocks and blocks[-1]['kind'] == 'prose':
            blocks[-1]['text'] += '\n\n' + text
        else:
            blocks.append({'id': new_id(), 'kind': 'prose', 'text': text})

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith('```'):
            end = i + 1
            while end < len(lines) and not lines[end].startswith('```'):
                end += 1
            blocks.append({'id': new_id(), 'kind': 'code', 'lang': line[3:].strip(), 'text': '\n'.join(lines[i + 1:end])})
            i = end + 1
        elif re.match(r'^#{3,6}\s', line):
            level = len(line) - len(line.lstrip('#'))
            blocks.append({'id': new_id(), 'kind': 'heading', 'level': level, 'text': line[level:].strip()})
            i += 1
        elif line.startswith('|') and i + 1 < len(lines) and TABLE_SEPARATOR.match(lines[i + 1].strip()):
            headers, end = cells_of(line), i + 2
            while end < len(lines) and lines[end].startswith('|'):
                end += 1
            rows = [cells_of(row) for row in lines[i + 2:end]]
            block_id = new_id()
            kind, mapping = detect_kind(headers)
            if kind:
                out = [make_row(kind, mapping, headers, cells, '%s.r%d' % (block_id, n)) for n, cells in enumerate(rows, 1)]
                blocks.append({'id': block_id, 'kind': 'rows', 'row_kind': kind, 'rows': out})
            else:
                blocks.append({'id': block_id, 'kind': 'table', 'columns': headers,
                               'rows': [{'id': '%s.r%d' % (block_id, n), 'cells': fit(cells, len(headers))}
                                        for n, cells in enumerate(rows, 1)]})
            i = end
        elif LIST_ITEM.match(line):
            end = i
            while end < len(lines):
                if lines[end].strip() and (LIST_ITEM.match(lines[end]) or lines[end].startswith((' ', '\t'))):
                    end += 1
                elif not lines[end].strip() and end + 1 < len(lines) and LIST_ITEM.match(lines[end + 1]):
                    end += 1     # a blank line between two items of one list
                else:
                    break
            blocks.append(parse_list([l for l in lines[i:end] if l.strip()], new_id()))
            i = end
        else:
            end = i
            while end < len(lines) and lines[end].strip() and not lines[end].startswith(('```', '|')) \
                    and not re.match(r'^#{3,6}\s', lines[end]) and not LIST_ITEM.match(lines[end]):
                end += 1
            end = max(end, i + 1)
            prose('\n'.join(lines[i:end]))
            i = end
    return blocks


def parse_list(lines, block_id):
    items = []
    numbered = (bool(lines and re.match(r'^\d+\. ', lines[0]))
                and any(OWNS.match(line) or INLINE_OWNS.search(line) for line in lines))
    for line in lines:
        match = LIST_ITEM.match(line)
        if match and (not numbered or (match.group(2)[0].isdigit() and not match.group(1))):
            items.append({'indent': len(match.group(1)), 'marker': match.group(2), 'lines': [match.group(3)]})
        elif items:
            items[-1]['lines'].append(line.strip())
    one_line = [INLINE_OWNS.search(item['lines'][0]) for item in items]
    if items and items[0]['marker'][0].isdigit() and sum(1 for f in one_line if f) * 2 >= len(items):
        for item, found in zip(items, one_line):       # "N. **Title** -- text Owns: `a` Depends on: 2" reads like the three-line form
            if found and not any(OWNS.match(l) for l in item['lines'][1:]):
                item['lines'] = ([item['lines'][0][:found.start()], 'Owns: ' + found.group(1)]
                                 + (['Depends on: ' + found.group(2)] if (found.group(2) or '').strip() else []) + item['lines'][1:])
    owns = sum(1 for item in items if any(OWNS.match(l) for l in item['lines'][1:]))
    if items and items[0]['marker'][0].isdigit() and owns:
        steps = []
        for item in items:
            number = int(item['marker'][:-1])
            head = STEP_HEAD.match(item['lines'][0])
            title, text = (head.group(1).strip(), head.group(2).strip()) if head else ('', item['lines'][0])
            step_owns, depends = [], []
            for extra in item['lines'][1:]:
                if OWNS.match(extra):
                    step_owns.extend(owned for owned in map(owned_path, re.split(r',\s*', OWNS.match(extra).group(1))) if owned)
                elif DEPENDS.match(extra):
                    depends = [int(n) for n in re.findall(r'\d+', DEPENDS.match(extra).group(1))]
                else:
                    text += '\n' + extra
            steps.append({'id': 'step-%d' % number, 'number': number, 'title': title, 'text': text.strip(),
                          'owns': step_owns, 'depends_on': depends})
        return {'id': block_id, 'kind': 'steps', 'items': steps}
    ordered = bool(items) and items[0]['marker'][0].isdigit()
    base = min((item['indent'] for item in items), default=0)
    out = []
    for n, item in enumerate(items, 1):
        node = {'id': '%s.i%d' % (block_id, n), 'depth': (item['indent'] - base) // 2, 'text': '\n'.join(item['lines'])}
        if item['marker'][0].isdigit() != ordered:      # a numbered item in a bullet list, or the reverse
            node['style'] = 'number' if item['marker'][0].isdigit() else 'bullet'
        if item['marker'][0].isdigit():
            node['number'] = int(item['marker'][:-1])
        out.append(node)
    return {'id': block_id, 'kind': 'list', 'ordered': ordered, 'items': out}


def implementation_blocks(body, section_id):
    heads = list(re.finditer(r'^#{3,6}\s+(?:Step\s+)?(\d+)[:.)-]\s*(.*)$', body, re.M | re.I))
    if not heads:
        return parse_blocks(body, section_id)
    blocks = parse_blocks(body[:heads[0].start()], section_id)
    steps = []
    for n, head in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(body)
        lines = body[head.end():end].strip().splitlines()
        owned, deps, text = [], [], []
        for line in lines:
            if OWNS.match(line):
                owned.extend(split_list(OWNS.match(line).group(1)))
            elif DEPENDS.match(line):
                deps.extend(int(x) for x in re.findall(r'\d+', DEPENDS.match(line).group(1)))
            else:
                text.append(line)
        number = int(head.group(1))
        steps.append({'id': 'step-%d' % number, 'number': number, 'title': head.group(2),
                      'text': '\n'.join(text).strip(), 'owns': owned, 'depends_on': deps})
    blocks.append({'id': '%s.%d' % (section_id, len(blocks) + 1), 'kind': 'steps', 'items': steps})
    return blocks


def steps_of(model):
    return [step for section in model['sections'] for block in section['blocks']
            if block['kind'] == 'steps' for step in block['items']]


def dependency_list(value):
    if isinstance(value, list) and all(type(n) is int and n >= 0 for n in value):
        return value[:]
    if isinstance(value, str) and re.fullmatch(r'\s*(?:\d+(?:\s*,\s*\d+)*)?\s*', value):
        return [int(n) for n in re.findall(r'\d+', value)]
    raise PlanError('depends_on: use step numbers as an integer array or comma-separated list')


def protected_paths(value):
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list) and all(isinstance(p, str) for p in value):
        return value[:]
    raise PlanError('protected_verification_paths: use paths, one per line or a string array')


def with_protected(model, plan):
    if 'protected_verification_paths' in plan:
        model = dict(model, protected_verification_paths=protected_paths(plan['protected_verification_paths']))
    return model


def ownership_errors(model, root=None):
    from step_groups import covers
    errors = []
    specific = [set(s.get('owns', [])) - {'*'} for s in steps_of(model)]
    for path in protected_paths(model.get('protected_verification_paths', [])):
        if not valid_path(path.rstrip('/')):
            errors.append('protected_verification_paths: replace %r with a repository-relative path' % path)
        elif root is not None and (Path(root) / path).exists():
            continue
        elif any(covers(owned, path) or (path.endswith('/') and any(p.startswith(path) for p in owned))
                 for owned in specific):
            continue
        elif root is not None:
            errors.append('protected path %r has no creator; set_step <creator-id> owns: add %s' % (path, path))
    return errors


def valid_path(path):
    return (isinstance(path, str) and bool(path) and not re.search(r'[\s`,;\\]', path)
            and not path.startswith(('/', '-', '~')) and not path.endswith('/')
            and not any(p in ('', '.', '..') for p in path.split('/'))
            and path != '.git' and not path.startswith('.git/'))


def import_markdown(narrative):
    """The model for a plan that exists only as Markdown (legacy plans)."""
    preamble, sections = split_sections(narrative)
    title = ''
    match = re.match(r'^#\s+(.*)$', preamble.split('\n', 1)[0]) if preamble else None
    intro = preamble
    if match:
        title, intro = match.group(1).strip(), preamble.split('\n', 1)[1].strip() if '\n' in preamble else ''
    model = {'title': title, 'intro': intro, 'sections': []}
    for number, section in enumerate(sections, 1):
        sid = 's%d' % number
        parser = implementation_blocks if re.search(r'Implementation (?:order|sequence|steps)', section['heading'], re.I) else parse_blocks
        model['sections'].append({'id': sid, 'heading': section['heading'][3:].strip(),
                                  'blocks': parser(section['body'], sid)})
    return dedupe(model)


def dedupe(model):
    """Make every id unique.  Real plans reuse one (a component C-1 and a concurrency concern C-1): the second
    definition is addressed as '<block id>/<its id>' and keeps the id it shows in `label`."""
    seen = set()
    for section in model['sections']:
        seen.add(section['id'])
        for block in section['blocks']:
            seen.add(block['id'])
            for row in block.get('rows') or block.get('items') or []:
                if row['id'] in seen:
                    row['label'] = row['id']
                    row['id'] = '%s/%s' % (block['id'], row['id'])
                seen.add(row['id'])
    return model


# ---- render -------------------------------------------------------------------------------------------

def cell_text(value):
    return ', '.join(value) if isinstance(value, list) else (value or '')


def escape(text):
    return text.replace('|', '\\|').replace('\n', ' ')


def render_block(block):
    kind = block['kind']
    if kind == 'prose':
        return block['text']
    if kind == 'heading':
        return '#' * block['level'] + ' ' + block['text']
    if kind == 'code':
        return '```%s\n%s\n```' % (block.get('lang', ''), block['text'])
    if kind == 'rows':
        fields = ROW_KINDS[block['row_kind']]
        keep = [f for n, f in enumerate(fields) if n == 0 or any(cell_text(r.get(f[0])) for r in block['rows'])]
        extras = list(dict.fromkeys(k for r in block['rows'] for k in r.get('extra', {})))
        out = ['| ' + ' | '.join([f[1] for f in keep] + extras) + ' |', '|' + '---|' * (len(keep) + len(extras))]
        for r in block['rows']:
            out.append('| ' + ' | '.join([escape(cell_text(r.get('label', r.get(f[0])) if f[0] == 'id' else r.get(f[0]))) for f in keep]
                                         + [escape(r.get('extra', {}).get(k, '')) for k in extras]) + ' |')
        return '\n'.join(out)
    if kind == 'table':
        out = ['| ' + ' | '.join(block['columns']) + ' |', '|' + '---|' * len(block['columns'])]
        out += ['| ' + ' | '.join(escape(c) for c in r['cells']) + ' |' for r in block['rows']]
        return '\n'.join(out)
    if kind == 'list':
        out = []
        for item in block['items']:
            numbered = item.get('style') == 'number' or (block.get('ordered') and item.get('style') != 'bullet')
            marker = '%d.' % item.get('number', 1) if numbered else '-'
            pad = '  ' * item.get('depth', 0)
            first, *rest = item['text'].split('\n')
            out.append(pad + marker + ' ' + first)
            out += [pad + ' ' * (len(marker) + 1) + line for line in rest]
        return '\n'.join(out)
    if kind == 'steps':
        out = []
        for step in block['items']:
            head = ('**%s** — %s' % (step['title'], step['text']) if step['title'] else step['text']).rstrip(' —')
            first, *rest = head.split('\n')
            out.append('%d. %s' % (step['number'], first))
            out += ['   ' + line for line in rest]
            if step['owns']:
                out.append('   Owns: ' + ', '.join('`%s`' % p for p in step['owns']))
            if step['depends_on']:
                out.append('   Depends on: ' + ', '.join(str(n) for n in step['depends_on']))
        return '\n'.join(out)
    raise PlanError('unknown block kind %r' % kind)


def render(model):
    head = '# ' + model['title'] if model.get('title') else ''
    parts = [part for part in (head, model.get('intro') or '') if part]
    for section in model['sections']:
        body = '\n\n'.join(render_block(block) for block in section['blocks'])
        parts.append('## ' + section['heading'] + ('\n\n' + body if body else ''))
    return '\n\n'.join(parts) + '\n'


# ---- index, validate ----------------------------------------------------------------------------------

def index(model):
    """{id: (node, parent list, section)} for every section, block, row, item and step."""
    found = {}
    for section in model['sections']:
        found[section['id']] = (section, model['sections'], section)
        for block in section['blocks']:
            found[block['id']] = (block, section['blocks'], section)
            for row in block.get('rows') or block.get('items') or []:
                found[row['id']] = (row, block.get('rows') if 'rows' in block else block['items'], section)
    return found


def validate(model, root='.'):
    """(errors, warnings).  Errors make the plan unusable; warnings are things a person should look at."""
    errors, warnings, seen = [], [], set()
    for section in model['sections']:
        for node in [section] + section['blocks'] + [r for b in section['blocks'] for r in b.get('rows') or b.get('items') or []]:
            if node['id'] in seen:
                errors.append('id %r is used twice' % node['id'])
            seen.add(node['id'])
    steps = steps_of(model)
    numbers, graph = set(), {}
    for step in steps:
        number = step.get('number')
        if type(number) is not int or number < 0:
            errors.append('%s number: use a nonnegative integer' % step['id'])
            continue
        if number in numbers:
            errors.append('%s number %d is used twice; renumber this step and its references' % (step['id'], number))
        numbers.add(number)
        owned = step.get('owns')
        if not isinstance(owned, list):
            errors.append('%s owns: use a file/glob array' % step['id'])
        else:
            if not owned:
                warnings.append('step %d owns no files' % number)
            for token in owned:
                if not valid_path(token) or (root is not None and (Path(root) / token).is_dir()):
                    errors.append('%s owns: replace %s with a file or glob (directory/**)' % (step['id'], repr(token)[:96]))
        deps = step.get('depends_on')
        if not isinstance(deps, list) or any(type(d) is not int for d in deps):
            errors.append('%s depends_on: use an integer array' % step['id'])
        else:
            graph[number] = deps
    for number, deps in graph.items():
        for dep in deps:
            if dep not in numbers or dep == number:
                errors.append('step %d depends on %r, which is not another step; set_step step-%d depends_on: remove %s'
                              % (number, dep, number, dep))
    state = {}

    def visit(n):
        state[n] = 1
        for dep in graph.get(n, []):
            if dep not in numbers or dep == n:
                continue
            if state.get(dep) == 1:
                errors.append('dependency cycle; set_step step-%d depends_on: remove %d' % (n, dep))
            elif state.get(dep) != 2:
                visit(dep)
        state[n] = 2
    for n in graph:
        if n not in state:
            visit(n)
    if not errors:
        errors.extend(ownership_errors(model, root))
    return errors, warnings


# ---- operations ---------------------------------------------------------------------------------------

def next_id(model, prefix):
    used = set(index(model))
    number = 1
    while '%s%d' % (prefix, number) in used:
        number += 1
    return '%s%d' % (prefix, number)


def op_keys(op):
    """What an op touches, for conflict detection: (id, field) pairs; field '*' means all of it."""
    name = op.get('op')
    if name == 'set_fields':
        return {(op['id'], f) for f in op.get('fields') or {}}
    if name == 'set_step':
        return {(op['id'], f) for f in op if f not in ('op', 'id')}
    if name == 'set_text':
        return {(op['id'], 'text')}
    if name == 'delete':
        return {(op['id'], '*')}
    if name == 'replace_section':
        return {(op['section'], '*')}
    if name == 'set_heading':
        return {(op['section'], 'heading')}
    if name in ('insert_row', 'insert_item', 'insert_block'):
        return {('after:' + str(op.get('after') or op.get('block') or op.get('list') or op.get('section')), '*')}
    if name == 'insert_section':
        return {('after:' + str(op.get('after')), '*')}
    raise PlanError('unknown op %r' % name)


def parent_of(model):
    """{id: id of what holds it} for every block, row, item and step (sections have no parent)."""
    found = {}
    for section in model['sections']:
        for block in section['blocks']:
            found[block['id']] = section['id']
            for row in block.get('rows') or block.get('items') or []:
                found[row['id']] = block['id']
    return found


def conflicts(model, ops_by_writer):
    """[[(writer, op), ...]] groups of ops from different writers that cannot both apply.

    Two ops clash when they touch the same field of the same id, when one removes or rewrites a whole id (field
    '*') that the other touches or sits inside, or when they insert after the same anchor.  Identical ops from
    two writers are one op and never clash."""
    parent = parent_of(model)

    def inside(child, ancestor):
        while child is not None:
            if child == ancestor:
                return True
            child = parent.get(child)
        return False

    def clash(a, b):
        for ka, fa in op_keys(a):
            for kb, fb in op_keys(b):
                if ka == kb and (fa == fb or '*' in (fa, fb)):
                    return True
                if (fa == '*' and inside(kb, ka)) or (fb == '*' and inside(ka, kb)):
                    return True
        return False

    entries, seen = [], set()
    for writer, ops in ops_by_writer:
        for op in ops:
            sig = json.dumps(op, sort_keys=True)
            if sig not in seen:
                seen.add(sig)
                entries.append((writer, op))
    groups = []
    for writer, op in entries:
        hit = [g for g in groups if any(clash(op, other) and writer != w for w, other in g)]
        groups = [g for g in groups if g not in hit] + [[item for g in hit for item in g] + [(writer, op)]]
    return [g for g in groups if len({w for w, _ in g}) > 1]


def fresh_ids(model, section_id, block):
    """`block` with an id (and ids for its list items) that nothing in the model uses yet."""
    block = copy.deepcopy(block)
    used = set(index(model))
    number = 1
    while '%s.%d' % (section_id, number) in used:
        number += 1
    block.setdefault('id', '%s.%d' % (section_id, number))
    for n, item in enumerate(block.get('items') or [], 1):
        if block['kind'] == 'list' and not item.get('id'):
            item['id'] = '%s.i%d' % (block['id'], n)
    return block


def locate(model, key):
    where = index(model)
    if key not in where:
        raise PlanError('no section, block, row or item has the id %r' % key)
    return where[key]


def apply_ops(model, ops, root=None):
    """A new model with every op applied; the first op that names something missing raises PlanError."""
    root = Path.cwd() if root is None else root
    # An edit answers for what it changes: a quirk the plan already had (run 12's
    # nested "1." read as a second step 1) must not block an unrelated fix.
    already = set(validate(model, root=root)[0])
    model = copy.deepcopy(model)
    for op in ops:
        name = op.get('op')
        if name == 'set_fields':
            row = locate(model, op['id'])[0]
            for field, value in (op.get('fields') or {}).items():
                if field not in row and field != 'extra':
                    raise PlanError('%s has no field %r' % (op['id'], field))
                row[field] = value
        elif name == 'set_text':
            node = locate(model, op['id'])[0]
            if 'text' not in node:
                raise PlanError('%s has no text to set' % op['id'])
            node['text'] = op['text']
        elif name == 'set_step':
            node = locate(model, op['id'])[0]
            if 'number' not in node:
                raise PlanError('%s is not a step' % op['id'])
            for field in ('title', 'text', 'owns', 'depends_on'):
                if field in op:
                    node[field] = op[field]
        elif name == 'delete':
            node, parent, _ = locate(model, op['id'])
            parent.remove(node)
        elif name == 'replace_section':
            section = locate(model, op['section'])[0]
            section['blocks'] = copy.deepcopy(op['blocks'])
        elif name == 'set_heading':
            locate(model, op['section'])[0]['heading'] = op['heading']
        elif name in ('insert_row', 'insert_item'):
            block = locate(model, op['block'] if name == 'insert_row' else op['list'])[0]
            rows = block.get('rows') if name == 'insert_row' else block.get('items')
            if rows is None:
                raise PlanError('%s has no %s' % (op.get('block') or op.get('list'), 'rows' if name == 'insert_row' else 'items'))
            new = copy.deepcopy(op['row'] if name == 'insert_row' else op['item'])
            if not new.get('id'):
                new['id'] = '%s.i%d' % (block['id'], len(rows) + 1)
                while new['id'] in index(model):
                    new['id'] += 'x'
            if new['id'] in index(model):
                raise PlanError('id %r already exists' % new['id'])
            after = op.get('after')
            position = 0 if after is None else rows.index(locate(model, after)[0]) + 1
            rows.insert(position, new)
        elif name == 'insert_block':
            section = locate(model, op['section'])[0]
            after = op.get('after')
            position = 0 if after is None else section['blocks'].index(locate(model, after)[0]) + 1
            section['blocks'].insert(position, fresh_ids(model, section['id'], op['block']))
        elif name == 'insert_section':
            after = locate(model, op['after'])[0]
            fresh = {'id': op.get('id') or next_id(model, 's'), 'heading': op['heading'], 'blocks': []}
            model['sections'].insert(model['sections'].index(after) + 1, fresh)
            for block in op.get('blocks') or []:
                fresh['blocks'].append(fresh_ids(model, fresh['id'], block))
        else:
            raise PlanError('unknown op %r' % name)
    errors = [e for e in validate(model, root=root)[0] if e not in already]
    if errors:
        raise PlanError(errors[0])
    return model


# ---- flat ops (what a model writes) -------------------------------------------------------------------

FIELD_NAMES = sorted({f[0] for fields in ROW_KINDS.values() for f in fields})
OP_NAMES = ('set_fields', 'set_text', 'set_step', 'insert_row', 'insert_item', 'insert_block', 'delete', 'insert_section')


def split_list(text):
    # JSON worker packets may naturally represent a typed list as an array.
    # Treat that as equivalent to the legacy comma-delimited string instead
    # of crashing during a speculative merge and forcing the whole panel to
    # run again in the foreground.
    if isinstance(text, list):
        if not all(isinstance(part, str) for part in text):
            raise PlanError('a typed list must contain only strings')
        return [strip_ticks(part) for part in text if part.strip()]
    if not isinstance(text, str):
        raise PlanError('a typed list must be a string or JSON string array')
    return [strip_ticks(part) for part in re.split(r'[,;\n]\s*', text or '') if part.strip()]


def block_of(model, node):
    """The rows or list block that holds `node` (a row, item or step)."""
    for section in model['sections']:
        for block in section['blocks']:
            for member in block.get('rows') or block.get('items') or []:
                if member is node:
                    return block
    raise PlanError('no block holds %r' % node.get('id'))


def typed_row(kind, flat):
    fields = {f[0]: f for f in ROW_KINDS[kind]}
    row = {'id': flat.get('id') or ''}
    for field, spec in fields.items():
        value = flat.get(field, '')
        row[field] = split_list(value) if spec[2] else value
    for field in flat:
        if field not in fields and field != 'id':
            raise PlanError('a %s row has no field %r' % (kind, field))
    return row


def typed_block(flat):
    kind = flat.get('kind')
    if kind == 'prose':
        return {'kind': 'prose', 'text': flat.get('text', '')}
    if kind == 'heading':
        level = int(flat.get('level') or 3)
        if not 3 <= level <= 6:
            raise PlanError('a heading block has level 3 to 6, not %d' % level)
        return {'kind': 'heading', 'level': level, 'text': flat.get('text', '')}
    if kind == 'code':
        return {'kind': 'code', 'lang': flat.get('lang', ''), 'text': flat.get('text', '')}
    if kind == 'list':
        return {'kind': 'list', 'ordered': False, 'items': [{'depth': 0, 'text': t} for t in flat.get('items') or []]}
    raise PlanError('a new block is prose, heading, code or list, not %r' % kind)


def typed_op(model, flat):
    """The typed op for one flat op written as strings; PlanError names what is wrong with it."""
    name = flat.get('op')
    if name not in OP_NAMES:
        raise PlanError('unknown op %r' % name)
    if name in ('set_fields', 'set_text', 'set_step', 'delete'):
        node = locate(model, flat.get('id') or '')[0]
        if name == 'delete':
            return {'op': 'delete', 'id': flat['id']}
        if name == 'set_text':
            return {'op': 'set_text', 'id': flat['id'], 'text': flat.get('text', '')}
        fields = flat.get('fields') or {}
        if 'number' in node:
            if set(fields) - {'title', 'text', 'owns', 'depends_on'}:
                raise PlanError('a step has the fields title, text, owns and depends_on')
            op = {'op': 'set_step', 'id': flat['id']}
            for field, value in fields.items():
                op[field] = split_list(value) if field == 'owns' else dependency_list(value) if field == 'depends_on' else value
            return op
        block = block_of(model, node)
        if block['kind'] != 'rows':
            detail = 'use set_text' if 'text' in node else 'its fields are ' + ', '.join(k for k in node if k != 'id')
            raise PlanError('%s is not a typed row; %s' % (flat['id'], detail))
        specs = {f[0]: f for f in ROW_KINDS[block['row_kind']]}
        out = {}
        for field, value in fields.items():
            if field not in specs or field == 'id':
                raise PlanError('%s has no field %r to set (its fields: %s)' % (
                    flat['id'], field, ', '.join(f for f in specs if f != 'id')))
            out[field] = split_list(value) if specs[field][2] else value
        return {'op': 'set_fields', 'id': flat['id'], 'fields': out}
    after = flat.get('after') or None
    if name in ('insert_row', 'insert_item'):
        block = locate(model, flat.get('target') or '')[0]
        new = flat.get('new') or {}
        if name == 'insert_row':
            if block.get('kind') != 'rows':
                raise PlanError('%s is not a typed rows block' % flat['target'])
            return {'op': 'insert_row', 'block': flat['target'], 'after': after, 'row': typed_row(block['row_kind'], new)}
        if block.get('kind') == 'steps':
            number = int(new.get('number') or 0)
            if number < 1 or new.get('id') != 'step-%d' % number:
                raise PlanError('a new step needs a number and the id step-<number>')
            item = {'id': new['id'], 'number': number, 'title': new.get('title', ''), 'text': new.get('text', ''),
                    'owns': split_list(new.get('owns')), 'depends_on': dependency_list(new.get('depends_on') or '')}
        elif block.get('kind') == 'list':
            item = {'id': new.get('id') or '', 'depth': 0, 'text': new.get('text', '')}
        else:
            raise PlanError('%s is neither a list nor steps' % flat['target'])
        return {'op': 'insert_item', 'list': flat['target'], 'after': after, 'item': item}
    if name == 'insert_block':
        locate(model, flat.get('target') or '')
        return {'op': 'insert_block', 'section': flat['target'], 'after': after, 'block': typed_block(flat.get('block') or {})}
    return {'op': 'insert_section', 'after': flat.get('after') or '', 'heading': flat.get('heading') or '',
            'blocks': [typed_block(b) for b in flat.get('blocks') or []]}


# ---- authoring: a worker's flat blocks -> typed sections -----------------------------------------------

BLOCK_KINDS = ('prose', 'heading', 'code', 'list', 'rows', 'table', 'steps')


def build_rows(kind, flat_rows, block_id):
    """Typed rows for a `rows` block written as flat all-string objects."""
    if kind not in ROW_KINDS:
        raise PlanError('unknown row_kind %r' % kind)
    key = ROW_KINDS[kind][0][0]
    rows = []
    for n, flat in enumerate(flat_rows, 1):
        row = typed_row(kind, flat)
        value = row.get(key)
        if key == 'id':
            if not value:
                raise PlanError('a %s row needs an id' % kind)
        else:
            row['id'] = value if isinstance(value, str) and ID_VALUE.match(value) else '%s.r%d' % (block_id, n)
        rows.append(row)
    return rows


def authored_block(flat, block_id):
    """The typed block for one block a section worker wrote; PlanError says what is wrong with it."""
    kind = flat.get('kind')
    if kind in ('prose', 'heading', 'code', 'list'):
        block = typed_block(flat)
        if kind == 'list':
            block['ordered'] = bool(flat.get('ordered'))
            for n, item in enumerate(block['items'], 1):
                item['id'] = '%s.i%d' % (block_id, n)
        block['id'] = block_id
        return block
    if kind == 'rows':
        if not flat.get('rows'):
            raise PlanError('a rows block has no rows')
        return {'id': block_id, 'kind': 'rows', 'row_kind': flat.get('row_kind'),
                'rows': build_rows(flat.get('row_kind'), flat['rows'], block_id)}
    if kind == 'table':
        columns = flat.get('columns') or []
        if not columns or not flat.get('cells'):
            raise PlanError('a table block needs columns and cells')
        return {'id': block_id, 'kind': 'table', 'columns': columns,
                'rows': [{'id': '%s.r%d' % (block_id, n), 'cells': fit(list(cells), len(columns))}
                         for n, cells in enumerate(flat['cells'], 1)]}
    if kind == 'steps':
        steps = []
        for flat_step in flat.get('steps') or []:
            number = int(flat_step.get('number') or 0)
            if number < 1:
                raise PlanError('a step needs a number')
            steps.append({'id': 'step-%d' % number, 'number': number, 'title': flat_step.get('title', ''),
                          'text': flat_step.get('text', ''), 'owns': split_list(flat_step.get('owns')),
                          'depends_on': dependency_list(flat_step.get('depends_on') or '')})
        if not steps:
            raise PlanError('a steps block has no steps')
        return {'id': block_id, 'kind': 'steps', 'items': steps}
    raise PlanError('a block is one of %s, not %r' % (', '.join(BLOCK_KINDS), kind))


def flat_of(block):
    """The flat, all-string form of a typed block: what a section worker would write to produce it."""
    kind = block['kind']
    if kind in ('prose', 'code'):
        return {k: v for k, v in block.items() if k != 'id'}
    if kind == 'heading':
        return {'kind': 'heading', 'level': str(block['level']), 'text': block['text']}
    if kind == 'list':
        return {'kind': 'list', 'ordered': bool(block.get('ordered')), 'items': [i['text'] for i in block['items']]}
    if kind == 'rows':
        fields = ROW_KINDS[block['row_kind']]
        rows = []
        for row in block['rows']:
            flat = {f[0]: ', '.join(row[f[0]]) if f[2] else row[f[0]] for f in fields if row.get(f[0])}
            if fields[0][0] == 'id':
                flat['id'] = row.get('label', row['id'])
            rows.append(flat)
        return {'kind': 'rows', 'row_kind': block['row_kind'], 'rows': rows}
    if kind == 'table':
        return {'kind': 'table', 'columns': block['columns'], 'cells': [r['cells'] for r in block['rows']]}
    if kind == 'steps':
        return {'kind': 'steps', 'steps': [{'number': str(s['number']), 'title': s['title'], 'text': s['text'],
                                            'owns': ', '.join(s['owns']), 'depends_on': ', '.join(map(str, s['depends_on']))}
                                           for s in block['items']]}
    raise PlanError('unknown block kind %r' % kind)


def empty_block(flat):
    """True for a block a model left empty (rows: [], no items, blank text): noise, not content."""
    kind = flat.get('kind')
    if kind == 'rows':
        return not flat.get('rows')
    if kind == 'list':
        return not flat.get('items')
    if kind == 'table':
        return not flat.get('cells')
    if kind == 'steps':
        return not flat.get('steps')
    if kind in ('prose', 'heading'):
        return not (flat.get('text') or '').strip()
    return False


def authored_section(heading, flat_blocks, section_id):
    flat_blocks = [flat for flat in flat_blocks if not empty_block(flat)]
    blocks = [authored_block(flat, '%s.%d' % (section_id, n)) for n, flat in enumerate(flat_blocks, 1)]
    return {'id': section_id, 'heading': heading, 'blocks': blocks}


def model_from_flat(flat_sections, title='', root=None, stage=None):
    """A model from sections written as flat blocks, in any order and under any headings (a change plan)."""
    sections = []
    for n, row in enumerate(flat_sections, 1):
        heading = re.sub(r'^#+\s*', '', (row.get('heading') or '').strip())
        if not heading:
            raise PlanError('a section has no heading')
        section = authored_section(heading, row.get('blocks') or [], 's%d' % n)
        if not section['blocks']:
            raise PlanError('section %r is empty' % heading)
        sections.append(section)
    if not sections:
        raise PlanError('the plan has no sections')
    model = dedupe({'title': title, 'intro': '', 'sections': sections})
    if renumber_enabled({}, root or Path.cwd(), stage):
        model = renumber_steps(model, root or Path.cwd())
    errors, _ = validate(model)
    if errors:
        raise PlanError('; '.join(errors))
    return model


def records_enabled(root=None):
    """Runner-neutral migration switch, using the existing config parser and precedence."""
    value = os.environ.get('WORKFLOW_PLAN_RECORDS')
    if value is None:
        path = os.environ.get('UNCLE_CONFIG') or str(Path(root or Path.cwd()) / '.uncle/config')
        if not Path(path).is_file():
            return True
        from self_hosted_http import _config_values
        value = _config_values(path).get('workflow.plan-records', '1')
    if value.strip().lower() not in ('0', '1', 'false', 'true'):
        raise PlanError('workflow.plan-records: use 0 or 1')
    return value.strip().lower() in ('1', 'true')


def renumber_steps(model, root=None):
    """Repair only numbering, leaving ambiguous references for the normal correction round."""
    steps = steps_of(model)
    if not steps or all(step.get('number') == n for n, step in enumerate(steps, 1)):
        return model
    if any(type(step.get('number')) is not int or step['number'] < 0 for step in steps):
        return model
    revised = copy.deepcopy(model)
    for position, step in enumerate(steps_of(revised), 1):
        deps = step.get('depends_on')
        if not isinstance(deps, list) or any(type(dep) is not int for dep in deps):
            return model
        mapped = []
        for dep in deps:
            targets = [n for n, old in enumerate(steps, 1) if old['number'] == dep and n != position]
            if len(targets) != 1:
                return model
            mapped.append(targets[0])
        step['number'], step['depends_on'] = position, mapped
    return model if validate(revised, root=root)[0] else revised


def renumber_narrative(narrative, before, after):
    """Change only step markers and Depends on numbers; unfamiliar layouts fall back."""
    fields = ('number', 'title', 'text', 'owns', 'depends_on')
    original_steps = steps_of(before)
    imported_steps = steps_of(import_markdown(narrative))
    if [[s.get(f) for f in fields] for s in original_steps] != [[s.get(f) for f in fields] for s in imported_steps]:
        return None
    headings = list(re.finditer(r'^## .+$', narrative, re.M))
    if len(headings) != len(before['sections']):
        return None
    edits = []
    for index, section in enumerate(before['sections']):
        old = [s for b in section['blocks'] if b['kind'] == 'steps' for s in b['items']]
        if not old:
            continue
        new = [s for b in after['sections'][index]['blocks'] if b['kind'] == 'steps' for s in b['items']]
        start = headings[index].end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(narrative)
        body = narrative[start:end]
        pattern = r'^[ \t]*(\d+)\.[ \t]+'
        if re.search(r'Implementation (?:order|sequence|steps)', section['heading'], re.I) and re.search(
                r'^#{3,6}\s+(?:Step\s+)?\d+[:.)-]\s*', body, re.M | re.I):
            pattern = r'^#{3,6}\s+(?:Step\s+)?(\d+)[:.)-]\s*'
        markers = list(re.finditer(pattern, body, re.M | re.I))
        if len(markers) != len(old):
            return None
        for n, (marker, previous, revised) in enumerate(zip(markers, old, new)):
            if int(marker[1]) != previous['number']:
                return None
            edits.append((start + marker.start(1), start + marker.end(1), str(revised['number'])))
            stop = markers[n + 1].start() if n + 1 < len(markers) else len(body)
            chunk = body[marker.end():stop]
            refs = list(re.finditer(r'(?im)\bDepends on:?\**[ \t]*([\d ,]+)', chunk))
            if len(refs) > 1 or (bool(refs) != bool(previous['depends_on'])):
                return None
            if refs:
                ref = refs[0]
                digits = list(re.finditer(r'\d+', ref[1]))
                if [int(d[0]) for d in digits] != previous['depends_on']:
                    return None
                for digit, value in zip(digits, revised['depends_on']):
                    offset = start + marker.end() + ref.start(1)
                    edits.append((offset + digit.start(), offset + digit.end(), str(value)))
    for start, end, value in sorted(edits, reverse=True):
        narrative = narrative[:start] + value + narrative[end:]
    return narrative


def plan_stage(plan, name=''):
    if Path(name).stem == 'UPDATED_PROJECT_PLAN':
        return 'updated-plan'
    if Path(name).stem == 'PROJECT_PLAN':
        return 'project-plan'
    if plan.get('kind') == 'change-plan':
        return 'updated-change-plan' if 'dispositions' in plan else 'change-plan'
    return 'updated-plan' if 'dispositions' in plan else 'project-plan'


def renumber_enabled(plan, root, stage=None):
    from self_hosted import config_stage
    from self_hosted_http import _config_values
    from unit_scheduler import granularity, option
    config = _config_values(os.environ.get('UNCLE_CONFIG') or str(Path(root) / '.uncle/config'))
    stage = stage or os.environ.get('UNCLE_STATUS_STAGE') or plan_stage(plan)
    parent = config_stage(stage, config)
    runner = config.get(parent + '.runner', config.get('runner', 'claude'))
    if runner not in ('self-hosted', 'opencode', 'aider') or granularity('self-hosted', stage, config) != 'small':
        return False
    value = option('self-hosted', stage, 'plan-renumber', 'on', config)
    if value not in ('on', 'off', '1', '0', 'true', 'false'):
        raise PlanError('self-hosted.plan-renumber must be on or off')
    return value in ('on', '1', 'true')


def publish_records(plan, root='.', model=None, stage=None):
    """Validate and retain records on a plan write; leave legacy untyped plans alone.

    Also usable by the edit-op merger after it has chosen its protected paths:
    result = publish_records(result, model=new_model).
    """
    if not records_enabled(root):
        return plan
    model = with_protected(model_of(plan) if model is None else model, plan)
    if not steps_of(model) and not plan.get('sections'):
        return plan
    if renumber_enabled(plan, root, stage):
        revised = renumber_steps(model, root)
        if revised is not model:
            if not plan.get('narrative'):
                model = revised
            else:
                narrative = renumber_narrative(plan['narrative'], model, revised)
                if narrative is not None:
                    plan, model = dict(plan, narrative=narrative), revised
    errors, _ = validate(model, root=root)
    if errors:
        raise PlanError(errors[0])
    return dict(plan, **{key: model[key] for key in ('title', 'intro', 'sections')})


def consistent(plan):
    """True when the plan's `sections` still say what its `narrative` says (the narrative is their rendering)."""
    import collections
    model = {'title': plan.get('title', ''), 'intro': plan.get('intro', ''), 'sections': plan['sections']}
    return collections.Counter(words(render(model))) == collections.Counter(words(plan.get('narrative') or ''))


def model_of(plan):
    """Canonical sections are authoritative; import the narrative only for legacy plans."""
    if 'sections' in plan:
        return with_protected({'title': plan.get('title', ''), 'intro': plan.get('intro', ''), 'sections': plan['sections']}, plan)
    return import_markdown(plan.get('narrative') or '')


def sidecar(plan_path):
    """Where the authored model of a plan JSON lives: beside it, so the plan JSON agents read does not carry two descriptions."""
    path = Path(plan_path)
    return path.with_name(path.stem + '.model.json')


def load_model(plan_path):
    """Canonical sections, else a matching legacy sidecar, else the narrative imported."""
    import collections
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    if 'sections' in plan:
        return model_of(plan)
    try:
        model = json.loads(sidecar(plan_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return model_of(plan)
    if collections.Counter(words(render(model))) == collections.Counter(words(plan.get('narrative') or '')):
        return with_protected(model, plan)
    return model_of(plan)


def agent_view(plan_path, out_path):
    """The plan as an agent reads it: the model (sections of blocks, rows with ids), the commands and the protected
    paths, with no Markdown narrative.  People read `narrative`; an agent given this file cites ids that exist."""
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    model = load_model(plan_path)
    view = {'schema': 'uncle.artifact/v1', 'kind': 'plan-view', 'title': model.get('title', ''), 'sections': model['sections']}
    for field in ('verification_commands', 'protected_verification_paths'):
        if plan.get(field):
            view[field] = plan[field]
    Path(out_path).write_text(json.dumps(view, ensure_ascii=False) + '\n', encoding='utf-8')


def attach(plan_path, model_path):
    """Store an authored model beside a plan JSON, when its rendering says what the plan's narrative says.

    The narrative stays in the plan: it is what people read and what the stages not yet ported read.  A model
    whose words differ from the narrative's is not stored, because two descriptions of one plan must not disagree."""
    import collections
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    model = dedupe(json.loads(Path(model_path).read_text(encoding='utf-8')))
    before, after = collections.Counter(words(plan.get('narrative') or '')), collections.Counter(words(render(model)))
    if before != after:
        raise PlanError('the authored model differs from the narrative: lost %s, added %s'
                        % (dict((before - after).most_common(5)), dict((after - before).most_common(5))))
    model = with_protected(model, plan)
    errors, _ = validate(model, root=Path.cwd())
    if errors:
        raise PlanError('the authored model does not validate: %s' % '; '.join(errors))
    sidecar(plan_path).write_text(json.dumps(model, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


# ---- report -------------------------------------------------------------------------------------------

def words(markdown):
    """Content words of a Markdown plan with table header and separator lines left out, for comparing."""
    kept, lines = [], markdown.split('\n')
    for n, line in enumerate(lines):
        if TABLE_SEPARATOR.match(line.strip()) and line.strip().startswith('|'):
            continue
        if line.startswith('|') and n + 1 < len(lines) and TABLE_SEPARATOR.match(lines[n + 1].strip()):
            continue
        kept.append(line)
    return re.findall(r'[A-Za-z0-9_]+', '\n'.join(kept).replace('Depends on', 'dependson'))


def report(path):
    import collections
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    narrative = plan.get('narrative') or ''
    model = import_markdown(narrative)
    errors, warnings = validate(model)
    before, after = collections.Counter(words(narrative)), collections.Counter(words(render(model)))
    again = import_markdown(render(model))
    blocks = collections.Counter(b['kind'] + (':' + b['row_kind'] if b['kind'] == 'rows' else '')
                                 for s in model['sections'] for b in s['blocks'])
    return {'path': str(path), 'sections': len(model['sections']), 'blocks': dict(blocks),
            'lost': dict((before - after).most_common(8)), 'added': dict((after - before).most_common(8)),
            'stable': again == model, 'errors': errors, 'warnings': warnings}


def main(argv):
    if len(argv) >= 2 and argv[0] == 'report':
        for path in argv[1:]:
            print(json.dumps(report(path), indent=2))
        return 0
    if len(argv) == 3 and argv[0] == 'view':
        try:
            agent_view(argv[1], argv[2])
        except (PlanError, OSError, ValueError, KeyError) as error:
            print('plan model: %s' % error, file=sys.stderr)
            return 1
        return 0
    if len(argv) == 3 and argv[0] == 'attach':
        try:
            attach(argv[1], argv[2])
        except (PlanError, OSError, ValueError) as error:
            print('plan model: %s' % error, file=sys.stderr)
            return 1
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
