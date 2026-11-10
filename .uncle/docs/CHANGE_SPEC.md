# Change spec: issue 231

Omitted sections: Performance (no hot path), Security (no new surface; the repair prompt contains only the saved plan and validator errors), Migration (none), Prototype isolation (not a prototype)

## 1. Change type
Bug fix.

## 2. Problem statement
A project plan (or updated plan) failing its check ends a headless build with exit 1 and no repair, while other stages get one repair attempt. The trigger can be a non-path token the parser accepted from a backticked `Owns:` span.

## 3. Current behavior
See baseline B-2..B-5.

## 4. Desired behavior
Non-path backticked/JSON `owns` tokens are dropped with a warning naming the step; a failed plan check gets exactly one model repair turn limited to the validator's errors; failure after repair exits 1 with an actionable message.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | PRESERVE | Owns line with comment-marker span | Dropped | Unchanged | existing marker test |
| BH-2 | MODIFY | Owns line `` `app/Main.hs`, `test/Spec.hs` (ends with a `-- EOF-GUARD` comment) `` | Possible bad token | `owns == ['app/Main.hs','test/Spec.hs']` | new parser test |
| BH-3 | MODIFY | Backticked span failing path shape (e.g. `foo bar`) | Kept, plan fails | Dropped; warning names step | new parser test |
| BH-4 | MODIFY | JSON `owns` array with non-path string | Kept, plan fails | Dropped with warning | new model test |
| BH-5 | MODIFY | PROJECT_PLAN check fails first time | exit 1 | One repair turn with plan + exact errors; re-check; continue if passes | new stage test |
| BH-6 | MODIFY | Check still fails after repair | n/a | exit 1, diagnostic names file, step and resume command; no second repair | new stage test |
| BH-7 | MODIFY | UPDATED_PLAN check fails | exit 1 | Same as BH-5/BH-6 | new stage test |
| BH-8 | ADD | Repair turn hits host spending stop | n/a | Stage stops cleanly with spending_limit stop-reason, no re-check loop | new stage test |
| BH-9 | ADD | Same failure in headless run (no TUI) | exit 1 | Same repair behavior, independent of supervisor | headless test |
| BH-10 | PRESERVE | Valid plan | Passes | No repair turn, no marker | existing + new test |
| BH-11 | PRESERVE | Real paths/globs in Owns | Kept | Kept | existing marker test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | Every `owns` token in a validated plan is a valid path/glob, not a directory (baseline I-1) | plan_model.validate | `plan_model.py:474-482` | existing + new tests |
| INV-2 | STRENGTHENED | At most one repair turn per plan check; it cannot loop | PROJECT_PLAN and UPDATED_PLAN checks | one-time marker in `$STATE_DIR` | stage test asserts one agent call |
| INV-3 | EXISTING | An invalid plan never advances | stagegate.sh | exit 1 after failed repair | stage test |
| INV-4 | EXISTING | A host spending stop halts model work (I-3) | repair turn | spending-stop check | stage test |
| INV-5 | NEW | Repair changes only what the validator errors name | repair prompt | prompt instruction; re-check | reviewed manually (model behavior) |

No RELAXED or REMOVED invariants.

## 7. Compatibility
Plans that validated before still validate (filter only drops tokens that previously failed or were non-paths). Exit codes unchanged on terminal failure.

## 8. Error and failure behavior
After a failed repair: stderr names the file, the step (parsed from the validator error), the validator message, and the resume command; `stop-reason` records validation failure; exit 1.

## 12. Rollback
Revert the change; no persisted format changes. A leftover marker file is harmless.

## 14. Non-goals
Starting the supervisor in headless mode; changing validator rules; repair for other stages; multi-attempt repair.

## 15. Assumptions
A marker cleared on a passing check, retained on failure, so a resumed run does not repair again.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `plan_steps.paths` on an Owns line with backticked paths followed by a parenthetical containing a backticked `-- EOF-GUARD` returns only the real paths. | New case in a plan_steps parser test; existing plan-owns-comment-marker test still passes. |
| AC-2 | Backticked Owns spans not matching the plain-token path shape are dropped from `paths()` with a warning that names the step; real paths/globs including `.gitignore` and `src/**` are kept. | New parser test asserts result and captured warning. |
| AC-3 | The `owns` array on the JSON route drops non-path-shaped strings with a warning naming the step, and keeps valid ones. | New plan_model test. |
| AC-4 | A project plan failing the plan check gets exactly one repair model turn given the saved plan and the validator's exact errors, is re-checked, and the build continues when the re-check passes. | Stage test with a stub agent: step 2 owns an invalid token; asserts one agent call and continuation. |
| AC-5 | A plan still invalid after the repair exits 1 with a diagnostic naming the file, the step and the resume command, and no second repair runs (also on resume). | Stage test asserts exit 1, message content and agent-call count of 1 across a rerun. |
| AC-6 | The updated-plan check has the same one-repair behavior. | Stage test for UPDATED_PLAN. |
| AC-7 | A spending stop during the repair turn stops the stage cleanly with a spending_limit stop-reason and does not re-check or loop. | Stage test using the existing spending-stop harness. |
| AC-8 | The repair works in a headless run with no TUI/supervisor. | Headless test (follow headless-run-test.py harness) of the AC-4 scenario. |
| AC-9 | A valid plan triggers no repair turn; existing shell and Python suites show no new regressions versus baseline. | Driver verification commands compared with baseline; stage test asserts zero agent calls. |

