# Baseline report

Omitted sections: Reproduction result (not reproduced here: stage forbids running flows; reproduction is plan step 1); Areas outside change folded into section 12.

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md: regression, no PR/push after a finished run; cause unconfirmed; when no PR is made the reason must be reported.

## 2. Repository architecture
Bash driver `scripts/change-workflow.sh` sources libs in `scripts/lib/`. PR publication = bash wrapper `change-pr.sh` (`change_pr_complete`, `change_pr_publish`) plus an embedded Python engine (`change_pr_engine`, actions validate/commit-tree/verdict-override/completed-signing-resume/handoff) that runs git push and `gh pr create`. Finished-block text comes from `scripts/lib/finished_extras.py` (REASONS map, lines 12-15).

## 3. Relevant code paths
- scripts/change-workflow.sh:4979-5003 calls `change_pr_complete` (unattended and attended branches), then `change_pr_extras_print` (437-448).
- scripts/lib/change-pr.sh:55-105 `change_pr_complete`; 107-161 `change_pr_publish`; 26-53 `assert_tree_matches_attested`; 1429-1520 engine `handoff`; 1589 git push; 1621 gh pr create; 1775-1790 engine error handler (prints `PR pending: ...` to stdout, exit 1 or 3).
- Silent `return 0` in `change_pr_publish`: line 123 and 126 (verdict not READY / override declined), 128-129 (validate failed), 148 (`issue_close_eligible ... || return 0`), 159 (tree mismatch, message only to stderr); line 160 `change_pr_engine handoff || true` discards the handoff exit status.
- change-pr.sh:70 and 98 set `CHANGE_PR_EXTRAS_REASON=publication-pending` unconditionally after `change_pr_publish`, even when the PR was created.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | Unattended run, origin recorded, CLOSE_ISSUE=1 | change_pr_publish 0 with UNCLE_AUTO_PUBLISH=1 (draft when not READY) | change-pr.sh:66-72; pr-auto-publish-test.sh | Yes |
| B2 | Attended, interactive | change_pr_publish 1, dialogs | change-pr.sh:104; pr-auto-publish-test.sh | Yes |
| B3 | Handoff disabled/headless and no completed signed commit | prints disabled message, reason handoff-disabled, no PR | change-pr.sh:84-96 | Yes |
| B4 | Verdict not READY, no override | publish returns 0 silently; engine prints `PR pending:` to stdout only | change-pr.sh:120-129, 1778 | Yes (gating) |
| B5 | issue_close_eligible fails | silent return 0, no PR, no reason | change-pr.sh:145-148 | Gate yes; silence no |
| B6 | Tree differs from attested | stderr `Publish refused`, no PR | change-pr.sh:159 | Yes |
| B7 | Handoff engine fails | status discarded by `|| true` | change-pr.sh:160 | Gate yes |
| B8 | After any publish call | extras reason forced to publication-pending | change-pr.sh:70,98 | No (misleading) |
| B9 | Any path | driver exits 0 | change-workflow.sh:5004 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | Tree must match attested tree before publishing | assert_tree_matches_attested | gitignore-clean-end-test.py | High |
| I2 | Non-READY audit needs human override (or unattended draft) | engine verdict-override | pr-verdict-binding-test.sh | High |
| I3 | Never force-push | engine push at line 1589 uses plain refspec | UNRESOLVED (no dedicated test found) | Medium |
| I4 | Unattended publication never opens a dialog | UNCLE_AUTO_PUBLISH + </dev/null | pr-auto-publish-test.sh | High |
| I5 | Bash 3.2 compatible driver libs | convention | shell suites | Medium |

## 6. Interface contracts
Engine exit codes: 0 ok, 1 pending/error, 3 recoverable (not READY/attestation). `CHANGE_PR_EXTRAS_REASON` keys consumed by finished_extras.py REASONS; unknown keys fall back to not-published (finished_extras.py:106).

## 7. Existing automated-test coverage
scripts/tests/pr-auto-publish-test.sh (routing with stubbed publish/engine), pr-verdict-binding-test.sh, unattended-test.sh (stubs change_pr_complete), gitignore-clean-end-test.py, supervisor-test.py. No test exercises change_pr_publish reason reporting. Shell and Python runners use separate temp dirs and share no ports, so they run as one parallel group.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (Uncle's documented runners). Not run here; the driver's baseline (.uncle/workflow/green-check.baseline.tsv) is authoritative. Some Python suites are known to fail on a clean checkout; pre-existing failures are recorded by the driver.

## 10. Existing failures/warnings
None documented in-repo beyond the note that some Python suites fail clean. UNRESOLVED: which.

## 12. Likely change surface
scripts/lib/change-pr.sh (change_pr_complete/publish), scripts/lib/finished_extras.py (REASONS), one new shell test.

## 13. Regression-sensitive components
change_pr_publish gating order, engine handoff, attestation/tree checks, unattended routing (pr-auto-publish-test.sh stubs change_pr_publish and change_pr_engine).

## 14. Outside the change
Publication dialogs, audit/approval gates, attestation logic, home_agent_session.py, gate_answer.py, supervisor, GITHUB_INTEGRATION.md semantics.

## 15. Unknowns and assumptions
- Operator's actual skip path is unknown; static reading shows several silent returns and an overwritten reason, but none proven to be the operator's cause. Plan step 1 must reproduce.
- Assumed commits a6c05c2/355822d/45d8feb did not touch change-pr.sh (git log on it shows last change 50b8c18); the regression may be in state/inputs (e.g. verdict or origin files) rather than the library.

## 16. Initial risk assessment
Medium: wrong fix could weaken gates. Mitigation: only reporting/status changes plus whatever the reproduction proves broken.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

