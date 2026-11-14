# Change spec: issue 276

Omitted sections: Performance, Security, Migration, Prototype isolation (none apply)

## 1. Change type
Bug fix.

## 2. Problem statement
In hand-off mode a work tree with no commits yields no attestation, no hand-off record, no verdict and no draft flag; completion text wrongly says findings are in the PR.

## 3. Current behavior
See baseline B-3, B-4.

## 4. Desired behavior
In hand-off mode with no base commit, the run seeds a base commit from the starting tree before the build so HEAD exists; the normal path then writes the attestation, `handoff.json`, verdict and `draft:true` when not READY. The NOT_READY completion line only claims PR/attestation findings when HEAD exists.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| BH-1 | ADD | Hand-off mode, git work tree with unborn HEAD, run start | No commit; "no git history" message | Starting tree (excluding `.uncle/`) committed as base with signing disabled; HEAD resolves; message names the seed | run-policy test |
| BH-2 | MODIFY | Unattended hand-off build, no pre-existing commit, NOT_READY audit | No hand-off record, "no base commit" | handoff.json written with attestation, audit_verdict NOT_READY, draft true, changes = only files changed since seed | new shell test |
| BH-3 | MODIFY | NOT_READY audit completes with no HEAD | Claims findings in PR and attestation | Says findings are in `.uncle/docs/FINAL_AUDIT.md` only; PR/attestation wording only when HEAD exists | new shell test |
| BH-4 | MODIFY | Unattended hand-off, HEAD absent even after seeding failed | Says "no PR was made" | Says no hand-off record was written and why; exit status unchanged | new shell test |
| BH-5 | PRESERVE | Non-hand-off mode, unborn HEAD | Run-policy skips branch, no commit | Unchanged; no commit made | run-policy test |
| BH-6 | PRESERVE | Hand-off mode with existing HEAD | No seed commit | Unchanged; HEAD not moved | run-policy test, handoff-export-test.py |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | NOT_READY audit yields a draft hand-off | handoff_export.py | `draft` computation | handoff-export-test.py + new test |
| INV-2 | NEW | Seeding happens only in hand-off mode with unborn HEAD and never touches user git config or signing | run-policy.sh | seed function guard | run-policy test |
| INV-3 | NEW | Seed commit never contains `.uncle/` state | run-policy.sh | pathspec exclude | run-policy test |
| INV-4 | EXISTING | Non-hand-off runs make no commit | run-policy.sh | mode guard | run-policy test |

No RELAXED or REMOVED invariants.

## 7. Compatibility
handoff.json schema unchanged. `base_commit` is the seed commit when seeded.

## 8. Failure behavior
Seed failure (commit error) prints a warning and continues as today; BH-4 messaging applies.

## 12. Rollback
Revert the commit; no persisted formats change.

## 14. Non-goals
The host build script; the `uncle verify` text in host PRs; changing the PR/handoff schema; seeding outside hand-off mode.

## 15. Assumptions
The seed commit being synthetic is acceptable under request option 1 ("commit the starting tree as a base"); the host must handle base_commit accordingly.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | In hand-off mode with an unborn HEAD in a git work tree, run_policy_change_branch creates one base commit of the starting tree excluding .uncle/, with signing disabled, and HEAD then resolves. | scripts/tests/run-policy-test.sh new cases |
| AC-2 | Outside hand-off mode, or with an existing HEAD, no commit is created and HEAD is unchanged. | scripts/tests/run-policy-test.sh new cases |
| AC-3 | An unattended hand-off build whose work tree started with no commits ends with .uncle/handoff/handoff.json containing the attestation, audit_verdict NOT_READY and draft true, and .uncle/attestation.json written. | scripts/tests/handoff-no-base-test.sh |
| AC-4 | The NOT_READY completion line says findings are in the PR and attestation only when HEAD resolves; otherwise it names .uncle/docs/FINAL_AUDIT.md. | scripts/tests/handoff-no-base-test.sh |
| AC-5 | If hand-off mode still has no HEAD at completion, output states no hand-off record was written instead of implying a PR path; exit status is unchanged. | scripts/tests/handoff-no-base-test.sh |
| AC-6 | Existing shell and Python suites show no new regressions versus the driver baseline. | driver verification commands |

