# Change spec: `uncle --audit [BRANCH]`

Omitted sections: Performance (none); Migration (none: no schema); Prototype isolation (not a prototype)

## 1. Change type
Feature (new CLI command).

## 2. Problem statement
Rerunning the final auditor requires hand-editing `.uncle/workflow/state` and rerunning the driver. Operators want one command.

## 3. Current behavior
B-1..B-7 in the baseline. `--audit` is an unknown argument.

## 4. Desired behavior
`uncle --audit [BRANCH]` sets the change workflow of the branch's checkout back to its `FINAL_AUDIT` state and runs the existing change driver, which runs the unchanged auditor, writes `.uncle/docs/FINAL_AUDIT.md` in that checkout, and routes the verdict as it does today. The command then prints the verdict class and the audit file path. BRANCH defaults to the current branch. Settled questions: auditor = FINAL_AUDIT stage; optional positional branch; output stays in `<checkout>/.uncle/docs/FINAL_AUDIT.md`.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| B-1 | ADD | `uncle --audit` | Unknown argument | Audits current branch's checkout; prints verdict and FINAL_AUDIT.md path; exit = driver status | AC-2 test |
| B-8 | ADD | `uncle --audit BRANCH` | n/a | Audits checkout where BRANCH is checked out (this or another worktree); caller's checkout untouched | AC-3 test |
| B-9 | ADD | `--audit` cannot run | n/a | One-line `Error: ...` on stderr naming the cause, nonzero exit (`$UNCLE_REFUSE_CODE`), state file unchanged | AC-4 tests |
| B-2 | MODIFY | `uncle --help` | usage without audit | usage lists `--audit [BRANCH]` | AC-1 |
| B-5 | MODIFY | near-miss like `--audt` | Did-you-mean from fixed list | list includes `--audit` | AC-1 |
| B-3,B-4,B-6,B-7 | PRESERVE | existing flags / driver | as baseline | unchanged | AC-5 |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| I-1 | EXISTING | One driver per checkout | driver | driver.lock | AC-4 lock case |
| I-3 | EXISTING | Audit binding/verdict routing unchanged | driver | `change-workflow.sh` untouched | AC-7 diff check |
| I-4 | EXISTING | Unknown args refused with `$UNCLE_REFUSE_CODE` | launcher | `uncle` | AC-5 |
| I-6 | NEW | `--audit` never modifies state unless every precondition passed | audit command | precondition order in new script | AC-4 tests assert state bytes unchanged |
| I-7 | NEW | `--audit` never switches or modifies the caller's checkout/branch | audit command | no `git checkout`/`switch` used | AC-3 test asserts HEAD unchanged |
No RELAXED or REMOVED invariants.

## 7. Compatibility
All existing flags, exit codes, and driver options unchanged. `--audit` composes with `--attended`/`--unattended`/`--noui`; refused with `--application`, `--issue`, `--change-request`, `verify`-style early exits are not combinable.

## 8. Error and failure behavior
Clear refusal (B-9) for: not a git repo; detached HEAD without BRANCH; BRANCH not a local branch; BRANCH not checked out in any worktree; checkout has no change-family workflow state; driver lock held; more than one BRANCH; BRANCH beginning with `--`; combined with another startup action. A driver failure or a not-READY audit surfaces the driver's own message and nonzero exit.

## 10. Security
Branch name is validated with `git check-ref-format --branch` and passed only as a quoted argument; never evaluated. No new env override for the driver path. `UNCLE_HOME_AGENT` rule (I-2) applies: refuse `--audit` from the home agent subtree without the app marker, as other startup actions do.

## 12. Rollback
Revert the commit: removes flag and script. State left at FINAL_AUDIT after a run is harmless: resuming reruns the audit; previous state is printed so an operator can restore it.

## 14. Non-goals
Changing what the auditor checks; other commands; app-family (stagegate) audits; creating worktrees or checking out branches; cleanup.

## 15. Assumptions
A1/A2 from the baseline. Exit status equals the driver's; the verdict is printed for information.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `uncle --help` lists `--audit [BRANCH]` and exits 0; the did-you-mean hint for a near miss such as `--audt` suggests `--audit`. | Shell test greps help output and hint output. |
| AC-2 | `uncle --audit` with no argument in a checkout with a change-family workflow sets state to FINAL_AUDIT, runs the change driver in that checkout, prints the verdict class and the path of `.uncle/docs/FINAL_AUDIT.md`, and exits with the driver's status. | Fixture test with stub driver via UNCLE_RUNTIME_ROOT records state, cwd and flags at invocation; asserts output and exit codes 0 and nonzero cases. |
| AC-3 | `uncle --audit BRANCH` runs the driver in the worktree where BRANCH is checked out, without changing the caller's checkout, branch or HEAD. | Fixture with two worktrees; stub driver records cwd; caller HEAD and branch compared before and after. |
| AC-4 | Each unrunnable case (not a git repo, detached HEAD without BRANCH, unknown branch, branch not checked out, no change workflow state or app-family state, driver lock held, extra positional, option-like BRANCH, combined with --application/--issue/--change-request) prints a one-line `Error:` message naming the cause, exits `$UNCLE_REFUSE_CODE`, and leaves the state file byte-identical. | One shell test case per condition checking stderr, exit code, and state checksum. |
| AC-5 | Existing launcher behavior is unchanged: existing launcher-* tests and the full shell and Python suites show no new failures versus baseline. | `bash scripts/run-shell-tests.sh` and `bash scripts/run-python-tests.sh` compared with baseline by the driver. |
| AC-6 | New automated tests (`scripts/tests/audit-command-test.sh`) cover AC-1 to AC-4 and fail when the command is absent or skips a precondition. | Run the test against the unmodified launcher (fails) and against a copy with one precondition removed (fails). |
| AC-7 | The auditor and driver are not modified: no diff in `scripts/change-workflow.sh`, `scripts/stagegate.sh`, `scripts/lib/audit-verdict.sh`, or `prompts/`. | `git diff --stat` against the change-impact table scope. |

