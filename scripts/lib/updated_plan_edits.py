#!/usr/bin/env python3
"""Resolve the adversarial findings in parallel and merge the edits mechanically.

The single synthesis call decides every disposition and writes every edit; its time is mostly
deliberation, so it grows with the number of findings.  Here each writer owns a consecutive run
of findings, reads the same sealed prompt (so the shared prefix caches), and returns the
dispositions and patch for its own findings.  The driver merges the pieces; it never asks a model
to reconcile everything.  Edits that overlap (two writers changing the same text or section) go to one
short resolver call that sees only those edits and the text around them; every other edit is still
merged mechanically.  Anything else -- a finding left undecided, a patch that does not apply, a
resolution that still overlaps -- is an error, and the caller runs the single synthesis call instead.  A merge that succeeds is exactly what that call would have
published: dispositions plus a patch against the base plan.

    updated_plan_edits.py slices REVIEW.json            one `n<TAB>ids` line per writer
    updated_plan_edits.py prompt BASE_PROMPT IDS OUT [owner]  the sealed prompt plus this writer's slice
    updated_plan_edits.py merge PLAN.json SLICES.tsv DIR OUTPUT [RESOLUTIONS.json]
    updated_plan_edits.py check PLAN.json DIR     (exit 5, with the group ids on stdout, when a resolver answer cannot be applied)
    (exit 3: edits overlap; DIR/prompts/resolve-<group>.md are the resolvers' prompts -- rerun with RESOLUTIONS.json, or a directory of resolutions-<group>.json)
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_patch import apply_patch, split_sections
from updated_plan_fast_path import protected_paths
from updated_plan_slices import finding_ids
from worker_schemas import EDIT_KIND, RESOLUTION_KIND

SLICE = 4       # findings per writer: the slowest writer sets the wall time, so keep them small
MAX_WRITERS = 8
MIN_FINDINGS = 4  # fewer than this and one call is already quick; splitting it only adds a merge


class Conflict(ValueError):
    pass


def slices(ids, size=SLICE):
    if len(ids) < MIN_FINDINGS:
        return []
    size = max(1, size)
    count = min(MAX_WRITERS, -(-len(ids) // size))
    per = -(-len(ids) // count)
    return [(str(n + 1), ids[n * per:(n + 1) * per]) for n in range(count) if ids[n * per:(n + 1) * per]]


SLICE_NOTE = '''

## Your slice (binding; overrides the instructions above where they differ)

Other writers are resolving the remaining findings at the same time, from this same base plan.
Their patches are merged mechanically with yours.

- You own exactly these findings: %s. The other rows above are context only.
- Write one disposition for each of your findings and none for any other.
- Edit only the text your findings require. Never rewrite text another finding obviously
  owns; two writers changing the same section or the same text is rejected.
- Use `replace_text` for every change that is not a whole section, and leave `edit_sections`
  for a section only your findings change.
%s'''

FIELDS_OWNER = '''- You also own `protected_verification_paths`: include it, complete, even when unchanged (the plan
  may not list protected paths yet; then choose them from its test sections as the instructions
  above say). Change `verification_commands` only through `commands_replace`, below.
'''
FIELDS_OTHER = '''- Do not write `protected_verification_paths`; the first writer owns it.
'''
COMMANDS_NOTE = '''- `verification_commands` is not part of your packet (the schema has no such field), whatever the
  instructions above say. To change a command, add `"commands_replace":
  [{"old": "<text copied exactly from the base commands, unique within them>", "new": "<replacement>"}]`
  at the top level of your reply. Writers' command edits are merged line by line; changing the
  same text differently is rejected.
'''


WRITER_EXAMPLE = (
    '{"schema":"uncle.artifact/v1","kind":"%s","dispositions":[{"finding":"AR-001","disposition":"Accepted",'
    '"reason":"...","plan_change":"..."}],"patch":{"replace_text":[{"heading":"...","old":"...","new":"..."}],'
    '"edit_sections":[],"insert_sections":[]},"commands_replace":[]%s}')
EXAMPLE_BLOCK = re.compile(r'```json\n\{"schema":"uncle\.artifact/v1","kind":"plan".*?\n```', re.S)


def write_prompt(base, ids, output, owns_fields=False):
    """The sealed synthesis prompt, re-pointed at this writer's packet.

    The base prompt's example is the whole-plan reply (kind `plan`); the writer's reply is its own packet
    kind, and a prompt that names two kinds gives a schema-enforcing runner no kind to hold the model to."""
    text = Path(base).read_text(encoding='utf-8')
    example = WRITER_EXAMPLE % (EDIT_KIND, ',"protected_verification_paths":"..."' if owns_fields else '')
    text = EXAMPLE_BLOCK.sub(lambda _: '```json\n' + example + '\n```', text)
    note = SLICE_NOTE % (', '.join(ids), (FIELDS_OWNER if owns_fields else FIELDS_OTHER) + COMMANDS_NOTE)
    Path(output).write_text(text + note, encoding='utf-8')


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise Conflict('%s: not valid JSON: %s' % (path, error))
    if not isinstance(value, dict):
        raise Conflict('%s: expected a JSON object' % path)
    return value


def spans(body, old, every):
    found, start = [], body.find(old)
    while start >= 0:
        found.append((start, start + len(old)))
        if not every:
            break
        start = body.find(old, start + len(old))
    return found


def merged_patch(parts, narrative):
    """Concatenate every writer's patch, refusing anything that touches the same place twice."""
    _, sections = split_sections(narrative)
    bodies = {section['heading']: section['body'] for section in sections}
    merged = {'replace_text': [], 'edit_sections': [], 'insert_sections': []}
    whole, taken = {}, {}
    seen_insert, identical = {}, set()
    for writer, patch in parts:
        if not isinstance(patch, dict):
            raise Conflict('writer %s: patch must be an object' % writer)
        for edit in patch.get('edit_sections') or []:
            heading = (edit.get('heading') or '').strip() if isinstance(edit, dict) else ''
            if heading in whole:
                raise Conflict('section %r was rewritten by writers %s and %s' % (heading, whole[heading], writer))
            whole[heading] = writer
            merged['edit_sections'].append(edit)
        for edit in patch.get('replace_text') or []:
            if not isinstance(edit, dict) or not isinstance(edit.get('old'), str) or not edit['old']:
                raise Conflict('writer %s: replace_text needs a non-empty "old"' % writer)
            heading = (edit.get('heading') or '').strip()
            if heading not in bodies:
                raise Conflict('writer %s: no section %r' % (writer, heading))
            signature = (heading, edit['old'], edit.get('new'), bool(edit.get('all')))
            if signature in identical:
                continue        # two writers made the very same edit: it is one edit
            identical.add(signature)
            found = spans(bodies[heading], edit['old'], bool(edit.get('all')))
            if not found:
                raise Conflict('writer %s: %r is not in section %r' % (writer, edit['old'][:60], heading))
            for other_writer, start, end in taken.get(heading, []):
                for begin, finish in found:
                    if begin < end and start < finish:
                        raise Conflict('writers %s and %s both change the same text in section %r'
                                       % (other_writer, writer, heading))
            taken.setdefault(heading, []).extend((writer, begin, finish) for begin, finish in found)
            merged['replace_text'].append(edit)
        for insert in patch.get('insert_sections') or []:
            content = insert.get('content') if isinstance(insert, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise Conflict('writer %s: insert_sections needs "content"' % writer)
            heading = content.lstrip('\n').split('\n', 1)[0].strip()
            if heading in seen_insert:
                raise Conflict('writers %s and %s both insert %r' % (seen_insert[heading], writer, heading))
            seen_insert[heading] = writer
            merged['insert_sections'].append(insert)
    for heading, writer in whole.items():
        if heading in taken:
            raise Conflict('section %r is rewritten by writer %s and also edited line by line' % (heading, writer))
    return merged


def merged_commands(base, edits_):
    """The base commands with every writer's line edits applied; the same edit twice is one edit."""
    chosen, spans_taken = [], []
    for writer, old, new in edits_:
        if (old, new) in [(o, n) for _, o, n, _ in chosen]:
            continue
        if base.count(old) != 1:
            raise Conflict('writer %s: command text %r occurs %d times in the base commands'
                           % (writer, old[:60], base.count(old)))
        start = base.find(old)
        for other, begin, end in spans_taken:
            if start < end and begin < start + len(old):
                raise Conflict('writers %s and %s both change the same command text' % (other, writer))
        spans_taken.append((writer, start, start + len(old)))
        chosen.append((writer, old, new, start))
    result = base
    for _, old, new, start in sorted(chosen, key=lambda row: -row[3]):
        result = result[:start] + new + result[start + len(old):]
    return result


class NeedsResolution(Exception):
    """Writers' edits overlap; `groups` are only the overlapping edits, each with the text around them."""

    def __init__(self, groups):
        super().__init__('%d overlapping group(s)' % len(groups))
        self.groups = groups


def components(items):
    """Connected components of (start, end, payload) items whose ranges overlap."""
    rows = sorted(items, key=lambda row: (row[0], row[1]))
    groups, end = [], None
    for row in rows:
        if groups and row[0] < end:
            groups[-1].append(row)
            end = max(end, row[1])
        else:
            groups.append([row])
            end = row[1]
    return groups


def nearest_lines(body, wanted, count=3):
    """The lines of `body` closest to text a writer quoted but the section does not contain."""
    import difflib
    lines = [line for line in body.splitlines() if line.strip()]
    first = wanted.strip().splitlines()[0] if wanted.strip() else ''
    return sorted(lines, key=lambda line: -difflib.SequenceMatcher(None, line, first).ratio())[:count]


def find_groups(parts, command_edits, narrative, base_commands):
    """Every place two writers' edits collide, as groups that hold only the colliding edits.

    A bad edit (text that is not in the base) is not a collision; the strict merge reports it."""
    _, sections = split_sections(narrative)
    bodies = {section['heading']: section['body'] for section in sections}
    ops = {}                                         # heading -> [(kind, writer, op)]
    inserts = {}
    seen = set()
    for writer, patch in parts:
        if not isinstance(patch, dict):
            continue
        for kind in ('edit_sections', 'replace_text'):
            for op in patch.get(kind) or []:
                if not isinstance(op, dict):
                    continue
                heading = (op.get('heading') or '').strip()
                signature = (kind, heading, op.get('old'), op.get('new'), op.get('content'), bool(op.get('all')))
                if signature in seen:
                    continue
                seen.add(signature)
                ops.setdefault(heading, []).append((kind, writer, op))
        for op in patch.get('insert_sections') or []:
            content = op.get('content') if isinstance(op, dict) else None
            if isinstance(content, str) and content.strip():
                inserts.setdefault(content.lstrip('\n').split('\n', 1)[0].strip(), []).append((writer, op, content))
    groups = []
    outline = '\n'.join(bodies)
    for heading, rows in ops.items():
        if heading not in bodies:
            # an edit aimed at a section that does not exist: the resolver places it where it belongs
            lost = [(k, w, op) for k, w, op in rows if k == 'replace_text']
            if lost:
                groups.append({'kind': 'missing', 'heading': heading, 'context': 'The plan\'s sections:\n' + outline,
                               'edits': [{'writer': w, 'replace_text': op} for _, w, op in lost],
                               'refs': [op for _, _, op in lost]})
            continue
        lost = [(k, w, op) for k, w, op in rows if k == 'replace_text' and isinstance(op.get('old'), str) and op['old']
                and (not spans(bodies[heading], op['old'], False)
                     or (bodies[heading].count(op['old']) > 1 and not op.get('all')))]
        if lost:
            # the quoted text is not in the section (a miscopy, or the wrong section): not an overlap,
            # but the same remedy -- a model that sees the section places the change in text that exists
            groups.append({'kind': 'missing', 'heading': heading, 'context': bodies[heading],
                           'edits': [{'writer': w, 'replace_text': op} for _, w, op in lost],
                           'refs': [op for _, _, op in lost],
                           'nearest': sorted({line for _, _, op in lost for line in nearest_lines(bodies[heading], op['old'])})})
            rows = [row for row in rows if all(row[2] is not op for _, _, op in lost)]
        whole = [row for row in rows if row[0] == 'edit_sections']
        if whole and len(rows) > 1:
            groups.append({'kind': 'section', 'heading': heading, 'context': bodies[heading],
                           'edits': [{'writer': w, 'edit_sections' if k == 'edit_sections' else 'replace_text': op}
                                     for k, w, op in rows], 'refs': [op for _, _, op in rows]})
            continue
        located = []
        for kind, writer, op in rows:
            if isinstance(op.get('old'), str) and op['old']:
                for start, end in spans(bodies[heading], op['old'], bool(op.get('all'))):
                    located.append((start, end, (writer, op)))
        for component in components(located):
            members = []
            for _, _, member in component:
                if all(member[1] is not other[1] for other in members):
                    members.append(member)
            if len(members) > 1:
                groups.append({'kind': 'text', 'heading': heading, 'context': bodies[heading],
                               'edits': [{'writer': w, 'replace_text': op} for w, op in members],
                               'refs': [op for _, op in members]})
    for heading, rows in inserts.items():
        distinct = {content for _, _, content in rows}
        if len(distinct) > 1:
            groups.append({'kind': 'insert', 'heading': heading, 'context': '',
                           'edits': [{'writer': w, 'insert_sections': op} for w, op, _ in rows],
                           'refs': [op for _, op, _ in rows]})
    located = []
    for writer, old, new in command_edits:
        if base_commands.count(old) == 1:
            start = base_commands.find(old)
            located.append((start, start + len(old), (writer, old, new)))
    for component in components(located):
        members = []
        for _, _, member in component:
            if member[1:] not in [m[1:] for m in members]:
                members.append(member)
        if len(members) > 1:
            groups.append({'kind': 'command', 'heading': 'verification_commands', 'context': base_commands,
                           'edits': [{'writer': w, 'commands_replace': {'old': o, 'new': n}} for w, o, n in members],
                           'refs': [(w, o, n) for w, o, n in members]})
    by_heading = {heading: [op for _, _, op in rows] for heading, rows in ops.items()}
    for number, group in enumerate(groups, 1):
        group['id'] = 'G%d' % number
        # text other edits in the same section already change: a resolution must stay clear of it
        mine = {op_sig(ref) for ref in group['refs']}
        group['avoid'] = [op['old'] for op in by_heading.get(group['heading'], [])
                          if isinstance(op.get('old'), str) and op_sig(op) not in mine]
    return groups


RESOLVE_PROMPT = '''Two or more writers revised the same approved plan at the same time and their edits overlap.
You reconcile only the overlapping edits below. Do not read files, run commands or investigate; everything
you need is here. Keep every requirement each edit serves, and write one coherent edit in place of the
overlapping ones. Edits elsewhere in the plan are merged by the driver; do not repeat them.

Your whole answer is one JSON object, checked against a schema, shaped exactly like:

{"schema":"uncle.artifact/v1","kind":"%s","resolutions":[{"group":"<its id>","patch":{"replace_text":[{"heading":"...","old":"...","new":"..."}],"edit_sections":[],"insert_sections":[]},"commands_replace":[]}]}

- A group of kind `missing` holds an edit whose `old` text is not in the section it names (a miscopy, or
  the wrong section) or occurs there more than once (add surrounding text to make it unique). Work out what the edit was meant to change and write it against text that exists:
  in that section as shown, or in another section if that is where it belongs (name that section's
  exact heading). The plan's headings are listed with such a group.
- One entry for the group below, with its id. Use `replace_text` (`old` copied exactly from the section text
  shown, unique within it) for a text or section group, unless the whole section needs rewriting
  (`edit_sections`: heading plus the section's whole new body). Several non-overlapping `replace_text`
  entries are fine. An insert group is answered with one `insert_sections` entry.
- A command group is answered only through `commands_replace` (`old` copied exactly from the commands shown).
- Change only the text the group's edits were aimed at. Other edits to the same section are already
  made; never touch text any of them changes (listed under each group), and do not restate them.
- Your edits must not overlap one another. Stop as soon as you have delivered the object.

%s
'''


def resolver_prompt(groups, dispositions):
    blocks, shown = [], set()
    for group in groups:
        why = sorted({(row.get('plan_change') or row.get('reason') or '').strip()
                      for row in dispositions if row.get('writer') in {e['writer'] for e in group['edits']}})
        blocks.append('## Group %s: %s edits in %s\n\nWhat the writers say they were doing: %s\n\n'
                      'Text as it is in the base plan:\n```\n%s\n```\n\nTheir overlapping edits:\n```json\n%s\n```\n\n'
                      '%s'
                      'Text already changed by other edits, which you must not touch:\n%s'
                      % (group['id'], group['kind'], group['heading'],
                         ' / '.join(w for w in why if w) or '(not stated)',
                         '(this section is printed under an earlier group)' if group['heading'] in shown else group['context'],
                         json.dumps(group['edits'], indent=2),
                         ('The lines of that section closest to what the writer quoted. Your `old` must be text '
                          'copied exactly from the section above, and these are the likeliest places:\n```\n%s\n```\n\n'
                          % '\n'.join(group['nearest'])) if group.get('nearest') else '',
                         '\n'.join('- `%s`' % text.replace('\n', ' ')[:300] for text in group.get('avoid') or []) or '(none)'))
        shown.add(group['heading'])
    return RESOLVE_PROMPT % (RESOLUTION_KIND, '\n\n'.join(blocks))


def op_sig(op):
    """What makes two edits the same edit, for dropping every copy of an edit a resolution replaces."""
    if isinstance(op, tuple):
        return ('c', op[1], op[2])
    if 'old' in op:
        return ('r', (op.get('heading') or '').strip(), op['old'], op.get('new'), bool(op.get('all')))
    if 'heading' in op:
        return ('e', (op.get('heading') or '').strip(), op.get('content'))
    return ('i', op.get('content'))


def substitute(parts, command_edits, groups, resolutions):
    """Replace each group's edits with its resolution; any group left unanswered stays a conflict."""
    answers = {}
    for row in resolutions.get('resolutions') or []:
        if isinstance(row, dict) and isinstance(row.get('group'), str):
            answers[row['group']] = row
    missing = [g['id'] for g in groups if g['id'] not in answers]
    if missing:
        raise Conflict('the resolver did not answer %s' % ', '.join(missing))
    dropped = {op_sig(ref) for group in groups for ref in group['refs']}
    cleaned = []
    for writer, patch in parts:
        cleaned.append((writer, {kind: [op for op in patch.get(kind) or [] if op_sig(op) not in dropped]
                                 for kind in ('edit_sections', 'replace_text', 'insert_sections')}))
    kept = [edit for edit in command_edits if op_sig(edit) not in dropped]
    for group in groups:
        answer = answers[group['id']]
        patch = answer.get('patch') if isinstance(answer.get('patch'), dict) else {}
        cleaned.append(('resolver-' + group['id'], patch))
        for edit in answer.get('commands_replace') or []:
            if isinstance(edit, dict) and isinstance(edit.get('old'), str) and isinstance(edit.get('new'), str):
                kept.append(('resolver-' + group['id'], edit['old'], edit['new']))
    return cleaned, kept


def read_resolutions(path):
    """One answer file, or a directory of `resolutions-<group>.json` files (one per resolver call)."""
    path = Path(path)
    if not path.is_dir():
        return read_json(path)
    rows = []
    for answer in sorted(path.glob('resolutions-*.json')):
        rows += read_json(answer).get('resolutions') or []
    return {'resolutions': rows}


def check_resolutions(plan_path, directory):
    """{group id: why its answer cannot be applied}, judged one group at a time against the base plan.

    A resolver is quick and now and then quotes text that is not in the section; finding that here lets
    that one group be asked again, with the reason, instead of failing the whole merge."""
    plan = read_json(plan_path)
    narrative = plan.get('narrative') or ''
    bodies = {section['heading']: section['body'] for section in split_sections(narrative)[1]}
    commands = (plan.get('verification_commands') or '').strip()
    groups = json.loads(Path(directory, 'conflicts.json').read_text(encoding='utf-8'))
    answers = {}
    for answer in sorted(Path(directory).glob('resolutions-*.json')):
        try:
            for row in read_json(answer).get('resolutions') or []:
                if isinstance(row, dict) and isinstance(row.get('group'), str):
                    answers[row['group']] = row
        except Conflict:
            pass
    bad = {}
    for group in groups:
        row = answers.get(group['id'])
        if row is None:
            bad[group['id']] = 'there was no valid answer for this group'
            continue
        patch = row.get('patch') if isinstance(row.get('patch'), dict) else {}
        for edit in patch.get('replace_text') or []:
            heading = (edit.get('heading') or '').strip()
            old = edit.get('old')
            if heading not in bodies:
                bad[group['id']] = 'the section %r does not exist' % heading
            elif not isinstance(old, str) or not old:
                bad[group['id']] = 'an edit has no `old` text'
            elif bodies[heading].count(old) == 0:
                bad[group['id']] = ('`old` text %r is not in section %r; copy it exactly from the section text shown'
                                    % (old[:120], heading))
            elif bodies[heading].count(old) > 1 and not edit.get('all'):
                bad[group['id']] = ('`old` text %r occurs %d times in section %r; add surrounding text so it is unique'
                                    % (old[:120], bodies[heading].count(old), heading))
        for edit in patch.get('edit_sections') or []:
            if (edit.get('heading') or '').strip() not in bodies:
                bad[group['id']] = 'the section %r does not exist' % edit.get('heading')
        for edit in row.get('commands_replace') or []:
            if isinstance(edit, dict) and commands.count(edit.get('old') or '\0') != 1:
                bad[group['id']] = 'command text %r is not in the verification commands exactly once' % (edit.get('old') or '')[:120]
    for gid, why in bad.items():
        original = Path(directory, 'prompts', 'resolve-%s.md' % gid).read_text(encoding='utf-8')
        Path(directory, 'prompts', 'resolve-%s.retry.md' % gid).write_text(
            original + '\n\n## Your previous answer was rejected\n\n%s.\nAnswer again for this group, copying every `old` '
            'exactly from the text shown above.\n' % why, encoding='utf-8')
    return bad


def merge(plan_path, slices_path, directory, output, resolutions=None):
    plan = read_json(plan_path)
    owners = []
    for line in Path(slices_path).read_text(encoding='utf-8').splitlines():
        name, _, ids = line.partition('\t')
        if name.strip():
            owners.append((name.strip(), [i for i in ids.split(',') if i]))
    if not owners:
        raise Conflict('no writers were planned')
    dispositions, parts = [], []
    paths, command_edits = {}, []
    base_commands = (plan.get('verification_commands') or '').strip()
    try:
        base_paths = protected_paths(plan).strip()
    except ValueError:
        base_paths = ''     # the plan predates the field; the writer that owns it supplies it
    for name, ids in owners:
        delivery = read_json(Path(directory) / ('%s.json' % name))
        by_finding = {}
        for row in delivery.get('dispositions') or []:
            if isinstance(row, dict) and row.get('finding') in ids and row['finding'] not in by_finding:
                by_finding[row['finding']] = row
        missing = [i for i in ids if i not in by_finding]
        if missing:
            raise Conflict('writer %s left %s without a disposition' % (name, ', '.join(missing)))
        dispositions += [by_finding[i] for i in ids]
        parts.append((name, delivery.get('patch') or {}))
        for edit in delivery.get('commands_replace') or []:
            if (not isinstance(edit, dict) or not isinstance(edit.get('old'), str) or not edit['old']
                    or not isinstance(edit.get('new'), str)):
                raise Conflict('writer %s: commands_replace needs "old" and "new"' % name)
            command_edits.append((name, edit['old'], edit['new']))
        value = delivery.get('protected_verification_paths')
        if isinstance(value, str) and value.strip() and value.strip() != base_paths:
            paths[value.strip()] = name
        if isinstance(delivery.get('verification_commands'), str) and delivery['verification_commands'].strip() != base_commands:
            raise Conflict('writer %s wrote verification_commands whole; it must use commands_replace' % name)
    if len(paths) > 1:
        raise Conflict('writers disagree on protected_verification_paths')
    narrative = plan.get('narrative') or ''
    groups = find_groups(parts, command_edits, narrative, base_commands)
    if groups:
        if resolutions is None:
            Path(directory, 'conflicts.json').write_text(json.dumps(groups, indent=2, default=str), encoding='utf-8')
            plan_changes = [dict(row, writer=name) for name, ids in owners
                            for row in read_json(Path(directory) / ('%s.json' % name)).get('dispositions') or []
                            if isinstance(row, dict) and row.get('finding') in ids]
            Path(directory, 'prompts').mkdir(exist_ok=True)
            for group in groups:   # one small call per group, so the slowest group sets the time, not all of them
                Path(directory, 'prompts', 'resolve-%s.md' % group['id']).write_text(
                    resolver_prompt([group], plan_changes), encoding='utf-8')
            raise NeedsResolution(groups)
        parts, command_edits = substitute(parts, command_edits, groups, read_resolutions(resolutions))
    commands = merged_commands(base_commands, command_edits)
    if not (next(iter(paths), base_paths) or '').strip():
        raise Conflict('no writer supplied protected_verification_paths')
    patch = merged_patch(parts, narrative)
    apply_patch(narrative, patch)   # a patch that does not apply is a conflict, found here
    result = {'schema': 'uncle.artifact/v1', 'kind': 'plan', 'dispositions': dispositions, 'patch': patch,
              'verification_commands': commands,
              'protected_verification_paths': next(iter(paths), base_paths)}
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(argv):
    try:
        command, rest = argv[0], argv[1:]
        if command == 'slices' and len(rest) == 1:
            try:
                size = int(os.environ.get('WORKFLOW_UPDATED_PLAN_EDIT_SLICE') or SLICE)
            except ValueError:
                size = SLICE
            for name, ids in slices(finding_ids(rest[0]), size):
                print('%s\t%s' % (name, ','.join(ids)))
        elif command == 'prompt' and len(rest) in (3, 4):
            write_prompt(rest[0], [i for i in rest[1].split(',') if i], rest[2], owns_fields=len(rest) == 4)
        elif command == 'check' and len(rest) == 2:
            bad = check_resolutions(*rest)
            for gid, why in sorted(bad.items()):
                print(gid)
                print('updated-plan edits: group %s: %s' % (gid, why), file=sys.stderr)
            return 5 if bad else 0
        elif command == 'merge' and len(rest) in (4, 5):
            merge(*rest)
        else:
            raise SystemExit(__doc__)
    except NeedsResolution as overlap:
        print('updated-plan edits: %s; they need one resolver call' % overlap, file=sys.stderr)
        return 3
    except (Conflict, ValueError, OSError) as error:
        print('updated-plan edits: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
