#!/usr/bin/env python3
"""The parallel updated-plan fan-out, editing the plan model by id (docs/plan-model.md, phase 2).

Same stages as updated_plan_edits.py -- slices, one writer per finding, a mechanical merge, one short resolver per
group of overlapping edits -- with one difference: a writer receives the plan as JSON (sections, blocks, rows
with ids) and answers with `ops` that name an id and a field, so there is no text to quote and nothing to
miscopy.  The merge applies the ops to the model and publishes the result as the section-level patch the rest
of the pipeline already reads, so nothing downstream changes.

    updated_plan_ops.py slices REVIEW.json            (as updated_plan_edits.py)
    updated_plan_ops.py prompt BASE_PROMPT IDS OUT [owner]
    updated_plan_ops.py merge PLAN.json SLICES.tsv DIR OUTPUT [RESOLUTIONS_DIR]   (UNCLE_LATE_OPS=reconcile.json adds its ops last)
    updated_plan_ops.py reconcile BASE_PROMPT SLICES DIR ADVISORS.json OUT       the prompt that checks the specialists' corrections
    updated_plan_ops.py resplit SLICES.tsv NAME...    (as updated_plan_edits.py)
    updated_plan_ops.py check PLAN.json DIR           (exit 5 with the group ids when a resolver answer cannot be applied)
    (exit 3: edits overlap; DIR/prompts/resolve-<group>.md are the resolvers' prompts)
"""
import copy
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_model as pm
import updated_plan_edits as base
from plan_patch import apply_patch, split_sections
from updated_plan_fast_path import protected_paths, derive_protected_paths
from updated_plan_synthesis_prompt import EDIT_RULES
from worker_schemas import EDIT_OPS_KIND, RESOLUTION_OPS_KIND

Conflict, NeedsResolution, CHANGE = base.Conflict, base.NeedsResolution, base.CHANGE

OPS_RULES = '''`ops` is an array of edits to the plan model in the last section of this prompt. The plan is JSON: sections
hold blocks, blocks hold rows, list items or steps, and every section, block, row, item and step has an `id`.
You name an id that exists. You never quote text and never name a heading. Follow the supplied schema's field types;
list fields (requirements, files, owns) use string arrays. Existing step dependencies use numbers or step ids;
`new:N` references the Nth inserted step in this packet when an existing step must depend on it.
Legacy schemas may instead request comma-separated strings for these lists.

- `{"op":"set_fields","id":"B-1","fields":{"failure":"..."}}` changes only the named fields of the row `id`. The
  field names are the keys of that row in the model.
- `{"op":"set_text","id":"s1.2","text":"..."}` replaces the text of a `prose` block or a list item.
- `{"op":"set_step","id":"step-3","fields":{"title":"...","text":"...","owns":["a.js", "b.js"],"depends_on":[1, 2]}}`
  changes only the fields named.
- `{"op":"insert_row","target":"<id of a rows block>","after":"B-3","new":{"id":"B-9", ...fields}}` adds a row after
  the row `after` ("" for first). The new row's id is new and unused.
- `{"op":"insert_item","target":"<id of a list block>","after":"<item id or empty>","new":{"text":"..."}}` adds a list item.
- `{"op":"insert_step","after":"step-1","new":{"title":"...","text":"...","owns":["a.js"],"depends_on":["step-1"]}}`
  adds an implementation step. Use `before` instead of `after` to insert before an existing step, or `after:"end"` to append.
  Never supply a new step's id or number: the driver assigns both and rewrites dependencies after merging every packet.
  New-step dependencies name existing step ids, or `new:N` for the Nth new step in this packet (1-based).
- `{"op":"insert_block","target":"<section id>","after":"<block id or empty>","block":{"kind":"prose","text":"..."}}`; block
  kinds are prose, heading (level, text), code (lang, text) and list (items: an array of strings).
- `{"op":"delete","id":"..."}` removes a row, list item, step or block.
- `{"op":"insert_section","after":"<section id>","heading":"13. Title","blocks":[ ...block shapes as above... ]}`.

Change as little as the finding needs: one `set_fields` on the row, not a new row. Other writers edit this plan at the
same time; two edits to the same field of the same id are rejected, so edit only what your findings require.'''

SLICE_NOTE = '''

## Your slice (binding; overrides the instructions above where they differ)

Other writers are resolving the remaining findings at the same time, from this same plan model.
Their ops are merged mechanically with yours.

- You own exactly these findings: %s. The other rows above are context only.
- Write one disposition for each of your findings and none for any other.
- Edit only what your findings require. Never rewrite what another finding obviously owns.
- Your reply has `ops`, not `patch`.
%s'''

DECIDE_NOTE = '''
## You decide each finding yourself (binding)

No specialist has reviewed these findings. Check each of yours against the plan model before you edit anything:
- A finding whose premise is wrong (the plan already says what it asks for, or the rule or id it cites does not exist) is
  `Rejected`, with that reason; write no op for it.
- A finding that is real but outside this plan's scope, or that needs a decision nobody here can make, is `Deferred`, with
  the reason; write no op for it.
- Otherwise it is `Accepted` (or `Partially accepted` when you change less than it asks), and your ops make the change.
- Only the id a finding names, and the ids that must change with it, are yours to edit. Another writer owns every other finding.
'''

EXAMPLE = ('{"schema":"uncle.artifact/v1","kind":"%s","dispositions":[{"finding":"AR-001","disposition":"Accepted",'
           '"reason":"...","plan_change":"..."}],"ops":[{"op":"set_fields","id":"B-1","fields":{"failure":"..."}}],'
           '"commands_replace":[]%s}')
PLAN_BLOCK = re.compile(r'## Existing sections in the base plan, in order.*?## Base project plan JSON\n```json\n(.*?)\n```\n', re.S)
PLAN_JSON = re.compile(r'## Base project plan JSON\n```json\n(.*?)\n```\n', re.S)
SECTIONS_ONLY = re.compile(r'## Existing sections in the base plan, in order.*?(?=## Base project plan JSON)', re.S)


def option(name, default):
    """Stage env overrides family env, then stage/family config, then the default."""
    from self_hosted_http import _config_values
    config = _config_values()
    stage = os.environ.get('UNCLE_PLAN_KIND', '')
    family = 'updated-change-plan' if stage == 'change-plan' else 'updated-plan'
    names = list(dict.fromkeys([family, 'updated-plan']))
    convert = int if isinstance(default, int) else str
    for prefix in names:
        key = 'WORKFLOW_' + (prefix + '-' + name).upper().replace('-', '_')
        if os.environ.get(key, '').strip():
            return convert(os.environ[key])
    # Retain existing callers' slice controls.
    if name == 'group-size':
        for key in ('WORKFLOW_UPDATED_PLAN_EDIT_SLICE', 'WORKFLOW_UPDATED_PLAN_PARALLEL_SLICE'):
            if os.environ.get(key, '').strip():
                return int(os.environ[key])
    for prefix in names:
        if config.get(prefix + '.' + name):
            return convert(config[prefix + '.' + name])
    return default


def strict_schema_attempt(attempt=None):
    if not option('strict-op-schemas', 1):
        return False
    # Only self-hosted callers pass an attempt; other runners keep their schema.
    if attempt is None:
        return True
    mode = option('strict-schema', 'retry').strip().lower()
    if mode not in ('first', 'retry', 'always') or attempt not in ('first', 'retry'):
        raise ValueError('updated-plan.strict-schema must be first, retry or always')
    return mode == 'always' or mode == attempt


def check_writer(plan_path, packet_path, ids):
    plan = base.read_json(plan_path)
    model = plan_model_of(plan, plan_path)
    delivery = read_packet(packet_path)
    findings = {row.get('finding') for row in delivery.get('dispositions') or [] if isinstance(row, dict)}
    missing = set(ids.split(',')) - findings
    if missing:
        raise pm.PlanError('missing dispositions for %s' % ', '.join(sorted(missing)))
    pm.apply_ops(model, [pm.typed_op(model, flat) for flat in delivery.get('ops') or []])
    commands = (plan.get('verification_commands') or '').strip()
    for edit in delivery.get('commands_replace') or []:
        if not isinstance(edit, dict) or not edit.get('old') or commands.count(edit['old']) != 1:
            raise pm.PlanError('command text is not in the verification commands exactly once')


