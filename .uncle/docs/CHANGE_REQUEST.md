# Change Request

Issue 248

Seeded from [unclehq/uncle#248](https://github.com/unclehq/uncle/issues/248).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Record the exact command, environment and output with each verification result, and let review rerun it

## Motivation

## Problem

Uncle's attestation says *what* each verification command returned, but not enough to show the result came from the command and tree it names, or to let a reviewer confirm it without trusting our word. A captured test run can show `exit=0` that is really the exit code of a `tail` or `tee` the output was piped through, and the record looks the same whether the tests passed or not. Uncle should make that class of mistake impossible to miss and cheap to check.

## What Uncle does today (read at `main`)

- `scripts/lib/green-check.sh` runs each approved command as `bash -o pipefail -c "$cmd"`, then writes `<status>\t<command>` to `green-check.tsv`. Good. But the command is wrapped by `shell_syntax.py` and `run_check.py` first, and the pipefail guarantee is only visible in `shell_syntax.py`'s own branch. Nothing tests that a piped command such as `false | tail` fails through the wrappers.
- `scripts/lib/build_attestation.py` writes a stage as `unavailable`, never `pass`, when it has no record. Good, and this is the rule worth keeping. It does not cover a check that ran but whose exit status is not trustworthy.
- The `verification` envelope records a summary string (`N commands: X pass, Y pre-existing, Z regressed`), the tree hash as `inputs.artifact`, and a digest of `green-check.tsv` plus `AUTOMATED_TEST_REPORT.md`.
- `verification` is a driver-written claim. `uncle verify` checks the signature and hashes; it does not run the commands again.

## Gaps

1. **No environment record.** The envelope has no OS, architecture, tool versions (node, python, npm, browsers), no relevant environment variables, no working directory, no timeout in force and no per-command duration. Two runs of the same command on the same tree hash can differ in ways the record cannot show.
2. **The commands ran on a copy, not the attested tree.** `isolated_verify.py` runs them in a private copy with the project's port moved. The envelope's `inputs.artifact` is the real tree's hash. The record doesn't say the commands ran on a modified copy, or how it differed.
3. **Output is not bound to the result.** `green-check.tsv` has the status and command only. The captured output log is not digested into the envelope, so a status can't be matched to the output it came from.
4. **No cross-check of the exit status.** Nothing records whether a command's status came from its own process or from a wrapper, and nothing flags a command whose pipeline masks failures.
5. **Review reads the record.** The reviewing step trusts `green-check.tsv`. It does not rerun the suite itself.

## Proposal

1. **Per-command record** in a new `green-check.json` (kept next to `.tsv`): exact command string, argv as run (after wrappers), cwd, exit status, `PIPESTATUS`/pipefail setting in force, start time, duration, timeout, and a sha256 of that command's captured output. Digest this file as envelope evidence, not just the `.tsv`.
2. **Environment block** in the `verification` envelope: OS and architecture, versions of the tools the commands invoke (at least node, npm, python3, bash, git and any browser driver), the allow-listed environment variables Uncle sets or unsets, and the config values that change behaviour (`WORKFLOW_CHECK_TIMEOUT_SECONDS`, the CPU jobs count).
3. **Say what tree ran.** When `isolated_verify.py` runs commands in a copy, record that, with the tree hash of the copy and the list of rewrites (the moved port). A hash that differs from `inputs.artifact` is stated, not hidden.
4. **Unavailable, not pass, for untrustworthy status.** If a command's status can't be tied to its own process (wrapper failed to start, output log missing, status file missing), the stage is `unavailable` with the reason, never `pass`. Add a test that `false | tail` and `false | tee file` fail through every wrapper.
5. **Independent rerun at review.** Add `uncle verify --rerun`: check out the attested tree, run the recorded commands with the recorded environment constraints, and compare status and output digest against the record. Report a mismatch (including environment differences) instead of passing. The final-audit stage should use it rather than reading the transcript.
6. **Tests.** Each new field gets a test that fails when the field is removed, in the style of the existing `host-preview-test.py` and `headless-preview-open-test.py`.

## Questions

- Which environment variables are safe to record? Anything that can hold a credential must be excluded by allow-list, not filtered after the fact.
- Should `--rerun` be part of `uncle verify` by default for builds Anya Sharp opens pull requests for, so a hirer can see the rerun result in the pull request?

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
