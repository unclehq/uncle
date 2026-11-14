# Change spec — issue 267

Omitted sections: Performance (none); Security (no new trust boundary); Migration (none, no persisted format change); Prototype isolation (n/a).

## 1. Change type
Bug fix.

## 2. Problem statement
An updated plan whose checks are scripts not named like tests (e.g. `scripts/check-launch.sh`) is refused with no protected paths, and the refusal is reported as `writer attempts exhausted`. Baseline B-2, B-3, B-7.

## 3. Current behavior
Baseline B-1..B-7.

## 4. Desired behavior
Protected paths fall back to the repository files that `verification_commands` execute; the Markdown project-plan fallback records protected paths; a merge refusal is reported as its own stop reason.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB-1 | MODIFY | Plan names no test file by name/dir but `verification_commands` run `scripts/check-a.sh`, `bash scripts/run-defects.sh`, `./scripts/check-b.sh` | Conflict, stage stops (B-2) | Those scripts are derived as protected paths (subject to B-5 ownership filter) and merge succeeds | unit test on `derive_protected_paths` and on merge with a fixture plan |
| SB-2 | PRESERVE | Plan names test files by name/dir | Named test files derived | Unchanged result: the executed-file fallback is not consulted | existing ops/fast-path tests |
| SB-3 | PRESERVE | Excluded tokens (`.json`, `.lock`, dot/abs/`..`/build dirs) | Excluded | Also excluded from the executed-file fallback | unit test |
| SB-4 | MODIFY | Commands execute only tools with no repo file (e.g. `cabal test`, `npm test`) and plan names no test file | Conflict | Still a refusal, now reported per SB-6 | unit test |
| SB-5 | MODIFY | Markdown single-pass project plan is ingested | No `protected_verification_paths` | Payload carries derived `protected_verification_paths` (named tests first, else executed files), so the updated plan need not derive | unit test on ingest |
| SB-6 | MODIFY | `updated_plan_ops.py merge` raises Conflict | stop-reason `updated-plan: writer attempts exhausted` | stop-reason `updated-plan: merge conflict: <message>`; stderr names the merge refusal | python test (exit code/message) + shell test (stop-reason file) |
| SB-7 | PRESERVE | Writers genuinely exhausted (stagegate 2984 path) | `updated-plan: writer attempts exhausted` | Unchanged | existing writer-retries test |
| SB-8 | PRESERVE | Merge refusal | `workflow_terminal_failure` treats the run as terminal | Still terminal | shell test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI-1 | EXISTING | Protected paths are repository-relative with no generated/build/dot/`..` paths (I-1) | derivation | fast_path | unit test |
| SI-2 | EXISTING | Protected path must be step-owned when any are owned (I-2) | merge/publish | ops, publish_agent_artifact | existing test |
| SI-3 | STRENGTHENED | Protected-path derivation covers executed repository files when no tests are named; empty only when commands execute no repo file | derivation | fast_path | unit test |
| SI-4 | EXISTING | Updated plan never published with empty protected paths (I-3) | merge/publish | ops, edits, publish | unit test (SB-4) |
| SI-5 | NEW | A merge refusal never reports writer exhaustion; writer exhaustion never reports merge conflict | stop-reason | stagegate, model-jobs | shell test |
No RELAXED or REMOVED invariants.

## 7. Compatibility requirements
Stop-reason keeps the `updated-plan:` prefix. `updated-plan-writers-exhausted` flag still created on merge refusal. Existing plans with named tests derive identical paths.

## 8. Error and failure behavior
Merge refusal: stderr line `updated-plan ops: <message>`, distinct exit status from other errors, stop-reason `updated-plan: merge conflict: <message>` (message single-line, truncated), stage returns 1.

## 12. Rollback
Revert the commit; no persisted data changes.

## 14. Non-goals
Changing writer prompts; changing the typed-plan path; protecting files beyond those executed; touching change-workflow.sh messaging.

## 15. Assumptions
Executed-file means a repository-relative path token with a file extension in command position or as the first argument to an interpreter (`bash`, `sh`, `python3`, `node`, etc.), with leading `./` stripped. Existence on disk is not required (the implementation steps create it).

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | derive_protected_paths(text, commands) with no test-named path returns the repository scripts executed by commands (`scripts/check-ghci-exercises.sh`, `scripts/check-launch.sh`, `scripts/run-defects.sh`, including `./`-prefixed and interpreter-prefixed forms), one per line, in first-appearance order, deduplicated. | New unit test in scripts/tests/updated-plan-fast-path-test.py with the issue's command list. |
| AC-2 | When any test-named path is found the executed-file fallback is not used, and exclusions (.json/.lock, dot/absolute/`..`/build-dir paths, tool names without a repository file such as `cabal test`) still apply. | Unit tests for named-test precedence and exclusions; existing ops-test:160-180 unchanged and passing. |
| AC-3 | updated_plan_ops merge of a fixture plan whose commands run scripts/check-*.sh (no test-named files, steps own those scripts) succeeds and yields those protected paths instead of Conflict. | New test in scripts/tests/updated-plan-ops-test.py. |
| AC-4 | When commands execute no repository file and no test is named, merge still refuses, with a distinct nonzero exit status and the message on stderr. | New test in updated-plan-ops-test.py asserting the status and message. |
| AC-5 | The single-pass Markdown project-plan ingest produces `protected_verification_paths` (named tests, else executed files) in the payload without failing validation. | New unit test scripts/tests/plan-context-protected-test.py calling the Markdown ingest on a plan like the issue's; payload field asserted and artifact validation succeeds. |
| AC-6 | A merge refusal in stagegate writes stop-reason `updated-plan: merge conflict: <message>`, still creates the updated-plan-writers-exhausted flag, and does not print the writer-exhausted line; genuine writer exhaustion still writes `updated-plan: writer attempts exhausted`. | New shell suite scripts/tests/updated-plan-merge-conflict-test.sh exercising the helper(s); existing updated-plan-writer-retries test passes. |
| AC-7 | All pre-existing shell and Python suites that passed in the baseline still pass. | Driver re-run of the verification commands compared with baseline. |