def slices(ids):
    size = option('group-size', 2)
    if size < 1:
        raise Conflict('updated-plan.group-size must be positive')
    if len(ids) < base.MIN_FINDINGS:
        return []
    # Concurrency is the dispatcher's job; a writer-count ceiling must not enlarge slices.
    return [(str(i // size + 1), ids[i:i + size]) for i in range(0, len(ids), size)]


def writer_budget(ids, granularity='small'):
    # Small-unit runners (self-hosted by default) get a short tool budget; large-unit
    # runners keep their usual turns (0 = no driver limit) unless one is configured.
    turns = option('writer-turns', 3 if granularity == 'small' else 0)
    expected_ops = option('ops-per-finding', 4)
    per_op = option('tokens-per-op', 512)
    if turns < 0 or min(expected_ops, per_op) < 1:
        raise Conflict('updated-plan writer budgets must be positive')
    return turns, max(4096, 1024 + len(ids) * (512 + expected_ops * per_op))


def resolver_budget(directory, group_id):
    groups = json.loads(Path(directory, 'conflicts.json').read_text(encoding='utf-8'))
    for group in groups:
        if group['id'] == group_id:
            return writer_budget(group['edits'])
    raise Conflict('unknown resolver group %s' % group_id)


def first_packet(text):
    """Decode the first complete packet, leaving validation to the existing consumer.

    Do not scan past a malformed first object into its nested objects or a second answer.
    """
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].lstrip()
    value, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(value, dict):
        raise Conflict('expected a JSON packet object')
    return value


def read_packet(path):
    try:
        return first_packet(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise Conflict('%s: not a valid packet: %s' % (path, error)) from error


def capture_packet(path):
    path = Path(path)
    value = read_packet(path)
    # Merge still checks finding coverage, ops and conflicts. Capture never repairs JSON.
    if not isinstance(value.get('ops'), list) and not isinstance(value.get('resolutions'), list):
        raise Conflict('expected an edit or resolution packet')
    intent_file = path.parent / 'prompts' / (path.stem + '.intent.json')
    if intent_file.is_file():
        try:
            pin_delivery(value, json.loads(intent_file.read_text(encoding='utf-8')))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')


def plan_model_of(plan, path=None):
    """The plan's model: the authored sidecar beside its file when that agrees with the narrative, else the narrative imported."""
    return pm.load_model(path) if path else pm.model_of(plan)


def finding_scope(model, findings):
    """Find editable locations from review evidence, without expanding their ancestors."""
    from worker_schemas import scoped_ids
    if len(findings) > 1:
        return sorted({key for finding in findings for key in finding_scope(model, [finding])})
    where = pm.index(model)
    context = re.sub(r'(?<![\w./-])(?:\./)+(?=[\w.])', '', json.dumps(findings, ensure_ascii=False))
    limit = option('scope-sections', 2)
    if limit < 1:
        raise Conflict('updated-plan.scope-sections must be positive')
    if not option('finding-scopes', 1):
        return list(where)

    def mentions(value, text=None):
        text = context if text is None else text
        return bool(re.search(r'(?<![\w.-])' + re.escape(value) + r'(?![\w.-])', text, re.I))

    def words(text):
        ignored = {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'plan', 'project', 'json',
                   'table', 'section', 'step', 'file', 'test', 'tests', 'none', 'has', 'not', 'its',
                   'are', 'but', 'all', 'only', 'does', 'through', 'says', 'should', 'required',
                   'change', 'address', 'verify', 'check', 'run', 'evidence', 'severity', 'critical', 'high'}
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        return {w for w in re.findall(r'[a-z][a-z0-9]+', text.lower()) if len(w) > 2 and w not in ignored}

    def own_text(node):
        return json.dumps({k: v for k, v in node.items() if k not in ('id', 'blocks', 'rows', 'items')}, ensure_ascii=False)

    def step_body(section):
        keys = []
        for block in section['blocks']:
            heading = re.search(r'(?:^|\n)#+\s+', block.get('text', ''))
            if not heading or block['text'][:heading.start()].strip():
                keys.append(block['id'])
            if heading:
                break
        return keys or [section['id']]

    # Ranges in evidence (MC-1 through MC-10, Steps 2-3) cite every member, not just endpoints.
    for match in list(re.finditer(r'\b([A-Z][A-Z0-9]*-)(\d+)\s*(?:through|to|[–-])\s*(?:\1)?(\d+)\b', context)):
        prefix, start, end = match.groups()
        if 0 <= int(end) - int(start) <= 300:
            context += ' ' + ' '.join(prefix + str(i) for i in range(int(start), int(end) + 1))
    step_numbers = set()
    step_labels = {label.lower() for label in re.findall(r'\bsteps?\s+(\d+[a-z]*)\b', context, re.I)}
    for match in re.finditer(r'\bsteps?\s+(\d+)\b(?:\s*(?:through|to|[–-])\s*(?:steps?\s+)?(\d+)\b)?', context, re.I):
        start, end = int(match[1]), int(match[2] or match[1])
        if 0 <= end - start <= 300:
            step_numbers.update(range(start, end + 1))
    references = set(re.findall(r'\b[A-Z][A-Z0-9]*-\d+\b', context))
    paths = set(re.findall(r'(?<![\w./-])(?:[.\w-]+/)*[.\w-]+\.[a-zA-Z][a-zA-Z0-9]*', context))
    # Legacy intro tables have no editable ids; follow their component/file links to the owning step.
    cited_intro = '\n'.join(line for line in model.get('intro', '').splitlines()
                            if any(mentions(ref, line) for ref in references - set(where)))
    query = words(context + ' ' + cited_intro)
    for line in model.get('intro', '').splitlines():
        if line.startswith('|'):
            cells = pm.cells_of(line)
            if len(cells) >= 3 and re.fullmatch(r'`?[\w.-]+/[\w./-]+`?', cells[1]):
                component = words(cells[0])
                if ((re.search(r'[a-z][A-Z]', cells[0]) and component & query)
                        or cells[0] in context):
                    paths.add(cells[1].strip('`'))
    symbols = set(re.findall(r'\b[a-z]+[A-Z][a-zA-Z]+\b', context))
    paths -= {'PROJECT_PLAN.json', 'PROJECT_PLAN.md', 'REQUIREMENTS_INTERPRETATION.json', 'REQUIREMENTS_INTERPRETATION.md'}
    for node, _, _ in where.values():
        declared = []
        for field in ('owns', 'files'):
            value = node.get(field, [])
            declared.extend(value.split(',') if isinstance(value, str) else value)
        if 'Owns:' in node.get('heading', ''):
            declared.extend(node['heading'].split('Owns:', 1)[1].split(','))
        paths.update(pm.owned_path(path) for path in declared if mentions(pm.owned_path(path)))
    targets = {key for key in where if mentions(key)}
    targets.update(step['id'] for step in implementation_steps(model)
                   if not step.get('_heading') and step['number'] in step_numbers)
    # Prefer owners to incidental mentions (e.g. an injection row mentioning a source file).
    owned_paths = set()
    for path in paths:
        for key, (node, _, _) in where.items():
            ownership = json.dumps({field: node[field] for field in ('owns', 'files') if field in node})
            heading = node.get('heading', '')
            if mentions(path, ownership) or ('Owns:' in heading and mentions(path, heading)):
                targets.update(step_body(node) if 'blocks' in node else [key])
                owned_paths.add(path)
    paths -= owned_paths
    for key, (node, _, _) in where.items():
        text = own_text(node)
        if 'blocks' not in node and any(mentions(ref, text) for ref in references | paths):
            targets.add(key)
        if node.get('kind') in ('prose', 'code') and any(mentions(symbol, text) for symbol in symbols):
            targets.add(key)
        if 'blocks' in node:
            heading = node['heading']
            title = re.split(r'\s+[—–]\s+Owns:', heading, flags=re.I)[0]
            title = re.sub(r'^\d+\.\s*', '', title)
            step = re.match(r'Step\s+(\d+[a-z]*)\b', title, re.I)
            if step and (step[1].lower() in step_labels or (step[1].isdigit() and int(step[1]) in step_numbers)
                         or any(mentions(path, heading) for path in paths)):
                # A legacy step section may also contain the closing tables; only the step body belongs here.
                targets.update(step_body(node))
            elif (mentions(title) or any(mentions(path, heading) for path in paths)
                  or (re.match(r'^(\d+)\.', heading) and re.search(
                      r'\bsection\s+' + re.escape(heading.split('.')[0]) + r'\b', context, re.I))):
                targets.add(key)
            # Imported single-# headings live in prose blocks. Include their following table/list.
            for pos, block in enumerate(node['blocks']):
                for heading_match in re.finditer(r'(?:^|\n)#+\s+([^\n]+)', block.get('text', '')):
                    title = heading_match[1].strip()
                    if mentions(title) or mentions(title.split(' and ')[0]):
                        targets.add(block['id'])
                        for following in node['blocks'][pos + 1:]:
                            if re.search(r'(?:^|\n)#+\s+', following.get('text', '')):
                                break
                            targets.add(following['id'])

    if not targets:
        query = words(context)
        ranked = []
        section_words = [words(json.dumps(section, ensure_ascii=False)) for section in model['sections']]
        for section in model['sections']:
            heading = words(section['heading'])
            body = words(json.dumps(section, ensure_ascii=False))
            score = 4 * len(query & heading) + sum(1 / sum(word in section for section in section_words) for word in query & body)
            if score:
                ranked.append((score, section['id']))
        targets = {key for _, key in sorted(ranked, key=lambda item: (-item[0], item[1]))[:limit]}
    if not targets and where:
        print('updated-plan ops: no relevant scope found; using whole-plan scope', file=sys.stderr)
        return list(where)
    return scoped_ids(model, targets)


# --- findings whose operation the driver decides ----------------------------------------------------------------------------------
# "Add a test" and "add a defect injection" findings are an insert into one known table. The operation, the table, the place in it
# and the new id are then facts about the plan, not judgment, so the driver fixes them (the writer's schema allows only that one
# insert_row, and a delivered insert into that table is re-pinned) and the model fills in the row's fields. Conservative on
# purpose: a finding that says the plan contradicts itself, or that is not plainly about a missing test or injection, is left to
# the writer as before, and so is any writer that owns more than one finding.
INTENT_CONFLICT = re.compile(r'\b(?:conflict|contradict|inconsisten|mismatch|disagree|incorrect|wrong|ambiguous|misleading)\w*', re.I)
INTENT_INJECTION = re.compile(
    r'\b(?:no|missing|lacks?|lacking|without|absent|add|adds|adding|needs?|requires?)\b[^.\n]{0,40}'
    r'\b(?:defect[- ]inject\w*|mutation\w*|mutant\w*)\b', re.I)
INTENT_TEST = re.compile(
    r'\b(?:no|missing|lacks?|lacking|without|absent|add|adds|adding|needs?|requires?)\b[^.\n]{0,30}'
    r'\b(?:automated |unit |e2e |browser |regression )?test(?:s| case| cases)?\b|'
    r'\bnot covered by any (?:automated )?test\b|\buntested\b', re.I)
INTENT_KINDS = (('mutation', INTENT_INJECTION, 'DI-'), ('automated_test', INTENT_TEST, 'T-'))


def rows_block(model, row_kind):
    for section in model['sections']:
        for block in section['blocks']:
            if block.get('kind') == 'rows' and block.get('row_kind') == row_kind:
                return block
    return None


def finding_intent(model, finding, advice=()):
    """{'op','target','after','row_kind','new_id','label'} when this finding is plainly "add a row to that table", else None."""
    if not isinstance(finding, dict):
        return None
    text = ' '.join(str(finding.get(key, '')) for key in ('title', 'failure', 'fix', 'references'))
    text += ' ' + ' '.join(str(c) for row in advice if isinstance(row, dict) for c in row.get('required_corrections') or [])
    if INTENT_CONFLICT.search(text):
        return None
    for row_kind, pattern, prefix in INTENT_KINDS:
        if not pattern.search(text):
            continue
        block = rows_block(model, row_kind)
        if block is None:
            return None
        members = [row['id'] for row in block.get('rows') or [] if isinstance(row, dict) and row.get('id')]
        used = set(pm.index(model))
        numbers = [int(m[1]) for ident in members for m in [re.fullmatch(re.escape(prefix) + r'(\d+)', ident)] if m]
        number = (max(numbers) if numbers else 0) + 1
        while prefix + str(number) in used:
            number += 1
        return {'op': 'insert_row', 'target': block['id'], 'after': members[-1] if members else '', 'row_kind': row_kind,
                'new_id': prefix + str(number), 'label': 'add_defect_injection' if row_kind == 'mutation' else 'add_test'}
    return None


INTENT_NOTE = '''

## The driver decided this finding's operation (binding)

Your finding asks for a new row in the %s table. The driver fixed the operation, so you do not choose one: if you accept the
finding, `ops` holds exactly one `insert_row` into `%s`, after `%s`, with the new row's `id` `%s` (the schema allows nothing
else). Your part is the row's field values, written from the finding and the rows already in the table. If the finding is wrong
or out of scope, reject or defer it with `"ops": []`.
'''


def write_intent(model, findings, output, scope, advice=()):
    """Write `<name>.intent.json` beside the writer's scope file for a single deterministic finding, add its table to the scope, and
    return the intent. Any stale intent file is removed first."""
    target = Path(output).with_suffix('.intent.json')
    target.unlink(missing_ok=True)
    if len(findings) != 1:
        return None, scope
    intent = finding_intent(model, findings[0], advice)
    if not intent:
        return None, scope
    target.write_text(json.dumps(intent) + '\n', encoding='utf-8')
    return intent, sorted(set(scope) | {intent['target']} | ({intent['after']} - {''}))


def pin_delivery(delivery, intent):
    """Re-pin what the driver owns in a delivered packet: an insert_row into the intent's table goes after the pinned row, under the
    pinned id. Other ops are untouched. Returns whether anything changed."""
    changed = False
    for op in delivery.get('ops') or []:
        if isinstance(op, dict) and op.get('op') == 'insert_row' and op.get('target') == intent['target']:
            new = op.get('new')
            if not isinstance(new, dict):
                continue
            if op.get('after') != intent['after'] or new.get('id') != intent['new_id']:
                op['after'], new['id'] = intent['after'], intent['new_id']
                changed = True
    return changed


def write_prompt(base_path, ids, output, owns_fields=False, note=None):
    """The sealed prompt with the patch instructions and the plan text replaced by the ops instructions and the model."""
    text = Path(base_path).read_text(encoding='utf-8')
    found = PLAN_JSON.search(text)
    if not found or EDIT_RULES not in text:
        raise Conflict('the base prompt is not in the shape the ops writers expect')
    # The same model the merge will read: the authored sidecar beside the plan file when the driver names the file.
    plan_file = os.environ.get('UNCLE_PLAN_JSON')
    model = plan_model_of(json.loads(found.group(1)), plan_file if plan_file and Path(plan_file).is_file() else None)
    kind = 'change-plan' if CHANGE else 'plan'
    text = base.EXAMPLE_BLOCK.sub(lambda _: '```json\n' + EXAMPLE % (EDIT_OPS_KIND, ',"protected_verification_paths":"..."' if owns_fields and not CHANGE else '') + '\n```', text)
    text = text.replace(EDIT_RULES, OPS_RULES)
    text = text.replace('and a `patch` object naming only what changed', 'and an `ops` array naming only what changed')
    text = text.replace('reconstructs the plan\'s full text from `patch`', 'reconstructs the plan\'s full text from `ops`')
    text = text.replace('must be reflected by some `patch` entry', 'must be reflected by some `ops` entry')
    text = SECTIONS_ONLY.sub('', text)
    text = PLAN_JSON.sub(lambda _: '## Plan model (JSON)\n\nUse existing ids below; your assigned scope limits which ones you may edit.\n```json\n%s\n```\n'
                         % json.dumps({k: v for k, v in model.items()}, ensure_ascii=False, separators=(',', ':')), text)
    assigned_context = []
    if ids:
        for heading in ('Adversarial review findings', 'Collated specialist corrections'):
            match = re.search(r'## ' + heading + r'[^\n]*\n```json\n(.*?)\n```', text, re.S)
            if match:
                value = json.loads(match[1])
                assigned_context.extend(row for row in value.get('findings', []) if row.get('id') in ids)
        text += ('\n\nAll plan sections and findings are supplied above. Do not read files, run commands or '
                 'investigate. Decide and deliver the small packet now; normally one answer is enough.\n')
    if not CHANGE:
        original = json.loads(found.group(1))
        text += '\n\nBase verification contract (preserve unless your findings change it):\n' + json.dumps(
            {key: original.get(key, '') for key in ('verification_commands', 'protected_verification_paths')}, ensure_ascii=False)
    notes = '' if CHANGE else (base.FIELDS_OWNER if owns_fields else base.FIELDS_OTHER) + base.COMMANDS_NOTE
    if note is None:
        note = SLICE_NOTE % (', '.join(ids), notes)
        if 'Collated specialist corrections' not in text:      # deciding writers: nobody has reviewed the findings first
            text += DECIDE_NOTE
    if assigned_context:
        note += '\n\n## Assigned findings and corrections\n```json\n' + json.dumps(assigned_context, ensure_ascii=False) + '\n```\n'
    scope = finding_scope(model, assigned_context)
    intent, scope = write_intent(model, assigned_context, output, scope)
    Path(output).with_suffix('.scope.json').write_text(json.dumps(scope) + '\n', encoding='utf-8')
    note += '\n\nAssigned edit scope (ids): ' + ', '.join(scope) + '.\n'
    if intent:
        note += INTENT_NOTE % (intent['row_kind'].replace('_', ' '), intent['target'], intent['after'] or '(the start of the table)',
                              intent['new_id'])
    Path(output).write_text(base.defer_reply_example(text) + note, encoding='utf-8')


RECONCILE_NOTE = '''

## Your task (binding; overrides the instructions above where they differ)

Other writers have already decided every finding and written the ops listed below. Specialist reviewers then checked
the findings and wrote the corrections listed after them. You decide no finding. Your only job is to find a correction
that none of those ops already meets, and write ops for it.

- Write `"dispositions": []`.
- Write ops only for what no listed op already does. Never repeat a listed op, and never change a field that a listed
  op changes: the driver drops any op of yours that does. If every correction is already met, answer with `"ops": []`.
- A correction that names a plan id is met when a listed op edits that id; one that names no id is met when a listed op plainly
  does what it says. When in doubt that something is missing, leave it out: a wrong extra edit costs more than a gap the
  audit below still sees.

Ops already written, by finding:
```json
%s
```

Specialist corrections, by finding:
```json
%s
```
'''


def decided_ops(slices_path, directory):
    """[{finding, ops}] for what the deciders delivered, from their packets (a writer that delivered nothing usable is skipped)."""
    rows = []
    for line in Path(slices_path).read_text(encoding='utf-8').splitlines():
        name, _, ids = line.partition('\t')
        try:
            delivery = read_packet(Path(directory, name.strip() + '.json'))
        except (OSError, ValueError):
            continue
        rows.append({'finding': ids.strip(), 'ops': delivery.get('ops') or []})
    return rows


def advisor_corrections(path):
    """The specialists' per-finding corrections from the collated worker packets, trimmed to what the reconciler needs."""
    try:
        collated = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [{'finding': f.get('id'), 'required_corrections': f.get('required_corrections') or [],
             'gaps': f.get('gaps') or [], 'risks': f.get('risks') or [], 'sources': f.get('sources') or []}
            for f in collated.get('findings') or [] if isinstance(f, dict)]


def write_reconcile_prompt(base_path, slices_path, directory, advisors_path, output):
    note = RECONCILE_NOTE % (json.dumps(decided_ops(slices_path, directory), ensure_ascii=False, indent=1),
                             json.dumps(advisor_corrections(advisors_path), ensure_ascii=False, indent=1))
    write_prompt(base_path, [], output, owns_fields=False, note=note)


def late_ops_of(model, path, applied):
    """(typed ops, notes) from the reconciler's packet: every op that clashes with an applied op, or is unusable, is dropped."""
    try:
        delivery = read_packet(path)
    except (OSError, ValueError):
        return [], ['the reconciler delivered nothing usable']
    kept, notes = [], []
    for flat in delivery.get('ops') or []:
        try:
            op = pm.typed_op(model, flat)
        except (pm.PlanError, ValueError, KeyError, TypeError) as error:
            notes.append('dropped %s: %s' % (json.dumps(flat)[:80], error))
            continue
        if pm.conflicts(model, [('applied', applied + kept), ('reconcile', [op])]):
            notes.append('dropped %s: an earlier edit already changes it' % json.dumps(flat)[:80])
            continue
        kept.append(op)
    return pm.namespace_steps(kept, 'reconcile'), notes


def ops_of(delivery, model, writer):
    """The typed ops in one writer's delivery; a writer that wrote a legacy `patch` instead is a conflict."""
    if delivery.get('patch'):
        raise Conflict('writer %s wrote a text patch, not ops' % writer)
    typed = []
    for flat in delivery.get('ops') or []:
        try:
            typed.append(pm.typed_op(model, flat))
        except (pm.PlanError, ValueError, KeyError) as error:
            typed.append({'op': 'invalid', 'flat': flat, 'why': str(error)})
    return pm.namespace_steps(typed, writer)


def op_group(writer_ops, model):
    """A group dict for a resolver: the conflicting (or invalid) ops and the current value of each id they touch."""
    where = pm.index(model)
    touched = []
    for _, op in writer_ops:
        flat = op.get('flat') or op
        for key in ('id', 'target', 'after', 'block', 'list', 'section'):
            value = flat.get(key)
            if isinstance(value, str) and value in where and value not in touched:
                touched.append(value)
    from worker_schemas import scoped_ids
    scope = scoped_ids(model, touched) if touched else finding_scope(model, [op.get('flat', op) for _, op in writer_ops])
    context = {}
    for key in scope:
        node = where[key][0]
        context[key] = {field: value for field, value in node.items() if field not in ('blocks', 'rows', 'items')}
    edits = []
    for writer, op in writer_ops:
        shown = copy.deepcopy(op.get('flat', op))
        shown.pop('_step_key', None)
        for fields in (shown, shown.get('new', {})):
            if 'depends_on' in fields and isinstance(fields['depends_on'], list):
                fields['depends_on'] = ['new:' + dep.rsplit(':', 1)[-1]
                                        if isinstance(dep, str) and dep.startswith('new:') else dep
                                        for dep in fields['depends_on']]
        edits.append({'writer': writer, 'op': shown, **({'problem': op['why']} if op.get('op') == 'invalid' else {})})
    return {'kind': 'ops', 'heading': ', '.join(touched[:4]) or '(the plan)',
            'context': json.dumps(context, ensure_ascii=False, indent=1),
            'edits': edits,
            'refs': [op for _, op in writer_ops]}


RESOLVE_PROMPT = '''Two or more writers revised the same approved plan at the same time and their edits cannot both apply (they
change the same field of the same id, or one of them names something that does not exist).
You reconcile only the edits below. Do not read files, run commands or investigate; everything you need is here.
Keep every requirement each edit serves, and write the edits that replace them. Edits elsewhere are merged by the driver.

Your whole answer is one JSON object, checked against a schema, shaped exactly like:

{"schema":"uncle.artifact/v1","kind":"%s","resolutions":[{"group":"<its id>","ops":[{"op":"set_fields","id":"B-1","fields":{"failure":"..."}}],"commands_replace":[]}]}

%s

- One entry for each group below, with its id. A group of kind `ops` is answered with `ops`; a group of kind `command` only with
  `commands_replace` (`old` copied exactly from the commands shown).
- An edit with a `problem` named an id or field that does not exist, or was malformed; write the edit it meant, against the
  ids shown under "Current values", or leave it out if the finding is already met.
- Change only what the group's edits were aimed at. Stop as soon as you have delivered the object.

%s
'''


def resolver_prompt(group, dispositions):
    why = sorted({(row.get('plan_change') or row.get('reason') or '').strip() for row in dispositions
                  if row.get('writer') in {e['writer'] for e in group['edits']}})
    body = ('## Group %s (kind %s)\n\nWhat the writers say they were doing: %s\n\n' % (
        group['id'], group['kind'], ' / '.join(w for w in why if w) or '(not stated)'))
    if group['kind'] == 'ops':
        body += 'Current values:\n```json\n%s\n```\n\nTheir edits:\n```json\n%s\n```\n' % (
            group['context'], json.dumps(group['edits'], ensure_ascii=False, indent=1))
    else:
        body += 'The verification commands:\n```\n%s\n```\n\nTheir edits:\n```json\n%s\n```\n' % (
            group['context'], json.dumps(group['edits'], ensure_ascii=False, indent=1))
    return RESOLVE_PROMPT % (RESOLUTION_OPS_KIND, OPS_RULES, body)


def apply_leniently(model, attributed):
    """(model, [(op, why, writers) that could not be applied]) for [(writers, op)]: each op alone, in order, so one
    bad op costs only itself and only the findings of the writers who wrote it."""
    dropped = []
    additions = []
    for writers, op in attributed:
        if op.get('op') == 'insert_step' or any(isinstance(dep, str) and dep.startswith('new:')
                                               for dep in op.get('depends_on', [])):
            additions.append((writers, op))
            continue
        try:
            model = pm.apply_ops(model, [op])
        except (pm.PlanError, ValueError, KeyError, TypeError) as error:
            dropped.append((op, str(error), writers))
    if additions:
        try:
            model = pm.apply_ops(model, [op for _, op in additions], normalize_new=False)
        except (pm.PlanError, ValueError, KeyError, TypeError):
            # Keep packet-local references atomic; one bad packet must not discard
            # unrelated new steps. Reapply the accepted prefix to preserve anchors.
            packets = {}
            for writers, op in additions:
                key = op.get('_step_key') or next(dep for dep in op['depends_on']
                                                 if isinstance(dep, str) and dep.startswith('new:'))
                packets.setdefault(key.rsplit(':', 1)[0], []).append((writers, op))
            accepted, revised = [], model
            for packet in packets.values():
                candidate = accepted + [op for _, op in packet]
                try:
                    revised = pm.apply_ops(model, candidate, normalize_new=False)
                    accepted = candidate
                except (pm.PlanError, ValueError, KeyError, TypeError) as error:
                    dropped.extend((op, str(error), writers) for writers, op in packet)
            model = revised
    return model, dropped


def owned_protected_paths(model, value):
    """Prefer inferred paths that an implementation step actually owns.

    A fallback protected-path list is only a recovery contract for older
    plans.  A stale prose reference must not turn into a protected file that
    no step can create.  Keep the historic broad fallback when a plan has no
    owned test/config path at all, so legacy plans remain usable.
    """
    candidates = [line.strip() for line in (value or '').splitlines() if line.strip()]
    owned = set()

    def visit(node):
        if isinstance(node, dict):
            values = node.get('owns')
            if isinstance(values, list):
                owned.update(item for item in values if isinstance(item, str))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(model)
    matching = [path for path in candidates if path in owned]
    return '\n'.join(matching or candidates)


def to_patch(old, new):
    """The section-level patch (`edit_sections` and `insert_sections`) that turns `old` into `new`."""
    old_by_id = {s['id']: s for s in old['sections']}
    patch = {'edit_sections': [], 'insert_sections': [], 'replace_text': []}
    previous = None
    for section in new['sections']:
        body = '\n\n'.join(pm.render_block(b) for b in section['blocks'])
        before = old_by_id.get(section['id'])
        if before is None:
            content = '## %s%s' % (section['heading'], '\n\n' + body if body else '')
            patch['insert_sections'].append({'content': content, 'after': '## ' + previous['heading']} if previous
                                            else {'content': content, 'position': 'start'})
        elif before != section:
            if before['heading'] != section['heading']:
                raise Conflict('section %s was renamed; ops do not rename sections' % section['id'])
            patch['edit_sections'].append({'heading': '## ' + section['heading'], 'content': body})
        previous = section
    gone = set(old_by_id) - {s['id'] for s in new['sections']}
    if gone:
        raise Conflict('sections %s were removed; ops do not remove sections' % ', '.join(sorted(gone)))
    return patch


def read_answers(directory, groups):
    """{group id: resolution row} from the resolutions-<group>.json files."""
    answers = {}
    for answer in sorted(Path(directory).glob('resolutions-*.json')):
        if re.search(r'-r[0-9]+\.json$', answer.name):
            continue  # Retained attempts are evidence, never current resolutions.
        try:
            for row in read_packet(answer).get('resolutions') or []:
                if isinstance(row, dict) and isinstance(row.get('group'), str):
                    answers[row['group']] = row
        except Conflict:
            pass
    return answers


def merge(plan_path, slices_path, directory, output, resolutions=None):
    plan = base.read_json(plan_path)
    model = plan_model_of(plan, plan_path)
    numbering = pm.renumber_enabled(plan, Path.cwd(), 'updated-change-plan' if CHANGE else 'updated-plan')
    errors, _ = pm.validate(model)
    if errors and not (numbering and pm.renumber_steps(model, Path.cwd()) is not model):
        raise Conflict('the base plan does not validate: %s' % '; '.join(errors))
    owners = []
    for line in Path(slices_path).read_text(encoding='utf-8').splitlines():
        name, _, ids = line.partition('\t')
        if name.strip():
            owners.append((name.strip(), [i for i in ids.split(',') if i]))
    if not owners:
        raise Conflict('no writers were planned')
    # The bounded updated-plan path is deliberately a one-round fan-out.  A
    # second model round per overlapping row destroys its latency guarantee.
    # Its contract is stable slice order: later writers may refine an earlier
    # edit, and every individual operation is applied leniently below.  The
    # legacy resolver path remains available when this is not set.
    fast_merge = os.environ.get('WORKFLOW_UPDATED_PLAN_FAST_MERGE') == '1'
    driver_contract = os.environ.get('WORKFLOW_UPDATED_PLAN_DRIVER_CONTRACT') == '1'
    dispositions, writer_ops, command_edits, paths = [], [], [], {}
    base_commands = (plan.get('verification_commands') or '').strip()
    try:
        base_paths = protected_paths(plan).strip()
    except ValueError:
        base_paths = ''
    for name, ids in owners:
        delivery = read_packet(Path(directory) / ('%s.json' % name))
        by_finding = {}
        for row in delivery.get('dispositions') or []:
            if isinstance(row, dict) and row.get('finding') in ids and row['finding'] not in by_finding:
                by_finding[row['finding']] = row
        missing = [i for i in ids if i not in by_finding]
        if missing:
            raise Conflict('writer %s left %s without a disposition' % (name, ', '.join(missing)))
        dispositions += [by_finding[i] for i in ids]
        writer_ops.append((name, ops_of(delivery, model, name)))
        for edit in delivery.get('commands_replace') or []:
            if (not isinstance(edit, dict) or not isinstance(edit.get('old'), str) or not edit['old']
                    or not isinstance(edit.get('new'), str)):
                raise Conflict('writer %s: commands_replace needs "old" and "new"' % name)
            command_edits.append((name, edit['old'], edit['new']))
        # Frozen verification paths are a driver-owned carry-forward field.
        # A writer represents them in a compact packet as a string and can
        # accidentally serialize a comma-delimited list, which is invalid for
        # the canonical artifact.  Never make that unchanged contract depend
        # on a worker in the fast path.
        if not driver_contract:
            value = delivery.get('protected_verification_paths')
            if isinstance(value, str) and value.strip() and value.strip() != base_paths:
                paths[value.strip()] = name
    if len(paths) > 1:
        raise Conflict('writers disagree on protected_verification_paths')
    command_edits, aside = base.place_commands(command_edits, base_commands)
    for name, count in aside.items():
        base.leave_out(dispositions, owners, {name}, count)
        print('updated-plan ops: writer %s: %d command edit(s) could not be placed and were left out' % (name, count), file=sys.stderr)

    # What cannot go through mechanically: ops that clash with another writer's, and ops that are invalid on their own.
    bad = [(w, op) for w, ops in writer_ops for op in ops if op.get('op') == 'invalid']
    valid = [(w, [op for op in ops if op.get('op') != 'invalid']) for w, ops in writer_ops]
    groups = [op_group(g, model) for g in pm.conflicts(model, valid)]
    groups += [op_group([item], model) for item in bad]
    groups += base.find_groups([], command_edits, plan.get('narrative') or '', base_commands)
    for number, group in enumerate(groups, 1):
        group['id'] = 'G%d' % number
    force_lenient = False
    if groups and fast_merge:
        print('updated-plan ops: %d overlapping/invalid edit group(s); applying stable writer-order merge without resolvers' % len(groups),
              file=sys.stderr)
        # Keep all non-invalid operations in their writer/slice order.  The
        # lenient application branch below applies the first edit, then lets a
        # later finding refine the same target.  This is deterministic and
        # avoids a slow, failure-prone resolver round.
        groups = []
        force_lenient = True
    answers = {}
    if groups:
        if resolutions is None:
            Path(directory, 'conflicts.json').write_text(json.dumps(groups, indent=2, default=str), encoding='utf-8')
            plan_changes = [dict(row, writer=name) for name, ids in owners
                            for row in read_packet(Path(directory) / ('%s.json' % name)).get('dispositions') or []
                            if isinstance(row, dict) and row.get('finding') in ids]
            Path(directory, 'prompts').mkdir(exist_ok=True)
            for group in groups:
                Path(directory, 'prompts', 'resolve-%s.md' % group['id']).write_text(resolver_prompt(group, plan_changes), encoding='utf-8')
                scope = list(json.loads(group['context'])) if group['kind'] == 'ops' else []
                Path(directory, 'prompts', 'resolve-%s.scope.json' % group['id']).write_text(json.dumps(scope) + '\n', encoding='utf-8')
            raise NeedsResolution(groups)
        answers = read_answers(resolutions, groups)
        missing = [g['id'] for g in groups if g['id'] not in answers]
        if missing:
            raise Conflict('the resolver did not answer %s' % ', '.join(missing))

    clashing = {json.dumps(op, sort_keys=True) for g in groups if g['kind'] == 'ops' for op in g['refs']}
    final_ops, seen_ops = [], {}
    for writer, ops in valid:
        for op in ops:
            sig = json.dumps(op, sort_keys=True)
            if sig in seen_ops:                                    # the same op from two writers is one op
                seen_ops[sig].add(writer)
            elif sig not in clashing:
                seen_ops[sig] = {writer}
                final_ops.append((seen_ops[sig], op))
    dropped_commands = {base.op_sig(ref) for g in groups if g['kind'] == 'command' for ref in g['refs']}
    command_edits = [e for e in command_edits if base.op_sig(e) not in dropped_commands]
    for group in groups:
        row = answers.get(group['id'], {})
        if group['kind'] == 'ops':
            resolved = []
            for flat in row.get('ops') or []:
                try:
                    resolved.append(pm.typed_op(model, flat))
                except (pm.PlanError, ValueError, KeyError) as error:
                    print('updated-plan ops: group %s: %s' % (group['id'], error), file=sys.stderr)
                    base.leave_out(dispositions, owners, {e['writer'] for e in group['edits']}, 1)
            final_ops.extend(({e['writer'] for e in group['edits']}, op)
                             for op in pm.namespace_steps(resolved, 'resolver-' + group['id']))
        for edit in row.get('commands_replace') or []:
            if isinstance(edit, dict) and isinstance(edit.get('old'), str) and isinstance(edit.get('new'), str):
                command_edits.append(('resolver-' + group['id'], edit['old'], edit['new']))
    late_path = os.environ.get('UNCLE_LATE_OPS')
    if late_path and Path(late_path).is_file():
        late, notes = late_ops_of(model, late_path, [op for _, op in final_ops])
        for note in notes:
            print('updated-plan ops: reconcile: %s' % note, file=sys.stderr)
        final_ops += [({'reconcile'}, op) for op in late]
        if late:
            print('updated-plan ops: reconcile added %d edit(s)' % len(late), file=sys.stderr)
    if force_lenient or groups or late_path:
        new_model, dropped = apply_leniently(model, final_ops)
        for op, why, writers in dropped:
            print('updated-plan ops: left out %s: %s' % (json.dumps(op)[:100], why), file=sys.stderr)
            if 'already exists' not in why:      # a duplicate insert lost nothing: another writer's row is in the plan
                base.leave_out(dispositions, owners, writers, 1)
    else:
        new_model = pm.apply_ops(model, [op for _, op in final_ops])
    has_new_steps = any(op.get('op') == 'insert_step' for _, op in final_ops)
    if numbering or has_new_steps:
        new_model = pm.renumber_steps(new_model, Path.cwd(), assign_ids=has_new_steps)
    errors, _ = pm.validate(new_model)
    if errors:
        raise Conflict('the revised plan does not validate: %s' % '; '.join(errors))
    commands = base.merged_commands(base_commands, command_edits)
    if driver_contract:
        paths = {}
    if not CHANGE and not (next(iter(paths), base_paths) or '').strip():
        # Neither the base plan nor a writer named any (calculator-local: a local model's plan had none, the whole ops result was
        # thrown away, and the one-call fallback failed on a text patch).  The plan's own test files and configs are what it means.
        # This is the post-merge contract.  Deriving from the base narrative
        # resurrects paths a compact writer has just renamed, leaving stale
        # protected files with no owning implementation step.
        derived = derive_protected_paths(pm.render(new_model), commands)
        if not derived:
            raise Conflict('no writer supplied protected_verification_paths, and the plan names no test files to protect')
        paths = {owned_protected_paths(new_model, derived): 'driver'}
        print('updated-plan ops: no protected_verification_paths anywhere; derived %d from the plan\'s test files' % len(derived.splitlines()),
              file=sys.stderr)
    patch = to_patch(model, new_model)
    apply_patch(plan.get('narrative') or pm.render(model), patch)     # a patch that does not apply is a conflict
    contract_paths = next(iter(paths), base_paths)
    if not CHANGE and driver_contract:
        contract_paths = base_paths
        if not contract_paths.strip():
            # Keep the published driver-owned field aligned with the merged
            # model above, never with the pre-review narrative.
            contract_paths = owned_protected_paths(
                new_model, derive_protected_paths(pm.render(new_model), commands))
    if CHANGE:
        result = {'schema': 'uncle.artifact/v1', 'kind': 'change-plan', 'dispositions': dispositions, 'patch': patch}
    else:
        result = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'dispositions': dispositions, 'patch': patch,
                  'verification_commands': commands, 'protected_verification_paths': contract_paths}
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def check_resolutions(plan_path, directory):
    """{group id: why its answer cannot be applied}, judged one group at a time against the base plan."""
    plan = base.read_json(plan_path)
    model = plan_model_of(plan, plan_path)
    commands = (plan.get('verification_commands') or '').strip()
    groups = json.loads(Path(directory, 'conflicts.json').read_text(encoding='utf-8'))
    answers = read_answers(directory, groups)
    bad = {}
    for group in groups:
        row = answers.get(group['id'])
        if row is None:
            bad[group['id']] = 'there was no valid answer for this group'
            continue
        if group['kind'] == 'ops':
            try:
                pm.apply_ops(model, [pm.typed_op(model, flat) for flat in row.get('ops') or []])
            except (pm.PlanError, ValueError, KeyError, TypeError) as error:
                bad[group['id']] = str(error)
                Path(directory, 'prompts', 'resolve-%s.validator-rejected' % group['id']).write_text(str(error))
        for edit in row.get('commands_replace') or []:
            if isinstance(edit, dict) and commands.count(edit.get('old') or '\0') != 1:
                bad[group['id']] = 'command text %r is not in the verification commands exactly once' % (edit.get('old') or '')[:120]
                Path(directory, 'prompts', 'resolve-%s.validator-rejected' % group['id']).write_text(bad[group['id']])
    for gid, why in bad.items():
        original = Path(directory, 'prompts', 'resolve-%s.md' % gid).read_text(encoding='utf-8')
        Path(directory, 'prompts', 'resolve-%s.retry.md' % gid).write_text(
            original + '\n\n## Your previous answer was rejected\n\n%s.\nAnswer again for this group, naming only ids shown above.\n' % why,
            encoding='utf-8')
    return bad


def implementation_steps(model):
    steps = pm.steps_of(model)
    for section in model['sections']:
        for block in section['blocks']:
            if block['kind'] == 'list' and re.search(r'implementation (?:order|sequence|steps)', section['heading'], re.I):
                for item in block['items']:
                    match = re.search(r'Owns:\s*([^\n]+)', item['text'])
                    if item.get('number') and match:
                        steps.append(dict(item, owns=re.findall(r'`([^`]+)`', match[1]), _inline=True))
    return steps


def ownership_edit(step, paths):
    if step.get('_inline'):
        text = re.sub(r'(Owns:\s*)[^\n]+', lambda m: m[1] + ', '.join('`%s`' % p for p in paths), step['text'], count=1)
        return {'op': 'set_text', 'id': step['id'], 'text': text}
    return {'op': 'set_step', 'id': step['id'], 'fields': {'owns': ', '.join(paths)}}


def ownership_ops(plan, model, gaps):
    """Only explicit accepted assignments or a uniquely owned source/test pair are automatic."""
    steps = implementation_steps(model)
    additions = {}
    unresolved = []
    for path in gaps:
        named = set()
        for disposition in plan.get('dispositions') or []:
            if disposition.get('disposition') not in ('Accepted', 'Partially accepted'):
                continue
            change = disposition.get('plan_change') or ''
            if not re.search(r'(?<![\w./-])' + re.escape(path) + r'(?![\w./-])', change):
                continue
            named.update(int(n) for n in re.findall(r'\bstep\s+(\d+)\b', change, re.I))
        candidates = [step for step in steps if step['number'] in named]
        if not named:
            # A test basename must pair with exactly one source path and one owner.
            test = re.fullmatch(r'(.+)\.(?:test|spec)\.(\w+)', Path(path).name)
            pairs = [(step, owned) for step in steps for owned in step['owns']
                     if test and Path(owned).name == test[1] + '.' + test[2]
                     and not any(p in ('tests', 'test', '__tests__') for p in Path(owned).parts)]
            candidates = [pairs[0][0]] if len(pairs) == 1 else []
        if len(candidates) != 1 or len(named) > 1:
            unresolved.append(path)
            continue
        step = candidates[0]
        additions.setdefault(step['id'], list(step['owns'])).append(path)
    return [ownership_edit(next(s for s in steps if s['id'] == sid), paths)
            for sid, paths in additions.items()], unresolved


def repair_plan(plan, model, operations):
    plan, model = dict(plan), copy.deepcopy(model)
    headings = {step['id']: step for step in pm.heading_steps(plan.get('narrative') or '') if step.get('_heading')}
    ordinary = []
    for operation in operations:
        step = headings.get(operation.get('id'))
        if step is None:
            ordinary.append(operation)
            continue
        if operation.get('op') != 'set_step' or set(operation.get('fields', {})) != {'owns'}:
            raise Conflict('heading-step repair may only add owns paths')
        paths = pm.split_list(operation['fields']['owns'])
        if any(not pm.valid_path(path) for path in paths):
            raise Conflict('heading-step repair needs repository-relative ownership paths')
        old = step['_heading_line']
        owns = re.search(r'\bOwns\s*:\s*(.*?)(?=\s*(?:[—–-]\s*)?Depends on\s*:|$)', old, re.I)
        if owns:
            new = old[:owns.start(1)] + ', '.join('`%s`' % path for path in paths) + old[owns.end(1):]
        else:
            additions = [path for path in paths if path not in step['owns']]
            new = old + ' — Owns: ' + ', '.join('`%s`' % path for path in additions)
        pattern = re.compile('^' + re.escape(old) + '$', re.M)
        if len(pattern.findall(plan['narrative'])) != 1:
            raise Conflict('heading-step repair cannot uniquely locate ' + step['label'])
        plan['narrative'] = pattern.sub(lambda _: new, plan['narrative'], count=1)
        for section in model['sections']:
            if section['heading'] == step['_heading']:
                section['heading'] = re.sub(r'^#+\s+', '', new)
            for block in section['blocks']:
                if 'text' in block:
                    block['text'] = pattern.sub(lambda _: new, block['text'])
        model['intro'] = pattern.sub(lambda _: new, model.get('intro', ''))
        # Imported heading steps now have typed records as well as source anchors.
        # Keep those records current without re-rendering the legacy approval view.
        for record in implementation_steps(model):
            if record['id'] == step['id']:
                record['owns'] = paths
    typed = [pm.typed_op(model, operation) for operation in ordinary]
    revised = pm.apply_ops(model, typed)
    result = dict(plan, narrative=apply_patch(plan['narrative'], to_patch(model, revised)))
    # Stale embedded model records must never shadow repaired text.
    result.pop('sections', None)
    return result, revised


def structure_schema(model, ids, ownership):
    from worker_schemas import edit_ops_packet, _object, _text
    schema = edit_ops_packet(ids, model=model)
    schema['properties']['protected_verification_paths'] = {'type': 'string'}
    schema['properties']['dispositions']['maxItems'] = 0
    if ownership:
        variants = []
        candidates = [step for step in implementation_steps(model) if step['id'] in ids]
        for inline in (False, True):
            keys = [step['id'] for step in candidates if bool(step.get('_inline')) == inline]
            if keys:
                field = 'text' if inline else 'fields'
                value = _text(12000, 0) if inline else _object({
                    'owns': {'type': 'array', 'maxItems': 150, 'items': _text(4000)}}, ['owns'])
                variants.append(_object({'op': {'const': 'set_text' if inline else 'set_step'},
                                         'id': {'type': 'string', 'enum': keys}, field: value}, ['op', 'id', field]))
        schema['properties']['ops']['items'] = {'anyOf': variants} if variants else {}
        schema['properties']['ops']['maxItems'] = 120 if variants else 0
        schema['properties']['commands_replace']['maxItems'] = 0
    return schema


def prepare_structure_repair(plan_path, project, directory, problem):
    from plan_ownership_gap import unowned_protected_paths
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plan = base.read_json(plan_path)
    model = plan_model_of(plan, plan_path)
    # A publication rejection has not written a human-facing plan yet. Inspect
    # this exact candidate privately rather than a stale published Markdown view.
    view = directory / 'candidate-view.md'
    view.write_text(plan.get('narrative') or pm.render(model), encoding='utf-8')
    protected = (plan.get('protected_verification_paths') or '').splitlines()
    gaps = unowned_protected_paths(view, project, protected)
    operations, unresolved = ownership_ops(plan, model, gaps)
    if operations:
        plan, model = repair_plan(plan, model, operations)
    (directory / 'automatic-ops.json').write_text(json.dumps(operations, indent=2) + '\n')
    (directory / 'base.json').write_text(json.dumps(plan, indent=2) + '\n')
    (directory / 'model.json').write_text(json.dumps(model) + '\n')
    ownership = bool(gaps) or 'owning implementation step' in problem
    if ownership and not unresolved:
        (directory / 'repaired.json').write_text(json.dumps(plan, indent=2) + '\n')
        return 0
    # Include step ids and their current ownership, plus only relevant sections for
    # other structural errors. The full plan never becomes a requested output.
    sections = [section for section in model['sections'] if any(b['kind'] == 'steps' for b in section['blocks']) or re.search(r'implementation order', section['heading'], re.I)
                or (not ownership and re.search(r'verif|protect|test', section['heading'], re.I))]
    scope = dict(model, sections=sections)
    candidates = implementation_steps(model)
    ids = [step['id'] for step in candidates] if ownership else list(pm.index(scope))
    (directory / 'scope.json').write_text(json.dumps({'ids': ids, 'gaps': unresolved,
                                                    'ownership': ownership, 'problem': problem}) + '\n')
    (directory / 'schema.json').write_text(json.dumps(structure_schema(model, ids, ownership), separators=(',', ':')) + '\n')
    prompt = ('Repair only the structural defect below using edit ops. Do not read files, run commands or investigate. '
              'Never return the complete plan or a narrative. All current step ownership and affected sections follow. '
              'Return one JSON packet: ' + EXAMPLE % (EDIT_OPS_KIND, '') + '\n'
              'Write dispositions: []; existing dispositions are retained. For an ownership gap use only set_step '
              'owns edits (set_text for an inline Owns list item) that add the missing paths, or remove only an unowned path '
              'from protected_verification_paths if no step will create it. Preserve existing ownership and all other protected paths. '
              'For other structural defects change only the supplied ids, commands_replace, or protected_verification_paths.\n\n'
              + OPS_RULES + '\n\nDefect: ' + problem + '\nUnowned paths: ' + json.dumps(unresolved) +
              '\nCurrent sections and steps:\n' + json.dumps(scope, ensure_ascii=False) +
              '\nCandidate owners:\n' + json.dumps(candidates, ensure_ascii=False) +
              '\nVerification commands:\n' + plan.get('verification_commands', '') +
              '\nProtected paths:\n' + plan.get('protected_verification_paths', ''))
    (directory / 'prompt.md').write_text(prompt, encoding='utf-8')
    return 3


def apply_structure_repair(directory, project):
    from plan_ownership_gap import unowned_protected_paths, normalized_path
    import artifact_json
    import tempfile
    directory = Path(directory)
    plan = base.read_json(directory / 'base.json')
    model = base.read_json(directory / 'model.json')
    scope = base.read_json(directory / 'scope.json')
    delivery = first_packet((directory / 'packet.json').read_text())
    from http_agent import conforms
    from worker_schemas import edit_ops_packet
    legacy = edit_ops_packet()
    legacy['properties']['protected_verification_paths'] = {'type': 'string'}
    conforms(delivery, {'anyOf': [structure_schema(model, scope['ids'], scope['ownership']), legacy]})
    if delivery.get('dispositions'):
        raise Conflict('structural repair must preserve existing dispositions')
    operations = delivery.get('ops') or []
    for operation in operations:
        target = operation.get('id') or operation.get('target')
        if target not in scope['ids']:
            raise Conflict('structural repair names an id outside its scope: %s' % target)
        if scope['ownership']:
            step = next((s for s in implementation_steps(model) if s['id'] == target), None)
            if step is None:
                raise Conflict('ownership repair must name an implementation step')
            if operation.get('op') == 'set_step' and set(operation.get('fields', {})) == {'owns'}:
                if set(operation) != {'op', 'id', 'fields'}:
                    raise Conflict('ownership repair changed unrelated operation fields')
                after = pm.split_list(operation['fields']['owns']) if step.get('_heading') else pm.typed_op(model, operation)['owns']
            elif operation.get('op') == 'set_text' and step.get('_inline'):
                match = re.search(r'Owns:\s*([^\n]+)', operation.get('text', ''))
                after = re.findall(r'`([^`]+)`', match[1]) if match else []
            else:
                raise Conflict('ownership repair may only add owns paths')
            if step.get('_inline') and operation != ownership_edit(step, after):
                raise Conflict('ownership repair changed unrelated step text')
            before = {normalized_path(path) for path in step['owns']}
            after = [normalized_path(path) for path in after]
            if (not before <= set(after) or not (set(after) - before) <= {normalized_path(path) for path in scope['gaps']}):
                raise Conflict('ownership repair changed unrelated paths')
            operation.clear()
            operation.update(ownership_edit(step, after))
    result, _ = repair_plan(plan, model, operations)
    if scope['ownership']:
        before = {normalized_path(path) for path in pm.protected_paths(plan.get('protected_verification_paths', ''))}
        after = {normalized_path(path) for path in pm.protected_paths(delivery.get(
            'protected_verification_paths', plan.get('protected_verification_paths', '')))}
        if delivery.get('commands_replace') or not after <= before or not before - after <= set(scope['gaps']):
            raise Conflict('ownership repair changed unrelated verification paths or commands')
    commands = plan.get('verification_commands', '')
    for edit in delivery.get('commands_replace') or []:
        old, new = edit['old'], edit['new']
        if old == '' and commands == '':
            commands = new
        elif not old or commands.count(old) != 1:
            raise Conflict('structural command replacement is not unique')
        else:
            commands = commands.replace(old, new, 1)
    if plan['kind'] == 'plan':
        result['verification_commands'] = commands
        result['protected_verification_paths'] = delivery.get('protected_verification_paths', plan.get('protected_verification_paths', ''))
        rendered = artifact_json.render_plan(result, protected=True)
    else:
        rendered = artifact_json.render_change_plan(result, require_dispositions=True)
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp) / 'PLAN.md'
        view.write_text(rendered)
        if unowned_protected_paths(view, project, (result.get('protected_verification_paths') or '').splitlines()):
            raise Conflict('structural repair left unowned protected paths')
    (directory / 'repaired.json').write_text(json.dumps(result, indent=2) + '\n')


def main(argv):
    try:
        command, rest = argv[0], argv[1:]
        if command == 'slices' and len(rest) == 1:
            for name, ids in slices(base.finding_ids(rest[0])):
                print('%s\t%s' % (name, ','.join(ids)))
        elif command == 'resplit':
            return base.main(argv)
        elif command == 'budget' and len(rest) in (1, 2):
            print('%s %s' % writer_budget([i for i in rest[0].split(',') if i], *rest[1:]))
        elif command == 'resolver-budget' and len(rest) == 2:
            print('%s %s' % resolver_budget(*rest))
        elif command == 'resolver-fallback-mode' and not rest:
            from self_hosted_http import option as http_option
            print('on' if http_option('writer-schema-first', 'on') in ('off', '0', 'false') else 'off')
        elif command == 'capture' and len(rest) == 1:
            capture_packet(rest[0])
        elif command == 'check-writer' and len(rest) == 3:
            try:
                check_writer(*rest)
            except (pm.PlanError, ValueError, KeyError, TypeError) as error:
                print(str(error), file=sys.stderr)
                return 5
        elif command == 'prompt' and len(rest) in (3, 4):
            write_prompt(rest[0], [i for i in rest[1].split(',') if i], rest[2], owns_fields=len(rest) == 4)
        elif command == 'repair-prepare' and len(rest) == 4:
            return prepare_structure_repair(*rest)
        elif command == 'repair-apply' and len(rest) == 2:
            apply_structure_repair(*rest)
        elif command == 'reconcile' and len(rest) == 5:
            write_reconcile_prompt(*rest)
        elif command == 'check' and len(rest) == 2:
            bad = check_resolutions(*rest)
            for gid, why in sorted(bad.items()):
                print(gid)
                print('updated-plan ops: group %s: %s' % (gid, why), file=sys.stderr)
            return 5 if bad else 0
        elif command == 'merge' and len(rest) in (4, 5):
            merge(*rest)
        else:
            raise SystemExit(__doc__)
    except NeedsResolution as overlap:
        print('updated-plan ops: %s; they need one resolver call' % overlap, file=sys.stderr)
        return 3
    except (Conflict, pm.PlanError, ValueError, OSError) as error:
        print('updated-plan ops: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
