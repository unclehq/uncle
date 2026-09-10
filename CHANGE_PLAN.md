# CHANGE_PLAN.md
| Finding | Disposition | Reason | Exact plan change |
|---|---|---|---|
| AR-001 | Accepted | External link content is not audit-bound. | Data-flow changes; Automated-test strategy |
| AR-002 | Accepted | A reference supplies no steps. | Data-flow changes; Automated-test strategy |
| AR-003 | Accepted | Comment contract remains blocking. | Risks and unresolved questions; Manual-verification strategy; Conditions that require stopping implementation |
| AR-004 | Accepted | Embedded terminators truncate defaults. | Interface and API changes; Automated-test strategy |
| AR-005 | Accepted | Producer permits purpose prose. | Data-flow changes; Automated-test strategy |
Omitted sections: none

## Selected technical approach
P-1: Plan defaults in C-1:handoff.
P-2: Preserve title_default() (BASELINE_REPORT.md B-2/P-3).

## Alternative approaches considered
| ID | Approach | Disposition |
|---|---|---|
| A-1 | Refetch title | Reject: network |
| A-2 | Agent | Reject: dependency |
| A-3 | Auto-publish | Reject: consent |

## Why the selected approach is preferred
P-3: Reuse C-1:ask()/journal.

## Exact components to modify
Planned path aliases.
| Component | Planned change | Reason | Regression risk | Test coverage |
|---|---|---|---|---|
| C-1 `scripts/lib/change-pr.sh` | Defaults | B-3 | Content | T-1 |
| C-2 `uncle_tui.py:_detect_prompt` | Default prefixes | AR-2/3 | Parsing | T-2 |
| C-3 `scripts/tests/close-flow-test.sh` | Fixtures | AR-1/3 | Drift | T-1 |
| C-4 `scripts/tests/pr-prompt-test.py` | Cases | AR-2 | Prompts | T-2 |

## Components explicitly not to modify
P-4: Protect BASELINE_REPORT.md P-1/P-3, `scripts/lib/issue-close.sh`, README files and spec §15 exclusions.
P-5: Preserve C-1 audit/identity checks; unrelated edits.

## Data-flow changes
P-6: Plan: read notes/checklist only from regular blobs (100644/100755) in C-1 journal commit_tree; absent/symlink sources are unusable. Extract three Purpose cells from IMPLEMENTATION_NOTES.md or three nonempty entries under “purpose of each change”.
P-7: Plan: semicolon-join; normalize controls/whitespace; cap summary at 480 characters. Without completed-work content require typed summary; retain title_default() for title only.
P-8: Plan: extract up to three complete action/expected-result pairs from MANUAL_CHECKLIST.md tables or labeled check blocks; normalize as P-7. Without usable pairs require typed steps; headings/references alone are unusable.
P-9: Preview before consent; retain closing reference/--body-file; no text execution.

## State-transition changes
P-10: Defaults in bound only; retain saved title/body.

## Interface and API changes
P-11: Plan: frame title, summary and manual defaults as `<label> [default chars=N: <text>]: ` in C-1/C-2; N counts Unicode code points. Wait for N characters plus terminator; extract by length, ignoring embedded `]:`/`[y/n]`. Preserve CLI editing.

## Schema or persistence changes
P-12: Preserve BASELINE_REPORT.md C-1/2.

## Compatibility strategy
P-13: Preserve spec §8 and `.git` file/directory routing.

## Concurrency implications
P-14: Retain C-1 post-prompt checks; no new writers.

## Error and recovery behavior
P-15: Malformed sources: P-7/8; retain spec §9/nonempty answers.

## Migration plan
P-16: None; P-10.

## Rollback plan
P-17: Revert C-1–4 changes only; retain journals/branches/PRs.

## Feature-flag or containment strategy
P-18: Retain flag/unattended guards (C-1:4).

## Automated-test strategy
| ID | Planned command/check |
|---|---|
| T-1 | `bash scripts/tests/close-flow-test.sh`: defaults, edits, bad/missing sources, controls, title; P-19 |
| T-2 | `python3 -B scripts/tests/pr-prompt-test.py -q`: prefixes, Unicode, all chunks, `[y/n]`, edits; hold chunks after embedded `]:`, assert no early dialog and full buffer |

P-19: Plan C-3:test_description_defaults: blanks accept action/outcome fixtures; headings-only checks require input; section-only notes describe completed work; unusable notes require input. Mutate external symlink targets after binding for both sources; assert contents absent from preview/body. Fail before/pass after.

## Regression-test strategy
P-20: Run BASELINE_REPORT.md §8; no new failures.

