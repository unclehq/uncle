# Change spec

Omitted sections: Performance, Security (no new surface beyond preserving gates), Migration (none), Prototype isolation (n/a).

## 1. Change type
Bug fix (regression) plus diagnosability.

## 2. Problem statement
A finished run does not push/open a PR and the operator is not told why; the finished block can also say `publication pending` after a PR was created.

## 3. Current behavior
Baseline B4-B8: several gate failures return silently; reason is overwritten.

## 4. Desired behavior
When gates pass (tree attested, verdict READY or human/unattended-draft override, origin/remote available) the branch is pushed and the PR created. On every other path the operator sees a specific reason in the finished block and on stderr. Gates are unchanged.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| SB1 | MODIFY | change_pr_publish finishes with a successful handoff | reason forced to publication-pending | reason `published` | pr-publish-reason-test.sh |
| SB2 | MODIFY | publish stops at validate failure / verdict not READY / issue not eligible / tree mismatch / handoff failure | silent or generic | distinct reason key and one stderr line naming it | pr-publish-reason-test.sh |
| SB3 | MODIFY | the reproduced skip path (if a defect) | no PR | PR created when gates pass | regression test, fails before fix |
| SB4 | PRESERVE | unattended routing, B1-B3 | as baseline | unchanged | pr-auto-publish-test.sh |
| SB5 | PRESERVE | tree mismatch or non-READY without override | no PR | still no PR | pr-publish-reason-test.sh, pr-verdict-binding-test.sh |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| SI1 | EXISTING | Tree must match attested tree before publish | change_pr_publish | assert_tree_matches_attested | gitignore-clean-end-test.py |
| SI2 | EXISTING | Non-READY audit publishes only with human override or unattended draft | engine | verdict-override | pr-verdict-binding-test.sh |
| SI3 | EXISTING | No force-push | engine | git push refspec | new test greps engine push has no force flag |
| SI4 | NEW | Every no-PR return sets a non-empty reason key | change_pr_publish/complete | CHANGE_PR_EXTRAS_REASON | pr-publish-reason-test.sh |
 No invariants RELAXED or REMOVED.

## 7. Compatibility
Driver exit status stays 0 (B9). Bash 3.2 compatible. Unknown reason keys already fall back safely.

## 8. Error behavior
Reasons never alter whether a PR is created; they only report.

## 12. Rollback
Revert the commit; no state/schema changes.

## 14. Non-goals
Dialog redesign, audit/approval gate changes, unrelated cleanup, force-push.

## 15. Assumptions
Root cause not yet proven; if reproduction shows the defect is outside change-pr.sh/finished_extras.py, implementation must stop and record a deviation.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | When gates pass and a GitHub remote exists, the publish path reaches engine handoff (push and gh pr create) and records reason `published`. | New shell test with stubbed engine drives change_pr_publish through the success path and asserts handoff called and reason published. |
| AC-2 | Each no-PR path (validate failure, verdict not READY without override, issue_close_eligible failure, tree mismatch, handoff failure) sets a distinct non-empty reason and prints one explanatory stderr line; none creates a PR. | New shell test per path asserts reason, stderr text and that handoff is not called. |
| AC-3 | change_pr_complete no longer overwrites a reason set by change_pr_publish with publication-pending. | New test asserts the reason after complete equals the one set by publish. |
| AC-4 | finished_extras.py renders each new reason key with a readable label. | Python or shell assertion on finished_extras output for each key. |
| AC-5 | If reproduction identifies a defect that skips publication when gates pass, it is fixed and covered by a regression test that fails before the fix. | Test run against pre-fix code fails; post-fix passes. Recorded in IMPLEMENTATION_NOTES.md. |
| AC-6 | Gates and force-push rules are unchanged; existing suites show no regressions. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh compared with baseline. |

