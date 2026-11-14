# Change Request

Issue 272

Seeded from [unclehq/uncle#272](https://github.com/unclehq/uncle/issues/272).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Hosted new-app builds never qualify as small: requirement counts read R-n/D-n ids the self-hosted interpretation doesn't have, so a hello-world app runs as large

## Motivation

## What happened

A hosted, unattended build (self-hosted delivery, Claude Sonnet 5) was asked for a hello-world app with a quick one-page interactive tutorial. The result is 156 lines across 4 files (`index.html`, `src/main.js`, `src/steps.js`, `src/tutorial.js`). Uncle classed the build `large` and ran its full process:

- a 46,143-character project plan
- 4 adversarial review lenses and full test scope
- 3 test-review lenses, 4 checklist lenses and 4 final-audit lenses
- a repair round

The build took about 37 minutes and about $16 of model usage, and it ended `NOT_READY`.

`change-class.json` from the build:

```
"class": "large", "source": "plan-recheck", "floor_class": "large",
"rationale": "Raised from standard to large: the plan (7 steps, 13 files) is larger than the standard class allows.",
"features": { "family": "app", "request_chars": 759, "plan_chars": 46143, "steps": 7, "owned_files": 13,
              "file_kinds": {"test": 4, "docs": 0, "scaffold": 4, "app": 5}, "criteria": 0, "requirements": 0, "risk_hits": [] }
```

Note `"requirements": 0` and `"criteria": 0`. The approved interpretation had 4 required-functionality items and 4 definition-of-done rows.

## Cause

1. In hosted builds, the requirements stage takes the self-hosted path ([`scripts/stagegate.sh#L4819-L4835`](https://github.com/unclehq/uncle/blob/9255d7e687614cfdb36a01a99cdd86c12a40f49b/scripts/stagegate.sh#L4819-L4835)). It copies the investigation as `REQUIREMENTS_INTERPRETATION.md` and renders the JSON from it ("Requirements fast path"). The investigation writes `required_functionality` as plain bullets and `definition_of_done` as a table, with no `R-n` or `D-n` ids.
2. `interpretation_counts` counts only `R-\d+` and `D-\d+` ids ([`scripts/lib/change_class.py#L226-L230`](https://github.com/unclehq/uncle/blob/9255d7e687614cfdb36a01a99cdd86c12a40f49b/scripts/lib/change_class.py#L226-L230)), so it returns `(0, 0)`.
3. `app_is_small` requires `0 < requirements` and `0 < criteria` ([`#L263-L269`](https://github.com/unclehq/uncle/blob/9255d7e687614cfdb36a01a99cdd86c12a40f49b/scripts/lib/change_class.py#L263-L269)), so a small app is never `small` on this path.
4. Not being `small`, the plan is written at full length, without `PLAN_TARGET` or `PLAN_WORD_SCALE`. This plan reached 7 steps and 13 files, 8 of them tests and scaffolding the plan added itself. `deterministic_class` then raised it to `large` ([`#L282`](https://github.com/unclehq/uncle/blob/9255d7e687614cfdb36a01a99cdd86c12a40f49b/scripts/lib/change_class.py#L282)).

So every hosted new-app build skips the small class, however small the request.

## Requested fix

1. Count the interpretation's items in a way that doesn't depend on ids: bullet items under `required_functionality` and table rows under `definition_of_done`. Alternatively, make the self-hosted investigation path assign `R-n`/`D-n` ids the way the other requirements paths do.
2. When an interpretation exists but its counts come back 0, treat them as unknown and log it, instead of silently ruling out `small`.
3. For the `large` check on new apps, consider not counting test and scaffold files toward `owned_files` and `steps`. A plan that adds its own test harness shouldn't push a small app into the heaviest class.
4. Add a test: a self-hosted-path interpretation for a hello-world app with 4 bullets and 4 done rows classes as `small`.

Related: #245 (no overall time or spending limit for unattended builds).

## Observed Current Behavior

Describe what the system currently does.

## Desired Behavior

Describe what the system should do after the change.

## Reproduction

For a bug, provide exact steps to reproduce it.

For other change types, write "Not applicable."

## Constraints

List compatibility, security, performance, timing, or scope constraints.

## Known Relevant Files

List files or components if known.

## Out of Scope

List behavior or components that must not be changed.

## Success Criteria

Describe the observable evidence that proves the change works.
