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

# Loaded both as a normal script (sys.path[0] is this directory already) and
# via importlib.util.spec_from_file_location (which does not add it), so the
# sibling import below needs the directory on sys.path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_patch import split_sections

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
    extra_fields = ''
    if not change:
        extra_fields = (' `verification_commands` and `protected_verification_paths` are also '
                         'required top-level strings, even when unchanged.')
    _, sections = split_sections(plan.get('narrative') or '')
    headings = '\n'.join('- `%s`' % section['heading'] for section in sections) or '(the base plan has no `## ` sections)'
    example_kind = 'change-plan' if change else 'plan'
    return '''You are revising an approved %s after adversarial review.

This is a sealed synthesis task. The complete authoritative inputs are embedded
below. Do not read files, enumerate directories, inspect the repository, run
commands, or read worker packets. Do not investigate again. Resolve only the
listed findings.

Produce exactly one JSON object. Do not read files, enumerate directories, run
commands, or write any file except the one canonical delivery path supplied by
the driver. Your final chat response is diagnostics only; the driver publishes
that file as `.uncle/docs/%s`. It must have
schema `uncle.artifact/v1`, kind `%s`, one disposition for every AR finding,
and a `patch` object naming only what changed.%s

Do not write a top-level `narrative` key -- not `null`, not the unchanged
text, not present at all. This is enforced: the driver silently discards any
`narrative` you include and reconstructs the plan's full text from `patch`
alone, against the base plan already on disk. Writing one out costs you
generation time for zero effect on the result. Shape your reply exactly like
this, with nothing else at the top level:

```json
{"schema":"uncle.artifact/v1","kind":"%s","dispositions":[{"finding":"AR-001","disposition":"Accepted","reason":"...","plan_change":"..."}],"patch":{"edit_sections":[{"heading":"...","content":"..."}],"insert_sections":[]}}
```

Do not reproduce a section you are not changing: every section not named in
`patch` carries over from the base plan exactly as it already is. `patch` has
two optional arrays:

- `edit_sections`: `[{"heading": "<exact existing heading, copied verbatim from
  the list below>", "content": "<the section's whole new body, heading line
  excluded>"}]`. Replaces one existing section's body in full.
- `insert_sections`: `[{"content": "<a whole new section, its own \\"## \\"
  heading line included>", "after": "<an existing heading to insert after>"}]`.
  Use `"before"` instead of `"after"` to insert before that heading, or
  `"position": "start"` to insert first; omitting all three appends at the end.
  Only for content that plainly does not belong in any existing section --
  prefer `edit_sections` whenever the change extends one that already exists.

Every disposition's `plan_change` must be reflected by some `patch` entry: a
disposition with no matching edit or insert is a rejected delivery. The
disposition fields are finding, disposition (Accepted, Partially accepted,
Rejected, or Deferred), reason, and plan_change. Do not write Markdown, a
summary, a draft, or progress commentary, and do not write a `narrative` key.

## Existing sections in the base plan, in order

Quote a heading exactly, as printed here, to edit it or to anchor an insert.

%s

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
''' % (label, artifact, plan['kind'], extra_fields, example_kind, headings,
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
