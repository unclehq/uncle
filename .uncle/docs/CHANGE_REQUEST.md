# Change Request

Issue 243

Seeded from [unclehq/uncle#243](https://github.com/unclehq/uncle/issues/243).

## Change Type

Feature | Bug Fix | Prototype | Refactor | Performance | Security | Upgrade

## Summary

Add 'uncle --revalidate': re-check a project and re-run only the stages whose inputs changed

## Motivation

## Summary

Add `uncle --revalidate`: re-check a project that Uncle already built, and run only the stages whose inputs changed since they last passed. Stages with unchanged inputs are reused, with the reason shown.

## Why

Today the only ways to get a project checked again are to resume a run at its parked state, or to start over. Both are blunt:

- A resume re-runs from wherever the run stopped. It can't tell that, say, only `src/style.css` changed since the last green check.
- Starting over spends a full build, and discards the reviews and approvals already done.
- After a hand edit, a merge, or an Uncle upgrade, there is no way to ask "is this project still good, and what needs redoing?"
- `uncle verify` checks the attestation (signature, approvals, tree match). It doesn't re-run anything.

Seen on a real build: a fix to the mutation runner meant only the mutation step and test review needed redoing, but the options were resume-and-hope or rebuild everything.

## Proposed behavior

`uncle --revalidate [--noui] [--attended]`, run from a project root that has `.uncle/` state.

1. **Fingerprint each stage's inputs.** For every stage, record a hash of what it read (the approved documents, the files it owns or checks, the protected verification paths, the stage's prompts or runner version, its config). Store it with the stage's result when the stage passes.
2. **Compare on `--revalidate`.** Recompute each stage's input hash. A stage whose hash matches its recorded passing hash is skipped and reported `unchanged (last passed <time>)`. A stage whose hash differs is re-run, and so is everything downstream of it.
3. **Print a plan first.** List which stages will re-run and why (which input changed) and which are reused. `--dry-run` stops there.
4. **Keep the human gates honest.** A re-run that changes an approved document or the diff reopens the gate. Revalidation never records an approval itself.
5. **Report.** End with per-stage results (`reused`, `passed`, `failed`) and a non-zero exit if anything failed.

### Required example: a documentation-only change

A change to `README.md` (or any file no stage reads as an input) must revalidate **without a full run**:

- `uncle --revalidate` fingerprints the project, sees that only `README.md` differs from the last passing state, and re-runs only the stages whose inputs include it. If no stage reads it, nothing re-runs.
- It still checks the things a README edit does affect: the head tree no longer matches the attested release artifact, so the attestation has to be refreshed or the change recorded, and any stage that does read `README.md` (for example a docs or acceptance check) runs.
- It does **not** re-run the plan, the adversarial review, the test review, the unit or browser tests, or the mutation checks. They are reported `unchanged`.
- The output says why: `README.md changed; 0 stages read it; 9 stages reused`.

This is the acceptance case for the whole feature. If a README edit triggers a full run, the stage input hashes are too coarse.

## Existing pieces to build on

- `green-check.fingerprint` already skips an unchanged green check in `change-workflow.sh`.
- `verification.manifest` and the protected-path hashes already detect changed tests.
- Approval records already store a `.sha256` of what was approved.
- `uncle verify` already compares the attested tree to `HEAD`.

## Invariants

- **R-1:** a stage is reused only if every input it reads is byte-identical to the last passing run. When unsure, re-run.
- **R-2:** a changed protected verification file is reported as a change needing review, never silently re-baselined.
- **R-3:** a reused stage never turns a failed or blocked stage into a pass. Only stages with a recorded pass can be reused.
- **R-4:** changing an input re-runs that stage and every stage after it.
- **R-5:** `--revalidate` writes no approval and no attestation. Those stay with the gates and the existing publish step.

## Failure behavior

- No `.uncle/` state or no recorded passing runs: say so and exit non-zero without running anything.
- A stage with no recorded input hash (older runs): treat as changed and re-run it, saying why.
- A model or credit failure mid-run: stop cleanly, keep the reused results, and make the next `--revalidate` pick up where this one stopped.

## Verification

- Unit tests for the fingerprint function: same inputs give the same hash, and each kind of input (file, document, prompt, config) changes it.
- A fixture project with recorded passes: edit one source file and assert exactly the dependent stages re-run.
- A defect-injection check: change a protected test file and assert it is flagged, not skipped.
- `--dry-run` prints the plan and changes nothing on disk.
- **README acceptance test:** on a fixture project with recorded passes, change only `README.md` and assert zero model calls, zero test-command runs, and every stage reported `unchanged`, with the tree-mismatch reported separately. Then change a file a stage does read and assert exactly that stage and its dependents re-run.

## Open questions

- Which inputs define each stage's hash, and how are downstream dependencies declared?
- Should an Uncle version change count as a changed input for every stage, or only for stages whose prompts or runners changed?
- How does this interact with attended mode: does a re-run stage always re-open its human gate?
- Should `--revalidate` also offer a one-shot fix mode for known driver-supplied files (for example the mutation runner)?

## Non-goals

- Replacing `uncle verify`.
- Rebuilding or rewriting code.
- Editing approved documents or approvals.

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
