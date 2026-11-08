# Add --audit command to uncle

## Change Type
Feature (new CLI command).

## Summary
Add an `--audit` command to the `uncle` CLI so the auditor can be rerun on a branch.

## Motivation
The operator wants to rerun the auditor on a branch without redoing the whole workflow.

## Observed Current Behavior
None stated. There is no `--audit` command. How the auditor is currently run is not yet established; the workflow should inspect the code to find out.

## Desired Behavior
Running `uncle --audit` reruns the auditor on a branch. Which branch is used when none is given, and how a branch is named, are to be settled in planning (see below).

## Reproduction
Run `uncle --audit`. Today the command does not exist.

## Constraints
Follow existing CLI conventions in the repository. Do not change existing commands or the behavior of the auditor itself.

## Known Relevant Files
None identified yet; to be found during baseline analysis (CLI entry point `uncle`, auditor code under `lib` or `scripts`).

## Out of Scope
Changes to what the auditor checks, other new commands, and unrelated cleanup.

## Success Criteria
`uncle --audit` exists, runs the auditor on a branch, reports the auditor's result, and fails with a clear message when it cannot run. Existing tests still pass and new tests cover the command.

## Open Questions
How is the auditor invoked today? Does `--audit` take a branch argument, or default to the current branch? Where does the audit output go (for example FINAL_AUDIT.md)?