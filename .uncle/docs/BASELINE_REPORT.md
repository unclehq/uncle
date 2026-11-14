# Baseline report

Omitted sections: Reproduction (done by reading code and the issue log, not run); Performance (none)

## 1. Change-request summary
Issue 276 (CHANGE_REQUEST.md). An unattended hand-off build (`UNCLE_PUBLISH_MODE=handoff`, `UNATTENDED=1`) whose work tree has no commit publishes nothing: no `.uncle/attestation.json`, no `handoff.json`, no audit verdict/findings, no `draft` flag. The completion text also claims findings are in the PR.

## 2. Repository architecture
Bash drivers (`scripts/change-workflow.sh`) source libs in `scripts/lib/`. PR/hand-off engine is an embedded Python program in `scripts/lib/change-pr.sh` (`change_pr_engine <action>`), plus `scripts/lib/handoff_export.py`. Tests are `scripts/tests/*-test.sh|py`, run by `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (default tier = `scripts/tests/critical-suites.txt`).

## 3. Relevant code paths
- `scripts/change-workflow.sh:44-48` run policy call; `:3997` `change_pr_engine start`.
- `scripts/lib/run-policy.sh:158-166` `run_policy_change_branch`: unborn HEAD -> prints "no git history to branch from" and returns 0.
- `scripts/change-workflow.sh:5269-5284` unattended completion: `git rev-parse --verify HEAD` else prints "Unattended: no base commit, so no PR was made." and skips `change_pr_complete`.
- `scripts/lib/change-pr.sh:198-214` `change_pr_complete_route` hand-off branch -> `attest-handoff` (`:815`) then `handoff_export.py`.
- `scripts/lib/change-pr.sh:903-911` `head()`/`branch()` need a commit; audit action creates the journal with `original_head=head()` (~`:2064`); `start_build` returns on unborn HEAD or no remote (`:1550-1557`).
- `scripts/lib/handoff_export.py:83-123` writes `.uncle/handoff/handoff.json` (`draft = not verdict.startswith('READY')`, `base_commit`, attestation, verdict); `changes()` tolerates empty base.
- `scripts/lib/audit-verdict.sh:216` unconditional "findings are in the PR and attestation".

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Hand-off/unattended build, HEAD exists, audit NOT_READY | handoff.json with attestation, verdict, `draft:true` | handoff-export-test.py; change-pr.sh:207 | Yes |
| B-2 | Any run, unborn HEAD, non-hand-off | run policy skips branch with message | run-policy.sh:164 | Yes |
| B-3 | Unattended, unborn HEAD | no PR/hand-off, prints "no base commit" | change-workflow.sh:5281 | Modify only for hand-off mode |
| B-4 | NOT_READY final audit, gate off | prints "findings are in the PR and attestation", state COMPLETE | audit-verdict.sh:216 | Modify wording only when untrue |
| B-5 | Non-hand-off unattended, HEAD exists | `change_pr_complete` publishes (draft if not READY) | unattended-test.sh:366-380 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | A NOT_READY verdict is never published as a ready PR | handoff_export.py:100 draft flag; PR draft path | handoff-export-test.py | High |
| I-2 | Run never works on main/preexisting branch when history exists | run-policy.sh | run-policy-test.sh | High |
| I-3 | Workflow never commits the project without consent in non-hand-off mode | CLAUDE.md/driver design | various | Medium |

## 6. Contracts
`handoff.json` schema `SCHEMA` in handoff_export.py: fields base_commit, draft, audit_verdict, attestation, changes, tree. `base_commit` empty means empty tree. Host script is outside this repo.

## 7. Existing automated-test coverage
`unattended-test.sh` (stubs `change_pr_complete`, harness extracts driver functions), `handoff-export-test.py` (real git fixtures), `run-policy-test.sh`, `pr-auto-publish-test.sh`, `pr-publish-reason-test.sh`. No test covers unborn HEAD in hand-off mode. The shell and Python runners use separate temp dirs and share no ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh`, `scripts/run-python-tests.sh` (named in the task's runner guidance). Not run here; the driver baseline is authoritative. Some Python suites are documented as failing on a clean checkout.

## 10. Existing failures
Unknown until driver baseline; see `.uncle/workflow/green-check.baseline.tsv`.

## 12. Likely change surface
`scripts/lib/run-policy.sh`, `scripts/change-workflow.sh` (unattended completion text), `scripts/lib/audit-verdict.sh` (message), new test, `scripts/tests/critical-suites.txt`.

## 13. Regression-sensitive components
run-policy branch creation; unattended completion for non-hand-off runs; PR engine journal binding to `original_head`.

## 14. Outside the change
Host build script (release owner, not in repo); `handoff_export.py` schema; PR publication for repos with history; the PR text quoting `uncle verify`.

## 15. Unknowns and assumptions
- A1: `scripts/run-shell-tests.sh -- <name>` selects one suite (same form as the Python runner); implementer confirms with `--help`.
- A2: With a seeded base, the audit action creates the PR journal even with no remote (journal creation at change-pr.sh ~2064 is not gated on remote); to be confirmed by the new test.

## 16. Initial risk
Medium: a synthetic base commit differs from the host's real base; handoff.json `base_commit` will then name the seed commit, which the host must treat as local-only (release-owner item).

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

