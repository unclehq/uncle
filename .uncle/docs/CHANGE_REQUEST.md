# Change Request

Issue 267

Seeded from [unclehq/uncle#267](https://github.com/unclehq/uncle/issues/267).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Updated plan stops with "writer attempts exhausted" after every writer succeeded, because the plan's check scripts aren't recognised as test files

## Motivation

## What happened

A hosted, unattended build (self-hosted delivery, Claude Sonnet 5 through an OpenAI-compatible chat route) was asked for a small Haskell hello-world command-line app with a one-page tutorial README. It stopped in `UPDATED_PLAN` and published nothing:

```
updated-plan ops: 5 overlapping group(s); they need one resolver call
[+00:16:02] Updated-plan edits overlap; one small resolver call per overlapping group, all at once.
updated-plan ops: no writer supplied protected_verification_paths, and the plan names no test files to protect
Updated-plan writer attempts exhausted; completed packets retained for diagnosis.
updated-plan: writer attempts exhausted
uncle --noui: driver exited with status 1
```

By then every edit writer had delivered a valid packet: writers 1, 3 and 5 first time; 2-1, 4-1 and 4-2 on the one-finding retry; 2-2 on the last try by the other delivery path. All five resolvers (G1–G5) also succeeded. The stage stopped in the merge, not in a writer.

## Cause

1. The plan Uncle approved came from the single-pass Markdown fallback (`Project plan: the typed (JSON) sectioned plan did not complete; falling back to the single-pass Markdown plan`). Its `PROJECT_PLAN.json` has no `protected_verification_paths` (the field is `null`).
2. No writer supplied the field, so the merge derives it from the plan: [`scripts/lib/updated_plan_ops.py#L947`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/updated_plan_ops.py#L947) raises `Conflict` when that derivation is empty.
3. The derivation recognises test files only by name or directory: [`scripts/lib/updated_plan_fast_path.py#L71-L91`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/lib/updated_plan_fast_path.py#L71-L91). This plan's `verification_commands` run `scripts/check-ghci-exercises.sh`, `scripts/check-launch.sh` and `scripts/run-defects.sh`, and its test table also names `scripts/check-run.sh`. None of those names matches `TEST_NAME`, and `scripts/` is not in `TEST_DIRS`, so the plan "names no test files".
4. [`scripts/stagegate.sh#L3119`](https://github.com/unclehq/uncle/blob/c5815a928b746ae322d7b6a1d813074e719f7bc5/scripts/stagegate.sh#L3119) turns any merge failure into `workflow_writer_exhausted`. The stop reason therefore says "writer attempts exhausted", and the agent relaying the build reported a writer/format failure instead of the merge refusal.

## Requested fix

1. When the plan names no test files by name, treat the repository files its `verification_commands` execute (here `scripts/check-ghci-exercises.sh`, `scripts/check-launch.sh`, `scripts/run-defects.sh`) as the protected paths instead of stopping the stage.
2. Have the single-pass Markdown plan fallback produce `protected_verification_paths`, as the typed plan path does, so the updated plan is not left to derive them.
3. Give a merge refusal its own stop reason (for example `updated-plan: merge conflict: <message>`) instead of "writer attempts exhausted".

## Workaround until then

A plan whose checks sit under `test/` or `tests/`, or are named like tests (for example a cabal test suite at `test/Spec.hs`), passes this check.

Checked against `main` at `c5815a928b`; the cited lines are unchanged there.

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