## Manual-verification strategy
| ID | Planned check |
|---|---|
| M-1 | CLI/TUI fixture: defaults, edits, body, decline/resume, prompt-time drift |
| M-2 | Disposable GitHub PR: merge to default branch; record closure and post-merge comment URL/body/author/time separately; closure alone fails spec AR-4 |
| M-3 | No `.git`: no dialog; worktree: dialog |

## Observability changes
P-21: Preview; retain pending/URL output.

## Implementation sequence
| ID | Planned step |
|---|---|
| S-1 | Resolve R-2; add C-3/4 tests |
| S-2 | Implement P-6–11 in C-1/C-2 |
| S-3 | Run T-1/T-2 and P-20; execute M-1–3 |

## Scope cuts under time pressure
P-22: No acceptance cuts.

## Risks and unresolved questions
| ID | Disposition |
|---|---|
| R-1 | ASSUMPTION: spec §16 Summary naming; settle T-1. |
| R-2 | UNRESOLVED: retain spec AR-4 comment requirement; C-1:handoff supplies only a closing reference. Before S-1, obtain human contract clarification or approved comment lifecycle: owner, merge trigger, permissions, deduplication, retries, tests, rollback. C-1–4 authorize no merge integration. |
| R-3 | Retain consent. |
| R-4 | UNRESOLVED: TTY; M-1/2. |

| Requirement | Behavior | Invariant | Component | Automated test | Manual check |
|---|---|---|---|---|---|
| AR-1 | B-2 | I-5 | C-1 | T-1 | M-1 |
| AR-2 | B-2 | I-5 | C-2 | T-2 | M-1 |
| AR-3 | B-3 | I-6 | C-1/2 | T-1/2 | M-1 |
| AR-4 | B-1 | I-3 | C-1 | T-1 reference only; R-2 | M-2 |
| AR-5 | B-5 | I-4 | P-4 | P-20 | M-3 |
| AR-6 | B-1 | I-1 | C-1 | P-20 | M-1 |
| AR-7 | B-4/7 | I-2 | C-1 | P-20 | M-1 |

## Frozen change scope
| ID | Planned boundary |
|---|---|
| F-1 | After R-2 resolution: C-1–4, P-6–11; retain consent and spec I-1–6. |
## Files expected to change
| ID | Planned paths |
|---|---|
| F-2 | C-1–4 paths in Exact components to modify. |
## Files that must not change
| ID | Protected paths |
|---|---|
| F-3 | All paths outside C-1–4, including P-4 exclusions and preexisting unrelated edits. |
## Expected behavioral differences
| ID | Planned observable |
|---|---|
| D-1 | T-1/T-2/P-19: audited, editable completed-work and action/outcome defaults. |
## Expected unchanged behavior
| ID | Planned preservation |
|---|---|
| U-1 | CHANGE_SPEC.md B-1/B-4–7, I-1–4; title_default(), consent, journal v1, P-13. R-2 blocks AR-4 acceptance. |
## Exact acceptance criteria
| ID | Required result |
|---|---|
| AC-1 | Spec AR-1: T-1 preserves issue/change-request title defaults. |
| AC-2 | Spec AR-2: T-2 passes editable buffers at every split, including embedded terminators. |
| AC-3 | Spec AR-3/I-6: T-1/P-19 prove completed work and actions/outcomes; unusable sources require input. |
| AC-4 | Spec AR-4: UNRESOLVED R-2; M-2 must record comment and closure. |
| AC-5 | Spec AR-5: M-3 proves no dialog without .git and dialog in worktrees. |
| AC-6 | Spec AR-6/I-1: P-19 excludes external link contents; M-1 rejects prompt-time drift. |
| AC-7 | Spec AR-7/I-2: P-20 verifies pending recovery and no duplicate/uncertain recreation. |
## Pre-implementation checks
| ID | Planned check |
|---|---|
| PRE-1 | Resolve R-2 before S-1; record `git status --short` and starting diff; run T-1/T-2 before edits. |
| PRE-2 | Inspect bound notes/checklist formats against P-6/P-8; settle R-1 with T-1 fixtures. |
## Post-implementation checks
| ID | Planned check |
|---|---|
| POST-1 | Run S-3 and AC-1–7; record results and M-2 evidence; check diff against F-2/F-3. |
## First features to cut if time expires
| ID | Planned cut |
|---|---|
| CUT-1 | None: P-22; stop incomplete work rather than waive acceptance. |
## Conditions that require stopping implementation
| ID | Stop condition |
|---|---|
| STOP-1 | R-2 unresolved; scope expansion requires revised approval before implementation. |
| STOP-2 | Audit binding, framing, protected paths or AC-1–7 cannot be preserved; report blocker. |
| STOP-3 | M-1/M-2 unavailable: R-4 remains unverified; do not claim acceptance. |
