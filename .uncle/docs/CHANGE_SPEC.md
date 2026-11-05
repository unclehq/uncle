# Change Spec

Omitted sections: Performance, Security (no new surface beyond deny list), Migration (none), Prototype isolation (n/a)

## 1. Change type
Feature.

## 2. Problem statement
Housekeeping is blocked by the build's checkout lock and the TUI's single-workflow guard, though it does not affect the build.

## 3. Current behavior
See baseline B-1..B-3.

## 4. Desired behavior
Housekeeping can be started from the TUI (and script) while a build runs. It runs as an independent background process, uses its own lock, and writes nothing the build reads. Starting it never changes the build's process, state, mode, gates or exit.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | `/housekeeping TEXT` while a build is active | Refused | Starts background housekeeping; chat notice 'Housekeeping started in background'; build proc/state untouched | tui-housekeeping-test.py |
| SB-2 | MODIFY | housekeeping script while driver.lock held by build | Exit 1 | Runs; does not take driver.lock | housekeeping-workflow-test.sh |
| SB-3 | MODIFY | housekeeping run | Writes shared `.uncle/workflow/mode` | Does not write or modify `.uncle/workflow/mode` | housekeeping-workflow-test.sh |
| SB-4 | PRESERVE | second housekeeping while one runs (script or TUI) | Refused | Still refused (own `housekeeping.lock`; TUI notice) | both tests |
| SB-5 | PRESERVE | `/housekeeping` when idle; `uncle --housekeeping` | Foreground run | Unchanged | existing tests |
| SB-6 | ADD | background housekeeping finishes | n/a | Chat notice with final state (DONE/FAILED) and exit code | tui-housekeeping-test.py |
| SB-7 | ADD | housekeeping prompt | n/a | Instructs agent not to edit, check out, reset or clean the working tree or current branch under build | housekeeping-workflow-test.sh (prompt.md content) |
| SB-8 | MODIFY | `/new`, `/issue`, `/change` while workflow active | Refused | Still refused | existing tests |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | At most one housekeeping run per checkout | script | housekeeping.lock | shell test |
| SI-2 | EXISTING | Deny list applies to every run | script | disallowedTools | housekeeping-policy-test.py |
| SI-3 | NEW | Housekeeping writes no build-owned state (driver.lock, workflow/mode, build artifacts) | script | script | shell test |
| SI-4 | STRENGTHENED | At most one build workflow per checkout | TUI | existing guard | tui test |
| SI-5 | RELAXED | Housekeeping previously excluded by the build's driver.lock; now allowed concurrently (**RELAXED, explicit human approval required**; requested by Issue 158) | script/TUI | n/a | tests SB-1, SB-2 |

## 7. Compatibility
CLI flags, exit codes, state names, startup option unchanged.

## 8. Error behavior
Second housekeeping: refuse exit 1 / chat notice. Launch failure: chat error, build unaffected. Background failure: notice with FAILED.

## 12. Rollback
Revert the commit; no persisted schema.

## 14. Non-goals
New UI pane; sandboxing agent filesystem access; concurrent builds; changing deny list; launcher `uncle --housekeeping` concurrency with a running build in another terminal beyond the script lock change.

## 15. Assumptions
See baseline section 15. Attended confirmation is not possible for a background run: background launch is always unattended.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | With a build workflow active in the TUI, /housekeeping TEXT starts a background housekeeping process and does not set the 'already active' error; self.proc, state and workflow_exit_* of the build are unchanged. | tui-housekeeping-test.py new test with mocked Popen |
| AC-2 | housekeeping-workflow.sh runs successfully while another process holds driver.lock, and it does not acquire driver.lock. | housekeeping-workflow-test.sh holds driver.lock then runs script with stub agent |
| AC-3 | A housekeeping run leaves .uncle/workflow/mode byte-identical (or absent if absent). | housekeeping-workflow-test.sh compares hash before/after |
| AC-4 | A second concurrent housekeeping run is refused (script exit 1; TUI notice) and the first is unaffected. | shell test with two runs on housekeeping.lock; tui test |
| AC-5 | The TUI posts a completion notice for a background housekeeping run with its final state, without touching the build's completion handling. | tui-housekeeping-test.py |
| AC-6 | The housekeeping prompt forbids modifying the working tree or branch under build; deny list behavior is unchanged. | shell test checks prompt.md; housekeeping-policy-test.py unchanged and passing |
| AC-7 | Idle /housekeeping, uncle --housekeeping, and /new,/issue,/change guards behave as before. | existing tests plus full runners pass |

