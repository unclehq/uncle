# Change Spec

Omitted sections: Performance (none); Security (no new surface beyond input parsing); Migration (none); Prototype isolation (not applicable)

## 1. Change type
Feature.

## 2. Problem statement
A new change request silently replaces a leftover `.uncle/docs/CHANGE_REQUEST.md`, so the user may run a different change than intended.

## 3. Current behavior
See baseline B1.

## 4. Desired behavior
When seeding a new change request in change mode and the request file already exists (and is not the same in-flight issue run), tell the user, ask to proceed; yes proceeds, otherwise stop with the file and run state untouched.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| S1 | ADD | Interactive, file exists, answer `y`/`yes` (case-insensitive) | Overwrites silently | Message names the file, prompt shown, run proceeds and file is replaced | AC-1 test |
| S2 | ADD | Interactive, file exists, answer anything else, empty, or EOF | Overwrites | Exit nonzero with message; file bytes and run state unchanged | AC-2 test |
| S3 | PRESERVE | No existing file | Written, no prompt | Same, no prompt | AC-3 test |
| S4 | ADD | `UNCLE_UNATTENDED=1`, file exists | Overwrites | No read from stdin; stop nonzero with clear message unless `UNCLE_REPLACE_CHANGE_REQUEST=1`, then proceed | AC-4 test |
| S5 | PRESERVE | Same-issue in-flight run (seed_is_current) | Resume, file untouched | Same, no prompt | AC-5 test |
| S6 | PRESERVE | `UNCLE_NEW_WORKFLOW=1` fresh start (old evidence archived first) | Archive then reseed | Same, no prompt | AC-5 test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| V1 | NEW | An existing CHANGE_REQUEST.md is never replaced without an explicit yes or explicit unattended opt-in | from-issue.sh change mode | confirm function before write | AC-1..4 |
| V2 | NEW | Declining or unattended refusal leaves CHANGE_REQUEST.md and `.uncle/workflow` state byte-identical | same | guard runs before archive, write_origin, and workflow launch | AC-2, AC-4 |
| V3 | EXISTING | Seed-only and stdin imports never overwrite | same | noclobber / EXISTS | existing tests |

No RELAXED or REMOVED invariants.

## 7. Compatibility
No-file and resume flows unchanged. Callers with closed or empty stdin now stop instead of overwriting.

## 8. Error behavior
Decline/EOF/unattended-without-opt-in: message on stderr naming the file and (unattended) the env opt-in, exit 1.

## 12. Rollback
Revert the from-issue.sh guard and test; no persisted state.

## 14. Non-goals
Archiving the previous request (open question: deferred, not requested as required); changing stdin import behavior; prompting in the new-app flow.

## 15. Assumptions
Yes = `y`/`yes` case-insensitive after trimming; empty = no. Unattended default is stop, opt-in via `UNCLE_REPLACE_CHANGE_REQUEST=1`. The worktree may already exist when declining; it is not modified beyond that.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Interactive run, existing request file, answer y/yes (any case): message names the file, run proceeds and the new request is written. | New shell test feeds `y`, `YES` on stdin; asserts exit 0 and new content. |
| AC-2 | Interactive run, existing file, answer n, other text, empty line, or EOF: run stops nonzero and file bytes and workflow state are unchanged. | Shell test with hash comparison of file and `.uncle/workflow` inventory. |
| AC-3 | No existing file: no prompt is printed and behavior is unchanged. | Shell test asserts no prompt text and file written; existing issue-document-test.sh still passes. |
| AC-4 | With UNCLE_UNATTENDED=1 the run never reads stdin: it stops with a clear message naming UNCLE_REPLACE_CHANGE_REQUEST=1 unless that is set, in which case it proceeds. Documented in scripts/README.md. | Shell test with stdin closed/hanging pipe under timeout; both cases; README grep. |
| AC-5 | In-flight same-issue resume and UNCLE_NEW_WORKFLOW=1 fresh start do not prompt. | Shell test or existing worktree-auto-seed-test.sh plus new case. |
| AC-6 | Full shell and Python suites show no new failures versus baseline. | Driver runs bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh. |

