#!/usr/bin/env python3
"""Build the sealed, JSON-only input for an updated-plan parent.

The specialist panel has already done the broad review.  The parent must make
only the remaining revision decisions; letting it rediscover the repository or
the worker directory both wastes turns and lets a missing packet turn into an
unrelated exploration failure.
"""
import json
import sys
from pathlib import Path


SCHEMA = 'uncle.artifact/v1'


def load(path, kind):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('%s: invalid canonical JSON: %s' % (path, error)) from error
    if not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('kind') != kind:
        raise ValueError('%s: expected canonical %s JSON' % (path, kind))
    return value


def prompt(plan, review, workers, change=False):
    if workers.get('schema') != SCHEMA or workers.get('kind') != 'updated-plan-worker-packets':
        raise ValueError('worker packet: expected collated updated-plan-worker-packets JSON')
    if not isinstance(workers.get('findings'), list) or not isinstance(workers.get('workers'), list):
        raise ValueError('worker packet: findings and workers must be arrays')
    artifact = 'CHANGE_PLAN.md' if change else 'UPDATED_PROJECT_PLAN.md'
    label = 'change plan' if change else 'implementation plan'
    fields = "the base plan's narrative updated only where the review requires it"
    if not change:
        fields = "the base plan's narrative/verification_commands/protected_verification_paths updated only where the review requires it"
    return '''You are revising an approved %s after adversarial review.

This is a sealed synthesis task. The complete authoritative inputs are embedded
below. Do not read files, enumerate directories, inspect the repository, run
commands, or read worker packets. Do not investigate again. Resolve only the
listed findings and preserve every unaffected normative plan row exactly.

Return exactly one JSON object as your final response. Do not use tools or
write any file. The driver will publish it as `.uncle/docs/%s`. It must have
schema `uncle.artifact/v1`, kind `%s`, %s, and
one disposition for every AR finding. For an implementation plan,
`narrative`, `verification_commands`, and `protected_verification_paths` are
all required top-level strings, even when unchanged. The disposition fields
are finding, disposition (Accepted, Partially accepted, Rejected, or Deferred),
reason, and plan_change. Do not write Markdown, a summary, a draft, or
progress commentary.

## Base project plan JSON
```json
%s
```

## Adversarial review JSON
```json
%s
```

## Collated specialist findings JSON
```json
%s
```
''' % (label, artifact, plan['kind'], fields,
       json.dumps(plan, indent=2, sort_keys=True),
       json.dumps(review, indent=2, sort_keys=True),
       json.dumps(workers, indent=2, sort_keys=True))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    change = False
    if args and args[0] == '--change':
        change = True
        args.pop(0)
    if len(args) != 4:
        raise ValueError('usage: [--change] PLAN.json ADVERSARIAL_REVIEW.json UPDATED_PLAN_WORKERS.json OUTPUT')
    plan = load(args[0], 'change-plan' if change else 'plan')
    review = load(args[1], 'adversarial-review')
    workers = load(args[2], 'updated-plan-worker-packets')
    Path(args[3]).write_text(prompt(plan, review, workers, change=change), encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print('updated-plan synthesis input: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
