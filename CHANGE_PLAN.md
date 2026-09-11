# Change plan
| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | Absence checks permit concurrent overwrite. | Selected technical approach; Exact components to modify; Compatibility strategy; Concurrency implications; Automated-test strategy; Scope cuts under time pressure; appended scope, acceptance and checks |
Omitted sections: none

## Selected technical approach
P-1: Plan: exclusively create absent requirements in C-1 with existing `brief` plus newline; retain existing-file handling.

## Alternative approaches considered
| ID | Approach | Disposition |
|---|---|---|
| A-1 | Copy template | Reject: deployment dependency |
| A-2 | Change routing | Reject: launchers already forward --new |

## Why the selected approach is preferred
P-2: Plan: reuse C-1 heredoc; no template dependency.

## Exact components to modify
Entries are planned.

| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| C-1 `scripts/from-issue.sh:write_new_project_brief` | Add exclusive absent-target creation | AC-1/AR-001 | Existing-file overwrite | T-1–T-4/T-6 |
| C-2 `scripts/tests/issue-project-root-test.sh` | Extend fixtures and collision barriers | B-1/B-2/AR-001 | Leakage | T-1–T-4/T-6 |
| C-3 `scripts/tests/menu-input-test.py` | Assert --new forwarding | Entry path | Stubs | T-5 |
| C-4 `scripts/README.md` from-issue section | Document creation/refusal | B-1 | Staleness | M-1 |

## Components explicitly not to modify
P-3: Protect `uncle`, `uncle_tui.py`, drivers, `scripts/lib/`, packaging, repository `REQUIREMENTS.md`, and C-1 fetch/change/mode logic.

## Data-flow changes
P-4: Plan: parsed issue → C-1 brief → selected project's requirements.

## State-transition changes
P-5: Plan: absent → seeded → exit 0; no state/run/close, even unattended.

## Interface and API changes
P-6: Plan: creation message; flags/hint unchanged.

## Schema or persistence changes
P-7: Markdown only.

## Compatibility strategy
P-8: Plan: preserve markerless refusal/prefix handling; absence requires `! -e` and `! -L`. Create with O_EXCL semantics; refuse collisions nonzero without truncation, symlink traversal, success output, or fallback to replacement.

## Concurrency implications
P-9: Plan: exclusive creation selects one absent-target writer; losers follow P-8. No workflow-wide lock; existing-marker concurrency unchanged.

## Error and recovery behavior
P-10: Plan: retain CHANGE_SPEC.md error contract; success only after write. Inspect partial files before retry; no auto-delete.

## Migration plan
P-11: None; no bulk rewrite.

## Rollback plan
P-12: Revert C-1–C-4 changes; keep generated requirements; rerun T-4/T-5. B-1 reverts to failure.

## Feature-flag or containment strategy
P-13: New-mode absent target only; no flag.

## Automated-test strategy
IDs reference CHANGE_SPEC.md.

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AC-1 | B-1 | I-1/I-4/I-5 | C-1/C-2 | T-1: absent, exit 0, title/body/URL/headings; install/change sentinels preserved; P-5 | M-1 |
| AC-2 | B-2 | I-1 | C-1/C-2 | T-2: prefix/tail/reseed; markerless/directory/dangling link refused unchanged | M-1 |
| Error contract | Failure | I-1 | C-2 | T-3: fetch/parse/write errors nonzero; no success | M-1 |
| AC-3 | B-3/B-4/B-5 | I-2/I-3 | C-2 | T-4: change+EOF; auto request/code/fresh; close-flow | M-1 |
| AC-1 | B-1 | I-1 | C-3 | T-5: shell n/TUI new forward --new | M-1 |
| AR-001 | B-1 | I-4 | C-1/C-2 | T-6: barrier after absence check, before creation; insert markerless file, symlink to sentinel, or dangling symlink; resume; require nonzero, unchanged bytes/link, dangling referent absent, no success/run/close | M-1 |

P-14: T-1 fails before fix, passes afterward; mock gh/curl; record driver/close calls.

## Regression-test strategy
P-15: Plan: run `bash -n uncle scripts/from-issue.sh`, `bash scripts/tests/issue-project-root-test.sh`, `PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/menu-input-test.py -q`, and `PYTHONDONTWRITEBYTECODE=1 bash scripts/tests/close-flow-test.sh`; require exit 0.

## Manual-verification strategy
M-1: Plan: scratch project, mocked fetch, shell/TUI issue → new; inspect output/files; repeat with marker/markerless files.

## Observability changes
P-16: P-6 only.

## Implementation sequence
| ID | Planned step |
|---|---|
| S-1 | Add C-2/C-3 tests; record T-1 baseline failure |
| S-2 | Implement P-1/P-8 in C-1; update C-4 |
| S-3 | Run P-15 and M-1; inspect diff against P-3 |

## Scope cuts under time pressure
P-17: Retain exclusive creation and all checks; defer workflow-wide locking.

## Risks and unresolved questions
R-1: ASSUMPTION: C-1 brief alone meets I-5; driver validation unrun. Settle by reviewing T-1 output against `REQUIREMENTS.md` guidance.
R-2: BASELINE_REPORT.md U-1 needs reporter steps.

## Frozen change scope
FS-1: Plan: C-1–C-4 only, implementing AC-1–AC-3 and AR-001; P-3/P-13 bound behavior.
## Files expected to change
FE-1: Plan: only the four paths in C-1–C-4.
## Files that must not change
FN-1: Plan: protect all other paths, including P-3 and workflow documents.
## Expected behavioral differences
BD-1: Plan: B-1 in CHANGE_SPEC.md plus P-8 collision refusal.
## Expected unchanged behavior
BU-1: Plan: CHANGE_SPEC.md B-2–B-5, I-2/I-3 and error contract; P-5/P-6/P-8.
## Exact acceptance criteria
| ID | Planned pass condition |
|---|---|
| AC-1 | T-1/T-5 pass; R-1 settled against generated headings. |
| AC-2 | T-2 passes. |
| AC-3 | T-4 passes. |
| AR-001 | Every T-6 collision passes; losing writer never replaces the inserted entry. |
| AC-4 | T-3, P-15 and M-1 pass; diff limited to FE-1. |
## Pre-implementation checks
PC-1: Plan: inspect C-1 creation primitive for O_EXCL semantics; implement T-6 barriers in test-only copies without sleeps or production hooks; verify collision injection before releasing writer.
## Post-implementation checks
PC-2: Plan: run P-15/M-1; record T-6 barrier and exit evidence; inspect diff against FN-1.
## First features to cut if time expires
FC-1: Plan: P-17 only; no acceptance criterion is optional.
## Conditions that require stopping implementation
ST-1: Plan: stop if R-1 remains unsettled, exclusive creation cannot be guaranteed, any acceptance check fails, or implementation requires paths outside FE-1.
