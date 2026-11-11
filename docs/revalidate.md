# Revalidating a finished build (`uncle --revalidate`)

`uncle --revalidate` answers "is this project still good, and what needs redoing?" without starting a run. It compares the
project with its attestation (`.uncle/attestation.json`) and prints, for each stage, whether the stage can be **reused** or
must be **re-run**.

```
$ uncle --revalidate
UNCLE REVALIDATION

changed since the attestation: README.md
1 of 1 changed file(s) are documentation that no stage reads as an input

✓ requirements                     reused  inputs unchanged; last passed
✓ plan                             reused  inputs unchanged; last passed
✓ adversarial review               reused  inputs unchanged; last passed
✓ implementation                   reused  inputs unchanged; last passed
✓ verification (build and tests)   reused  inputs unchanged; last passed
✓ final audit and manual checks    reused  inputs unchanged; last passed

○ attestation is stale: it covers tree 5f8f…60e2 and the project is now 890d…ba35. Refresh it or record the change;
  this does not by itself re-run any stage.
6 stage(s) reused, none re-run.
```

## What this version does

It **reports**; it does not run stages. Re-running a stage means running a driver, so a report that finds work to do ends with
the command that does it (`uncle --audit` for the final audit, `uncle --change-request --attended` for the full change flow).
Nothing is written: no approval, no attestation, no workflow state.

Exit codes: `0` every stage reusable; `1` at least one stage must be re-run; `2` there is no attestation to compare with.

Options: `--attestation PATH` to use another attestation, `--tree TREE` to compare a commit instead of the working tree
(uncommitted edits are included by default), `--dry-run` (accepted; this version never executes a stage).

## How a stage is judged

| Rule | |
|---|---|
| R-1 | A stage is reused only if every input it reads is identical to the last passing run. When unsure, it re-runs. |
| R-2 | A changed test or other protected verification file is reported as a change needing review, never as reusable. |
| R-3 | A stage that did not pass last time (`fail` in the attestation) is never reused. |
| R-4 | A changed input re-runs that stage and every stage after it. |
| R-5 | Revalidation writes nothing. |

The baseline is what the attestation recorded: the sha256 of each stage's approved documents, and the filtered git tree the
verification and audit judged (the same tree `uncle verify` compares). A changed project file is sorted into:

- **documentation** (`README*`, `CHANGELOG*`, `LICENSE*`, `*.md`, `*.rst`, images under `docs/`): no stage reads it, so nothing re-runs;
- **tests** (`tests/`, `*.test.*`, `*.spec.*`, `playwright.config.*`, and anything in `.uncle/workflow/verification.paths`): re-runs verification and the audit, flagged for review;
- **source**: anything else, including configuration, lockfiles and unknown files. Re-runs verification and the audit.

A changed approved document (for example `PROJECT_PLAN.md`) re-runs the stage that wrote it and everything after.

## Limits

- It trusts the attestation as a baseline; it does not check its signature. Run `uncle verify` for that.
- If the attested tree is not in the repository (for example the build ran in another worktree), nothing can be compared and
  verification and the audit are reported as needing a re-run.
- It does not yet execute stages or refresh the attestation (issue #243 tracks that).
