#!/usr/bin/env python3
"""Private review units; the four public lens packets retain their old contract."""
import argparse
import json
import os
import re
from pathlib import Path
import sys

from unit_scheduler import granularity, group_size, option
from worker_packets import PacketError, SCHEMA, SEVERITIES, _norm, load

KIND = 'adversarial-review-worker-packet'
AREAS = {
    'requirements': (
        'Acceptance criteria, requirement coverage, and omitted user flows.',
        'Data semantics, calculations, validation, and boundary cases.',
        'User interactions, accessibility, error states, and recovery.',
        'Cross-section consistency, dependencies, assumptions, and feasibility.'),
    'regression': (
        'Existing behavior, compatibility, interfaces, and scope boundaries.',
        'State transitions, persistence, migration, and data integrity.',
        'Failure recovery, concurrency, lifecycle, and integration boundaries.',
        'Cross-section dependencies, rollout, configuration, and operational regressions.'),
    'security': (
        'Trust boundaries, authentication, authorization, and tenant isolation.',
        'Input validation, injection, unsafe rendering, and untrusted content.',
        'Secrets, sensitive data, storage, transport, and privacy.',
        'Dependencies, resource abuse, deployment, and cross-section security assumptions.'),
    'testability': (
        'Acceptance criteria mapped to observable assertions and test coverage.',
        'Fixtures, determinism, isolation, setup, and environment dependencies.',
        'Negative cases, boundaries, failure recovery, and regression tests.',
        'Integration evidence, verification commands, test ownership, and cross-section gaps.')}


def slice_count(runner, config=None):
    default = group_size(runner, 'adversarial-review', small=4, large=1, config=config)
    value = os.environ.get('WORKFLOW_ADVERSARIAL_REVIEW_SLICES',
                           option(runner, 'adversarial-review', 'slices', default, config)).strip().lower()
    if value in ('off', 'false', '0'):
        return 1
    if not value.isdecimal() or not 1 <= int(value) <= 8:
        raise ValueError('adversarial-review.slices must be off or an integer from 1 to 8')
    return int(value)


def prepare(directory, plan, context, count):
    directory = Path(directory)
    inputs = []
    for path in (Path(plan), Path(context)):
        if path == Path(context) and not path.exists():
            continue
        inputs.append('### %s\n\n```json\n%s\n```' %
                      (path.name, json.dumps(json.loads(path.read_text()), ensure_ascii=False)))
    template = Path(__file__).resolve().parents[2] / 'prompts/change/adversarial-review-worker.md'
    common = template.read_text() + '\n\n## Canonical inputs (binding)\n\n'
    common += 'All review inputs are embedded below. Use these snapshots only; do not inspect the repository.\n\n'
    common += '\n\n'.join(inputs)
    prompts = directory / 'slices/prompts'
    prompts.mkdir(parents=True, exist_ok=True)
    for lens, areas in AREAS.items():
        # More than four units subdivide each checklist area by plan region.
        for index in range(count):
            if count <= 4:
                assigned = areas[index::count]
                scope = ''
            else:
                assigned = (areas[index % 4],)
                scope = ''
                if index % 4 < count - 4:
                    scope = (' Primary evidence must be in the %s half of the plan in document order; '
                             'read the whole plan for interactions. For omissions or cross-half issues, '
                             'the first-half unit owns the finding.' % ('first' if index < 4 else 'second'))
            prompt = common + '\n\n## Assigned review lens\n\nFocus only on **%s**.\n' % lens
            prompt += '\n## Assigned checklist areas\n\n' + '\n'.join('- ' + area for area in assigned)
            prompt += scope + '\nReport only findings in these assigned areas. Other units cover the remaining areas.\n'
            prompt += ('Gather and rank candidate issues for this lens, strongest evidence first. Cite the affected plan ids '
                       'and the specific defect category; combine near-duplicates. Omit speculative issues. '
                       'The lens publishes one ranked selection from all its units.\n')
            (prompts / ('%s-%d.md' % (lens, index + 1))).write_text(prompt, encoding='utf-8')


