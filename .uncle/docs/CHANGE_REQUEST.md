# Change Request

Issue 228

Seeded from [unclehq/uncle#228](https://github.com/unclehq/uncle/issues/228).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Fix failing tests so the full suite passes 100% green

## Motivation

## Problem

`./scripts/run-all-tests.sh` does not pass. Latest run on `main` (4c23afa): **96 passed, 11 failed, 0 skipped**. Goal: every suite green, with no skips and no weakened tests.

## Failing suites

- `scripts/tests/worktree-run-test.sh` (shards #3of4, #4of4): many checks fail with `expected exit 0, got 127` (command not found), so the cause is probably an environment or PATH assumption. Needs confirming.
- `scripts/tests/attestation-statement-test.py` (shards #1of3, #2of3, #3of3):
  - `test_not_ready_audit_with_driver_override_never_publishes`
  - `test_gitignore_boundary`
  - `test_final_audit_writes_audit_and_release_envelopes`
- `scripts/tests/early-branch-test.py`: `test_t1_unknown_default_defers_without_guessing`, `test_t3_non_default_current_branch_is_the_head`, `test_t4_divergent_candidate_ref_is_never_overwritten`, `test_t5_unavailable_contexts_skip_without_journal_or_ref`, plus 1 error
- `scripts/tests/supervisor-test.py`: `test_every_fixture_commit_and_tag_disables_signing`
- `scripts/tests/unattended-test.sh`: `sg-version-flag` (expected `0.1.0`, got empty) and `stagegate-help` (`--unattended` not documented in `--help`)
- `scripts/tests/home-actions-test.py`: 2 errors
- `gates-verification-integrity`, `gates-verification-integrity-2`, `gates-verification-integrity-4`: workflow sits in `IMPLEMENT` where the tests expect `REPAIR`, `COMPLETE` or `VALIDATE_TEST_REVIEW` (`sg-repair-*`, `sg-review-cannot-bless-failed-command`, `sg-missing-driver-results-block`, `sg-verifier-rewrites-test`, `sg-command-rewrites-test`, `sg-approved-parallel-checks`, `sg-invalid-parallel-plan`)

The first run printed the failing suites above, and a second run printed the individual `FAIL` lines. Re-run to get current output, since the list may shift.

## Requirements

- For each failure, decide whether the product or the test is wrong. Fix the root cause.
- Do not weaken, delete or skip tests, and do not loosen assertions to get green. Any test change needs a requirement-based explanation.
- Separate environment-dependent failures (for example exit 127) from real defects. Make the tests self-contained or have them fail with a clear prerequisite message.
- Fix the `--version` and `--help` regressions in `stagegate.sh`.

## Definition of done

- `./scripts/run-all-tests.sh` exits 0 with `0 failed, 0 skipped` on a clean checkout of `main`.
- Failures that were not code defects are documented in the PR.

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
