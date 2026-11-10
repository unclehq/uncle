# Change Spec (Issue 228)

Omitted sections: Performance (none), Security (none beyond signing hygiene), Migration (none), Prototype isolation (not a prototype)

## 1. Change type
Bug fix / test-health.

## 2. Problem statement
`run-all-tests.sh` has 11 failing suites (see CHANGE_REQUEST).

## 3-4. Current / desired behavior
Current: see baseline B-1..B-8. Desired: all suites green, 0 skipped, root cause fixed in product or test with rationale; environment-dependent failures become self-contained or fail with a clear prerequisite message.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | `stagegate.sh --version` / `change-workflow.sh --version` in any tree state | May be refused by run policy | Prints `0.1.0`, exit 0 | unattended-test.sh |
| SB-2 | MODIFY | `--help`/`-h` on both drivers | May be refused by run policy | Prints usage incl. `--unattended`, exit 0 | unattended-test.sh |
| SB-3 | PRESERVE | Real app build in dirty/non-main tree | Refused | Still refused | run-policy tests |
| SB-4 | MODIFY | Early-branch in no-remote/detached/unborn context | Creates ref in at least one case | No ref, no journal, no mutation | early-branch-test.py |
| SB-5 | MODIFY | TUI resume where git worktree listing is unavailable or project is not a repo | Unhandled exception | Defined refusal message per tests (or fixture made a valid repo, per root-cause) | home-actions-test.py |
| SB-6 | MODIFY | Attestation fixtures with repo `.gitignore` containing `.uncle` | tree-mismatch, wrong envelope | Attestation tests independent of the host checkout's `.gitignore` state | attestation-statement-test.py |
| SB-7 | MODIFY | Fixture commits/tags | Some lack explicit no-sign flags | All carry `-c commit.gpgsign=false` and `--no-gpg-sign` / `--no-sign` | supervisor-test.py |
| SB-8 | MODIFY | worktree-run and gates-verification-integrity suites | Fail with 127 / wrong state in some environments | Pass, or fail with clear prerequisite message | those suites |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | App builds start only from clean main | run-policy | run-policy.sh | run-policy tests |
| SI-2 | EXISTING | Fixtures never invoke the user's signer | tests | supervisor audit | supervisor-test.py |
| SI-3 | EXISTING | Skip contexts create no ref/journal | early-branch | early-branch code | early-branch-test.py |
| SI-4 | EXISTING | No test weakened/deleted/skipped | all | review | diff review |

No RELAXED or REMOVED invariants.

## 7. Compatibility
CLI flags and output unchanged except `--version`/`--help` now always work.

## 8. Error behavior
Missing prerequisites yield a message naming the missing tool, not exit 127.

## 12. Rollback
Revert the commit; changes are scripts and fixtures only.

## 14. Non-goals
New features; loosening run policy for real builds; changing assertions to pass.

## 15. Assumptions
Some failures (B-4, possibly B-1) depend on the host worktree's dirty `.gitignore`/branch; clean-main reproduction decides product-vs-test. Causes of 127 and gates-verification-integrity UNRESOLVED until reproduced.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `stagegate.sh --version` and `change-workflow.sh --version` print `0.1.0` and exit 0 regardless of working-tree state. | bash scripts/run-all-tests.sh (unattended-test.sh sg-version-flag) |
| AC-2 | `--help` on both drivers exits 0 and documents `--unattended`, regardless of tree state. | unattended-test.sh stagegate-help |
| AC-3 | Run policy still refuses real app builds from a dirty or non-main tree. | existing run-policy suites |
| AC-4 | early-branch-test.py passes fully with unmodified assertions. | run-all-tests.sh |
| AC-5 | attestation-statement-test.py passes in all shards, including with a dirty host .gitignore. | run-all-tests.sh |
| AC-6 | supervisor-test.py signing audit passes with every fixture git commit/tag carrying explicit no-sign flags. | run-all-tests.sh |
| AC-7 | home-actions-test.py, worktree-run-test.sh and gates-verification-integrity* pass or fail only with a clear prerequisite message (never exit 127 unexplained). | run-all-tests.sh |
| AC-8 | `./scripts/run-all-tests.sh` exits 0 reporting 0 failed, 0 skipped; no test is deleted, skipped or has weakened assertions; each test edit has a requirement-based explanation in IMPLEMENTATION_NOTES.md, and non-code-defect failures are listed for the PR. | run-all-tests.sh plus diff review |