def validate(packet):
    # The generic legacy loader accepts any worker kind; slices require this one.
    value = json.loads(Path(packet).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('kind') != KIND:
        raise PacketError('%s: expected %s' % (Path(packet).name, KIND))
    return load(packet, KIND)


def finding_limit(runner='self-hosted', config=None):
    default = 6 if granularity(runner, 'adversarial-review', config) == 'small' else 0
    value = os.environ.get('WORKFLOW_ADVERSARIAL_REVIEW_MAX_FINDINGS_PER_LENS',
                           option(runner, 'adversarial-review', 'max-findings-per-lens', default, config)).strip()
    if not value.isdecimal():
        raise ValueError('adversarial-review.max-findings-per-lens must be a nonnegative integer')
    return int(value)


def issue_key(item):
    text = item['summary'] + ' ' + item['evidence']
    targets = set(re.findall(r'\b(?:[A-Z]{1,4}-\d+[A-Za-z]?|step-\d+|s\d+(?:\.[a-z]?\d+)+)\b', text))
    categories = set()
    for category, words in (
            ('validation', r'validat|malformed|invalid|reject|out.of.range|bounds'),
            ('authorization', r'authoriz|permission|access control|tenant isolation'),
            ('injection', r'inject|escap|saniti|unsafe render'),
            ('recovery', r'rollback|recover|retry|retries'),
            ('concurrency', r'concurren|race|atomic|lock|simultaneous'),
            ('ownership', r'owner|owns|unowned'),
            ('determinism', r'determinis|flak|random|clock'),
            ('accessibility', r'accessib|keyboard|screen.reader|aria')):
        if re.search(words, text, re.I):
            categories.add(category)
    return targets, categories


def same_issue(left, right):
    if _norm(left['summary']) == _norm(right['summary']):
        return True
    a, ac = issue_key(left)
    b, bc = issue_key(right)
    # A shared target alone is not a duplicate: one row can have several defects.
    return bool(a & b and ac and ac == bc)


def rank(item):
    severity = SEVERITIES.index(item['severity']) if item['severity'] in SEVERITIES else len(SEVERITIES)
    return severity, -len(issue_key(item)[0]), -len(item['evidence'])


def merge(directory, count, runner='self-hosted'):
    directory = Path(directory)
    packets = {}
    small = count > 1 and granularity(runner, 'adversarial-review') == 'small'
    for lens in AREAS:
        findings = []
        limit = finding_limit(runner) if small else 0
        for index in range(1, count + 1):
            for item in validate(directory / 'slices' / ('%s-%d.json' % (lens, index))):
                target = next((f for f in findings if same_issue(f, item)), None) if small else next(
                    (f for f in findings if _norm(f['summary']) == _norm(item['summary'])), None)
                if target is None:
                    target = dict(item)
                    target['_evidence'] = [item['evidence']] if item['evidence'] else []
                    findings.append(target)
                else:
                    if rank(item) < rank(target):
                        target['summary'] = item['summary']
                        target['evidence'] = item['evidence']
                        target['_evidence'] = [item['evidence']] + [e for e in target['_evidence'] if e != item['evidence']]
                    if item['evidence'] and item['evidence'] not in target['_evidence']:
                        target['_evidence'].append(item['evidence'])
                    if item['severity'] in SEVERITIES and (target['severity'] not in SEVERITIES or
                            SEVERITIES.index(item['severity']) < SEVERITIES.index(target['severity'])):
                        target['severity'] = item['severity']
        if limit and len(findings) > limit:
            selected = {id(item) for item in sorted(findings, key=rank)[:limit]}
            findings = [item for item in findings if id(item) in selected]
        # Slice-local AR-001 IDs must never fuse unrelated observations in the
        # existing lens collator. Preserve unique IDs, allocate collisions in order.
        reserved = {item['id'] for item in findings}
        used = set()
        number = 1
        for item in findings:
            if item['id'] in used:
                while 'AR-%03d' % number in reserved | used:
                    number += 1
                item['id'] = 'AR-%03d' % number
            used.add(item['id'])
            item['evidence'] = '; '.join(item.pop('_evidence'))
            if item['severity']:
                item['severity'] = item['severity'].title()
        packets[lens] = {'schema': SCHEMA, 'kind': KIND, 'findings': findings}
    # Validate every slice before publishing any complete lens.
    for lens, packet in packets.items():
        (directory / (lens + '.json')).write_text(json.dumps(packet, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    count = sub.add_parser('count'); count.add_argument('runner')
    prep = sub.add_parser('prepare')
    prep.add_argument('directory'); prep.add_argument('plan'); prep.add_argument('context'); prep.add_argument('count', type=int)
    check = sub.add_parser('validate'); check.add_argument('packet')
    join = sub.add_parser('merge'); join.add_argument('directory'); join.add_argument('count', type=int)
    join.add_argument('--runner', default='self-hosted')
    args = vars(parser.parse_args()); command = args.pop('command')
    try:
        result = {'count': slice_count, 'prepare': prepare, 'validate': validate, 'merge': merge}[command](**args)
        if command == 'count':
            print(result)
    except (ValueError, OSError) as error:
        print('adversarial slices: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
