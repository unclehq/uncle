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
You name an id that exists. You never quote text and never name a heading. Every value in an op is a string;
a field that holds a list (requirements, files, owns, depends_on) is written as one string, items separated by commas.

- `{"op":"set_fields","id":"B-1","fields":{"failure":"..."}}` changes only the named fields of the row `id`. The
  field names are the keys of that row in the model.
- `{"op":"set_text","id":"s1.2","text":"..."}` replaces the text of a `prose` block or a list item.
- `{"op":"set_step","id":"step-3","fields":{"title":"...","text":"...","owns":"a.js, b.js","depends_on":"1, 2"}}`
  changes only the fields named.
- `{"op":"insert_row","target":"<id of a rows block>","after":"B-3","new":{"id":"B-9", ...fields}}` adds a row after
  the row `after` ("" for first). The new row's id is new and unused.
- `{"op":"insert_item","target":"<id of a list or steps block>","after":"<item id or empty>","new":{...}}` adds a list item
  (`{"text":"..."}`) or a step (`{"id":"step-N","number":"N","title":"...","text":"...","owns":"...","depends_on":"..."}`).
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


def plan_model_of(plan, path=None):
    """The plan's model: the authored sidecar beside its file when that agrees with the narrative, else the narrative imported."""
    return pm.load_model(path) if path else pm.model_of(plan)


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
    text = PLAN_JSON.sub(lambda _: '## Plan model (JSON)\n\nEvery `id` below is one you may name.\n```json\n%s\n```\n'
                         % json.dumps({k: v for k, v in model.items()}, ensure_ascii=False, separators=(',', ':')), text)
    notes = '' if CHANGE else (base.FIELDS_OWNER if owns_fields else base.FIELDS_OTHER) + base.COMMANDS_NOTE
    if note is None:
        note = SLICE_NOTE % (', '.join(ids), notes)
        if 'Collated specialist corrections' not in text:      # deciding writers: nobody has reviewed the findings first
            note += DECIDE_NOTE
    Path(output).write_text(text + note, encoding='utf-8')


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
            delivery = json.loads(Path(directory, name.strip() + '.json').read_text(encoding='utf-8'))
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
        delivery = json.loads(Path(path).read_text(encoding='utf-8'))
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
    return kept, notes


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
    return typed


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
    return {'kind': 'ops', 'heading': ', '.join(touched[:4]) or '(the plan)',
            'context': json.dumps({k: where[k][0] for k in touched}, ensure_ascii=False, indent=1),
            'edits': [{'writer': w, 'op': op.get('flat', op), **({'problem': op['why']} if op.get('op') == 'invalid' else {})}
                      for w, op in writer_ops],
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
    for writers, op in attributed:
        try:
            model = pm.apply_ops(model, [op])
        except (pm.PlanError, ValueError, KeyError, TypeError) as error:
            dropped.append((op, str(error), writers))
    return model, dropped


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
        try:
            for row in base.read_json(answer).get('resolutions') or []:
                if isinstance(row, dict) and isinstance(row.get('group'), str):
                    answers[row['group']] = row
        except Conflict:
            pass
    return answers


def merge(plan_path, slices_path, directory, output, resolutions=None):
    plan = base.read_json(plan_path)
    model = plan_model_of(plan, plan_path)
    errors, _ = pm.validate(model)
    if errors:
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
        delivery = base.read_json(Path(directory) / ('%s.json' % name))
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
                            for row in base.read_json(Path(directory) / ('%s.json' % name)).get('dispositions') or []
                            if isinstance(row, dict) and row.get('finding') in ids]
            Path(directory, 'prompts').mkdir(exist_ok=True)
            for group in groups:
                Path(directory, 'prompts', 'resolve-%s.md' % group['id']).write_text(resolver_prompt(group, plan_changes), encoding='utf-8')
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
            for flat in row.get('ops') or []:
                try:
                    final_ops.append(({e['writer'] for e in group['edits']}, pm.typed_op(model, flat)))
                except (pm.PlanError, ValueError, KeyError) as error:
                    print('updated-plan ops: group %s: %s' % (group['id'], error), file=sys.stderr)
                    base.leave_out(dispositions, owners, {e['writer'] for e in group['edits']}, 1)
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
    errors, _ = pm.validate(new_model)
    if errors:
        raise Conflict('the revised plan does not validate: %s' % '; '.join(errors))
    commands = base.merged_commands(base_commands, command_edits)
    if driver_contract:
        paths = {}
    if not CHANGE and not (next(iter(paths), base_paths) or '').strip():
        # Neither the base plan nor a writer named any (calculator-local: a local model's plan had none, the whole ops result was
        # thrown away, and the one-call fallback failed on a text patch).  The plan's own test files and configs are what it means.
        derived = derive_protected_paths(plan.get('narrative') or pm.render(new_model), commands)
        if not derived:
            raise Conflict('no writer supplied protected_verification_paths, and the plan names no test files to protect')
        paths = {derived: 'driver'}
        print('updated-plan ops: no protected_verification_paths anywhere; derived %d from the plan\'s test files' % len(derived.splitlines()),
              file=sys.stderr)
    patch = to_patch(model, new_model)
    apply_patch(plan.get('narrative') or pm.render(model), patch)     # a patch that does not apply is a conflict
    contract_paths = next(iter(paths), base_paths)
    if not CHANGE and driver_contract:
        contract_paths = base_paths
        if not contract_paths.strip():
            contract_paths = derive_protected_paths(plan.get('narrative') or pm.render(new_model), commands)
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
        for edit in row.get('commands_replace') or []:
            if isinstance(edit, dict) and commands.count(edit.get('old') or '\0') != 1:
                bad[group['id']] = 'command text %r is not in the verification commands exactly once' % (edit.get('old') or '')[:120]
    for gid, why in bad.items():
        original = Path(directory, 'prompts', 'resolve-%s.md' % gid).read_text(encoding='utf-8')
        Path(directory, 'prompts', 'resolve-%s.retry.md' % gid).write_text(
            original + '\n\n## Your previous answer was rejected\n\n%s.\nAnswer again for this group, naming only ids shown above.\n' % why,
            encoding='utf-8')
    return bad


def main(argv):
    try:
        command, rest = argv[0], argv[1:]
        if command in ('slices', 'resplit'):
            return base.main(argv)
        if command == 'prompt' and len(rest) in (3, 4):
            write_prompt(rest[0], [i for i in rest[1].split(',') if i], rest[2], owns_fields=len(rest) == 4)
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
