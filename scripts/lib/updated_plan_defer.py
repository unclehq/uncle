"""Bound finding attempts and record exhausted edits as ordinary dispositions."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unit_scheduler import config_values


def option(stage, name, default):
    from self_hosted import config_stage
    config = config_values()
    scopes = list(dict.fromkeys((stage, config_stage(stage, config), 'updated-plan')))
    prefix = 'WORKFLOW_UPDATED_PLAN_' + name.upper().replace('-', '_')
    for scope in scopes:
        for key in (prefix + '_' + scope.upper().replace('-', '_'),
                    'WORKFLOW_' + scope.upper().replace('-', '_') + '_' + name.upper().replace('-', '_')):
            if key in os.environ:
                return os.environ[key].strip().lower()
    for scope in scopes:
        if scope + '.' + name in config:
            return config[scope + '.' + name].strip().lower()
    return str(default)


def policy(stage):
    value = option(stage, 'defer-unapplied', 'on')
    if value not in ('on', 'off', 'non-critical'):
        raise ValueError('updated-plan.defer-unapplied must be on, off or non-critical')
    return value


def remaining(directory, ids, stage):
    limit = float(option(stage, 'finding-seconds', 360))
    if not 0 < limit < float('inf'):
        raise ValueError('updated-plan.finding-seconds must be positive and finite')
    path = Path(directory, 'finding-started.json')
    with Path(directory, 'finding-started.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        starts = json.loads(path.read_text()) if path.exists() else {}
        now = time.monotonic()
        for finding in ids.split(','):
            if finding:
                record = starts.setdefault(finding, dict(start=now, deadline=now + limit))
                record['deadline'] = min(record['deadline'], record['start'] + limit)
        path.write_text(json.dumps(starts) + '\n')
        return max(0, min((starts[i]['deadline'] - now for i in ids.split(',') if i), default=limit))


def owners(directory):
    return [line.split('\t', 1) for line in Path(directory, 'slices.tsv').read_text().splitlines() if line.strip()]


def group_writers(directory, groups):
    conflicts = json.loads(Path(directory, 'conflicts.json').read_text())
    writers = {e['writer'] for g in conflicts if g['id'] in groups for e in g['edits']}
    # A packet is atomic: without op-to-finding provenance, dropping one of its
    # edits means deferring its findings. Include connected resolver groups too.
    while True:
        expanded = writers | {e['writer'] for g in conflicts if any(e['writer'] in writers for e in g['edits']) for e in g['edits']}
        if expanded == writers:
            return writers
        writers = expanded


def group_ids(directory, group):
    writers = {e['writer'] for g in json.loads(Path(directory, 'conflicts.json').read_text())
               if g['id'] == group for e in g['edits']}
    return ','.join(ids for name, ids in owners(directory) if name in writers)


def cause(directory, name, stage, resolver=False):
    directory = Path(directory)
    worker = stage + ('-worker-resolve-' if resolver else '-worker-edits-') + name
    candidates = [directory / 'prompts' / (('resolve-' if resolver else '') + name + suffix)
                  for suffix in ('.rejection', '.validator-rejected')]
    detail = []
    for path in candidates + [directory.parent / 'logs' / (worker + suffix) for suffix in ('.log', '-retry.log')]:
        if path.exists():
            text = path.read_text(errors='replace')
            lines = text.splitlines()[-12:]
            detail.extend(line for line in lines if line.strip())
    stage_log = directory.parent / 'logs/UPDATED_PLAN.log'
    if stage_log.exists():
        detail.extend(line for line in stage_log.read_text(errors='replace').splitlines() if worker + ' ' in line or worker + '-retry ' in line)
    # Preserve the actual rejection, but keep the human-facing reason bounded.
    precise = [line for line in detail if re.search(r'typed rows block|deadline:|finding wall|runner exit|Error:|invalid|unknown|not found|does not|not a |rejected', line, re.I)]
    return ' '.join(precise or detail or ['writer attempts exhausted without a usable packet'])[-1200:]


def defer(directory, names, stage, reason):
    directory = Path(directory)
    assigned = [(name, ids.split(',')) for name, ids in owners(directory) if name in names]
    if not assigned:
        raise ValueError('no finding packets match exhausted work')
    mode = policy(stage)
    if mode == 'off':
        raise ValueError('automatic deferral is disabled')
    if mode == 'non-critical':
        review = json.loads((directory.parent / 'documents/ADVERSARIAL_REVIEW.json').read_text())
        critical = {row['id'] for row in review.get('findings', []) if re.match(r'critical\b', str(row.get('severity', '')), re.I)}
        if any(critical.intersection(ids) for _, ids in assigned):
            raise ValueError('automatic deferral is disabled for CRITICAL findings')
    saved = directory / 'deferred.json'
    deferred = json.loads(saved.read_text()) if saved.exists() else {}
    for name, ids in assigned:
        path = directory / (name + '.json')
        if path.exists():
            archive = directory / 'attempts'
            archive.mkdir(exist_ok=True)
            n = 1
            while (archive / (name + '-deferred-%d.json' % n)).exists():
                n += 1
            shutil.copy2(path, archive / (name + '-deferred-%d.json' % n))
        rows = []
        for finding in ids:
            why = 'Deferred: the plan edit could not be applied automatically (%s); review by hand.' % reason
            row = dict(finding=finding, disposition='Deferred', reason=why, plan_change='None; review by hand.')
            rows.append(row)
            deferred[finding] = row
        # Both merge engines accept this empty packet; no schema or document
        # extension is needed for an existing disposition.
        packet = dict(schema='uncle.artifact/v1', kind='updated-plan-edit-ops-packet', dispositions=rows,
                      ops=[], patch={}, commands_replace=[])
        path.write_text(json.dumps(packet, indent=2) + '\n')
    saved.write_text(json.dumps(deferred, indent=2) + '\n')


def merge_remaining(directory, stage, plan, helper):
    import updated_plan_edits as edits
    import updated_plan_ops as ops
    directory = Path(directory)
    recorded = directory / 'merge-helper'
    if recorded.exists():
        helper = recorded.read_text().strip()
    module = ops if helper.endswith('updated_plan_ops.py') else edits
    late = os.environ.get('UNCLE_LATE_OPS') or str(directory / 'reconcile.json')
    if Path(late).is_file():
        os.environ['UNCLE_LATE_OPS'] = late
    conflicts = directory / 'conflicts.json'
    old_groups = json.loads(conflicts.read_text()) if conflicts.exists() else []
    answers = {}
    for group in old_groups:
        path = directory / ('resolutions-' + group['id'] + '.json')
        if path.exists():
            try:
                packet = ops.read_packet(path) if module is ops else edits.read_json(path)
                answers[group['id']] = next(row for row in packet.get('resolutions', []) if row['group'] == group['id'])
            except (ValueError, KeyError, StopIteration):
                pass
    try:
        module.merge(plan, directory / 'slices.tsv', directory, directory / 'merged.json')
        return
    except edits.NeedsResolution as error:
        new_groups = error.groups
    def signature(group):
        return json.dumps({k: v for k, v in group.items() if k != 'id'}, sort_keys=True)
    prior = {signature(g): answers[g['id']] for g in old_groups if g['id'] in answers}
    # Group numbers can shift when a failed group disappears. Rebind only an
    # identical remaining group to its already validated successful answer.
    for group in new_groups:
        row = dict(prior[signature(group)], group=group['id'])
        (directory / ('resolutions-' + group['id'] + '.json')).write_text(json.dumps(dict(resolutions=[row])))
    module.merge(plan, directory / 'slices.tsv', directory, directory / 'merged.json', directory)


def resolver_defer(directory, groups, stage, plan, helper):
    names = group_writers(directory, set(groups))
    reason = '; '.join('resolver %s: %s' % (g, cause(directory, g, stage, resolver=True)) for g in groups)
    defer(directory, names, stage, reason)
    merge_remaining(directory, stage, plan, helper)


def structure_writers(directory, repair):
    import plan_model as pm
    import updated_plan_edits as edits
    scope = json.loads(Path(repair, 'scope.json').read_text())
    ids = set(scope['ids'])
    model = json.loads(Path(repair, 'model.json').read_text())
    headings = {section['heading'] for section in model['sections']
                if ids.intersection(set(pm.index(dict(model, sections=[section])))
                                    | {step['id'] for step in pm.steps_of(dict(model, sections=[section]))})}
    base = json.loads(Path(directory, 'base-plan.json').read_text())
    names = set()
    for name, _ in owners(directory):
        packet = json.loads(Path(directory, name + '.json').read_text())
        text_patch = edits.retarget(packet.get('patch') or {}, base['narrative'])
        structural_patch = any(isinstance(row, dict) and (row.get('heading') or '').lstrip('# ').strip() in headings
                               for rows in text_patch.values() if isinstance(rows, list) for row in rows)
        if (any((op.get('id') or op.get('target')) in ids for op in packet.get('ops', []))
                or structural_patch or packet.get('commands_replace')
                or (packet.get('protected_verification_paths') and packet['protected_verification_paths'] != base.get('protected_verification_paths'))):
            names.add(name)
    # Preserve atomic resolver results: a failed structural edit cannot keep
    # another packet's half of the same resolved conflict.
    conflicts = Path(directory, 'conflicts.json')
    if conflicts.exists():
        groups = json.loads(conflicts.read_text())
        names |= group_writers(directory, {g['id'] for g in groups if any(e['writer'] in names for e in g['edits'])})
    return names


def structure_defer(directory, repair, stage, helper):
    directory, repair = Path(directory), Path(repair)
    names = structure_writers(directory, repair)
    reason = 'structural repair attempts exhausted: ' + (repair / 'apply-error.log').read_text()[-1200:]
    defer(directory, names, stage, ' '.join(reason.split()))
    merge_remaining(directory, stage, directory / 'base-plan.json', helper)
    materialize(directory / 'base-plan.json', directory / 'merged.json', repair / 'repaired.json')


def materialize(base_path, packet_path, output):
    from plan_patch import apply_patch
    base = json.loads(Path(base_path).read_text())
    packet = json.loads(Path(packet_path).read_text())
    result = dict(base, **packet)
    result['narrative'] = apply_patch(base['narrative'], packet.get('patch', {}))
    result.pop('patch', None)
    result.pop('sections', None)
    Path(output).write_text(json.dumps(result, indent=2) + '\n')


def prepare_publication(directory, stage):
    import plan_model as pm
    import publish_agent_artifact as publisher
    directory = Path(directory)
    packet = json.loads((directory / 'merged.json').read_text())
    publisher.expand_patch(packet, Path.cwd(), stage)
    publisher.preserve_updated_plan_fields(packet, Path.cwd(), stage)
    try:
        pm.publish_records(packet, Path.cwd(), stage=stage)
    except pm.PlanError as error:
        packet.pop('patch', None)
        (directory / 'publication-candidate.json').write_text(json.dumps(packet, indent=2) + '\n')
        (directory / 'publication-error.log').write_text(str(error) + '\n')
        return 3
    return 0


def report(directory):
    path = Path(directory, 'deferred.json')
    if not path.exists():
        return
    rows = json.loads(path.read_text())
    for finding, row in rows.items():
        print('Updated-plan finding %s: %s' % (finding, row['reason']))
    print('Updated-plan: %d finding(s) Deferred; review by hand in the existing dispositions table.' % len(rows))


if __name__ == '__main__':
    try:
        command, *args = sys.argv[1:]
        if command == 'remaining':
            print(remaining(*args))
        elif command == 'group-ids':
            print(group_ids(*args))
        elif command == 'writer':
            directory, name, stage = args
            defer(directory, {name}, stage, cause(directory, name, stage))
        elif command == 'resolvers':
            directory, groups, stage, plan, helper = args
            resolver_defer(directory, groups.split(), stage, plan, helper)
        elif command == 'structure-ids':
            directory, repair = args
            names = structure_writers(directory, repair)
            print(','.join(ids for name, ids in owners(directory) if name in names))
        elif command == 'structure':
            structure_defer(*args)
        elif command == 'prepare-publication':
            sys.exit(prepare_publication(*args))
        elif command == 'report':
            report(*args)
    except (ValueError, OSError, KeyError) as error:
        print('updated-plan deferral: %s' % error, file=sys.stderr)
        sys.exit(1)
