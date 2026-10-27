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


def _cell(value, limit=None):
    """One table cell: whitespace collapsed, pipes escaped.  `limit` None keeps all of it."""
    if isinstance(value, (list, tuple)):
        value = '; '.join(str(item) for item in value)
    text = ' '.join(str(value if value is not None else '').split()).replace('|', '\\|')
    if limit and len(text) > limit:
        text = text[:limit - 1].rstrip() + '\u2026'
    return text


def review_table(review):
    """The adversarial review as one row per finding: id, severity, evidence, required change.

    The model wrote its updated plan from the full review JSON, which repeats each finding
    as a title, a failure, a reference and a fix.  Every finding and its evidence is kept;
    the repeated prose around them is not, which shortens the input the model has to hold
    while it writes a plan that already has to stay short.
    """
    rows = ['| id | severity | evidence | required plan change |', '|---|---|---|---|']
    for finding in review.get('findings') or []:
        if not isinstance(finding, dict):
            continue
        evidence = finding.get('references') or finding.get('failure') or finding.get('title') or ''
        change = finding.get('fix') or ''
        verify = finding.get('verify')
        if verify:
            change = (change + ' Verify: ' + _cell(verify)).strip()
        rows.append('| %s | %s | %s | %s |' % (_cell(finding.get('id')), _cell(finding.get('severity')),
                                              _cell(evidence), _cell(change)))
    verdict = _cell(review.get('overall_assessment'))
    return '\n'.join(rows) + ('\n\nOverall verdict: ' + verdict if verdict else '')


def corrections_table(workers):
    """What each specialist asked for, per finding.  Their evidence and sources repeat the
    review table's, so only the corrections, gaps and risks are carried."""
    rows = ['| id | required corrections | gaps | risks |', '|---|---|---|---|']
    for finding in workers.get('findings') or []:
        if not isinstance(finding, dict):
            continue
        rows.append('| %s | %s | %s | %s |' % (
            _cell(finding.get('id')), _cell(finding.get('required_corrections')),
            _cell(finding.get('gaps')), _cell(finding.get('risks'))))
    status = ', '.join('%s: %s' % (_cell(w.get('source')), _cell(w.get('status')))
                       for w in workers.get('workers') or [] if isinstance(w, dict))
    return '\n'.join(rows) + ('\n\nSpecialists: ' + status if status else '')


EDIT_RULES = '''Do not reproduce a section you are not changing: every section not named in
`patch` carries over from the base plan exactly as it already is. Output is the cost of this
stage, so change as little text as the finding needs. `patch` has three optional arrays:

- `replace_text` (use this first): `[{"heading": "<exact existing heading>", "old": "<text copied
  exactly from that section, unique within it>", "new": "<what replaces it>"}]`. Changes a sentence,
  a table row, a command or a line without rewriting the section; `"all": true` replaces every
  occurrence. Most findings are this small. Copy `old` exactly as the base plan has it; if it is
  missing or occurs more than once the delivery is rejected.
- `edit_sections` (only when most of a section changes): `[{"heading": "<exact existing heading, copied verbatim from
  the list below>", "content": "<the section's whole new body, heading line
  excluded>"}]`. Replaces one existing section's body in full. If the heading
  is `Implementation sequence`, every step in the new body still ends with
  `Owns:` (and `Depends on:` where one step needs another finished first) --
  the base plan's steps you are not otherwise changing keep the exact `Owns:`/
  `Depends on:` they already have; do not drop or loosen them while rewriting
  the section for the finding at hand.
- `insert_sections`: `[{"content": "<a whole new section, its own \\"## \\"
  heading line included>", "after": "<an existing heading to insert after>"}]`.
  Use `"before"` instead of `"after"` to insert before that heading, or
  `"position": "start"` to insert first; omitting all three appends at the end.
  Only for content that plainly does not belong in any existing section --
  prefer `replace_text` (or `edit_sections`) whenever the change extends one that already exists.

Never add a `Depends on:` to an implementation step to make one file match another's contents: steps run
at the same time, and every dependency adds a whole step's time (25-35 s) to the stage. Fix the interface in the
plan instead (the export name, the shape of the data, the file path the other step uses) so both steps can be
written at once, and add a dependency only when a step truly cannot be written before another's output exists.

Never add a section that "overrides", "supersedes" or "amends" other sections. Implementation
reads each section on its own, so a change to a step, an invariant, a test or a command that
lives in an addendum is a change nobody applies. Change the step, row or paragraph itself with
`replace_text` or `edit_sections` on the section it belongs to -- the step, row or paragraph itself,
not a note beside it.'''


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
                         'required top-level strings, even when unchanged.\n\n'
                         '`protected_verification_paths` names test and source files the '
                         'implementation must not edit -- never anything under `.uncle/`, which is '
                         'workflow bookkeeping, not a file under test, and is a rejected delivery if '
                         'listed. One repository-relative path per line, not comma-separated. Example: '
                         '`src/calc.js\\nsrc/calc.test.js\\ne2e/calc.spec.js`.')
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
{"schema":"uncle.artifact/v1","kind":"%s","dispositions":[{"finding":"AR-001","disposition":"Accepted","reason":"...","plan_change":"..."}],"patch":{"replace_text":[{"heading":"...","old":"...","new":"..."}],"edit_sections":[],"insert_sections":[]}}
```

%s

Every disposition's `plan_change` must be reflected by some `patch` entry: a
disposition with no matching edit or insert is a rejected delivery. The
disposition fields are finding, disposition (Accepted, Partially accepted,
Rejected, or Deferred), reason, and plan_change. `reason` and `plan_change` are one
sentence each (300 characters at most); `plan_change` may simply name the section the
patch edits. Do not write Markdown, a
summary, a draft, or progress commentary, and do not write a `narrative` key.

Once you have written the delivery file, you are done: stop immediately.
There is no operator here to answer a question or approve a next step, and
nothing you write after delivery is read. Do not summarize what you wrote, do
not propose implementation steps, do not ask what to do next -- any of that
is pure generation time spent on a reply nothing will ever see.

## Existing sections in the base plan, in order

Quote a heading exactly, as printed here, to edit it or to anchor an insert.

%s

## Base project plan JSON
```json
%s
```

## Adversarial review findings (every finding, condensed)

%s

## Collated specialist corrections (condensed)

%s
''' % (label, artifact, plan['kind'], extra_fields, example_kind, EDIT_RULES, headings,
       json.dumps(plan, indent=2, sort_keys=True),
       review_table(review),
       corrections_table(workers))


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
