# Change Request

Issue 172

Seeded from [unclehq/uncle#172](https://github.com/unclehq/uncle/issues/172).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Let the classifier skip adversarial review for docs, test-only and small builds

## Motivation

## Problem

Every build runs the adversarial review, even a docs-only, test-only or small change. The classifier (`scripts/lib/change-class-stage.sh`, `prompts/classify-change.md`) already picks a class and trims review lenses, but `profile()` in `scripts/lib/change_class.py` never goes below `requirements` + `regression`, so a trivial change still pays for a review panel and a primary reviewer.

## Proposal

Let the classifier decide that a build needs no adversarial review, for the classes `docs`, `test-only` and `small` only (the existing `REDUCIBLE` classes).

1. The classifier may return `review: skip` for those three classes only.
2. A deterministic floor in `change_class.py` rejects the skip when any of these is true: `risk_hits` is non-empty (security, secrets, signing, publication, approval gates, deletion, migrations, concurrency); the floor raised the class above the model's; the plan touches non-doc, non-test paths for a `docs` or `test-only` class.
3. A skipped review still writes a stub `ADVERSARIAL_REVIEW` artifact that says "skipped: class <class>, no risk hits" and has zero findings. It goes through the normal approval gate, so the state machine, hashes, envelopes and `plan-gate` keep working, and the human can see the skip and decline it.
4. Fail closed: a classifier failure, bad answer, or disabled classifier (`WORKFLOW_CLASSIFY=0`) runs the full review, as today.
5. An off switch (for example `WORKFLOW_SKIP_REVIEW=0`) and a record of the decision in the cost ledger and run record.
6. Both drivers: `scripts/stagegate.sh` and `scripts/change-workflow.sh` each have their own review flow.

## Observable behaviors

- Docs-only change with no risk hits: review panel and primary reviewer do not run; the stub review reaches the approval gate with a visible "skipped" reason.
- Small change that mentions deletion, signing or approval gates: full review runs.
- Classifier runner fails: full review runs.

## Invariants

- A skip never happens when `risk_hits` is non-empty.
- A skipped review is always visible at the human gate and recorded.
- The human plan-approval gate and the final audit are unchanged.

## Failure behavior

Any uncertainty runs the full review. A stub that fails validation stops the run, as a bad review does today.

## Verification

- docs plan skips; small plan with a risk keyword does not; classifier failure runs the review.
- Stub passes `VALIDATE_ADVERSARIAL_REVIEW`, approval and attestation checks in both drivers.
- `WORKFLOW_SKIP_REVIEW=0` restores the full review.

## Risks

- For a new app, `small` ("a handful of requirements, no sensitive behavior") rests on the model's judgment plus the floor. A misjudged small app would ship without adversarial review; the human plan-approval gate is the remaining check.
- The updated-plan stage must accept a review with no findings.

## Non-goals

- Skipping the final audit, the human gates, or reviews for `standard`, `large` and `risky` classes.

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
