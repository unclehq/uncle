# Change spec

Omitted sections: Performance (none); Security (folded into invariants); Migration (none); Prototype isolation (not a prototype).

## 1. Change type
Behavior change (feature).

## 2. Problem statement
A finished build in a git worktree publishes a PR only when issue-linked (baseline B-1) or when a person answers a dialog; unattended/headless non-issue worktree builds end with no PR and exit 0 (B-3), and PR failures do not fail the run (B-4).

## 3. Current behavior
See baseline B-1..B-7.

## 4. Desired behavior
When a change-workflow run in a linked worktree completes, it publishes through the existing PR engine (push of the branch, `gh pr create` against the default branch, reuse of an existing PR), with no dialog when unattended, regardless of issue origin. A failure to create the PR is reported with its reason and makes the run exit non-zero instead of claiming completion.

## 5. Observable behavior table
| ID | Class | Trigger | Current behavior | Expected behavior | Verification |
|---|---|---|---|---|---|
| OB-1 | ADD | Unattended finish in worktree, no origin | no PR, exit 0 | publish invoked with auto-publish, no dialog | shell test AC-1 |
| OB-2 | PRESERVE | Unattended issue-linked finish | auto-publish | unchanged, publish invoked exactly once | shell test AC-2 |
| OB-3 | MODIFY | Worktree run where publish yields no PR (reason not published*) | exit 0 | `change_pr_complete` returns non-zero; driver exits non-zero with reason shown | shell test AC-3 |
| OB-4 | PRESERVE | Existing PR for branch | reused by engine | unchanged | existing pr-reconcile-test.py (AC-5) |
| OB-5 | PRESERVE | Non-worktree build, any origin | existing routing, rc 0 | identical, including 'no PR was created' with no origin | shell test AC-4 |
| OB-6 | PRESERVE | WORKFLOW_CLOSE_ISSUE=0 | handoff disabled | unchanged even in worktree | shell test AC-6 |
| OB-7 | PRESERVE | Attended worktree run | dialog | unchanged dialog flow | existing test |

## 6. Invariant table
| ID | Status | Invariant | Scope | Enforcement point | Verification |
|---|---|---|---|---|---|
| INV-1 | EXISTING | No force push | PR publish | engine git push | code inspection + grep test AC-7 |
| INV-2 | EXISTING | PR only from audited tree | publish | assert_tree_matches_attested | pr-verdict-binding-test.sh |
| INV-3 | EXISTING | Issue closes only on READY audit | issue runs | issue_close_eligible | pr-verdict-binding-test.sh |
| INV-4 | NEW | A worktree run that ends with no PR never exits 0 as complete | worktree runs | change_pr_complete rc + driver exit | AC-3 |
| INV-5 | EXISTING | At most one PR per branch | publish | journal + lookup | pr-reconcile-test.py |
No RELAXED or REMOVED invariants.

## 7. Compatibility
Issue-linked and non-worktree flows unchanged. A non-zero exit applies only to worktree runs.

## 8. Error behavior
Validate/tree/handoff/verdict failures keep their reasons via `change_pr_no_pr` (stderr + extras reason) and in worktree runs additionally produce a non-zero status. An unreviewed verdict still publishes only as a draft (existing behavior).

## 12. Rollback
Revert the commit; no persistent state or schema changes.

## 14. Non-goals
Auto-merge, gate changes, worktree cleanup, greenfield workflow, engine rewrite.

## 15. Assumptions
As baseline section 15. 'Worktree' = linked worktree detected by marker or git-dir comparison.

## Acceptance criteria

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | Unattended change_pr_complete in a worktree with no ORIGIN_FILE calls change_pr_publish once with UNCLE_AUTO_PUBLISH=1 and no dialog. | New case in scripts/tests/pr-auto-publish-test.sh using a disposable linked git worktree fixture (gpg signing disabled). |
| AC-2 | Unattended issue-linked change_pr_complete still calls change_pr_publish exactly once, same arguments as before. | Existing pr-auto-publish-test.sh checks plus a call-count assertion. |
| AC-3 | In a worktree run, when publication yields a reason other than published/published-draft-unreviewed, change_pr_complete returns non-zero and the driver exits non-zero; a created PR returns zero. | New cases in pr-auto-publish-test.sh stubbing change_pr_publish to set CHANGE_PR_EXTRAS_REASON; grep assertion on change-workflow.sh exit handling. |
| AC-4 | Outside a worktree with no origin, behavior is unchanged: no publish, 'no PR was created', return 0. | New case in pr-auto-publish-test.sh in a plain git repo. |
| AC-5 | Existing PR for the branch is reused and no duplicate is created. | Existing scripts/tests/pr-reconcile-test.py passes unchanged (engine untouched). |
| AC-6 | With CLOSE_ISSUE=0 a worktree run still does not publish. | New case in pr-auto-publish-test.sh. |
| AC-7 | No force push is introduced: the diff adds no --force/-f/--force-with-lease to push commands. | git diff grep during review plus run-shell-tests.sh. |
| AC-8 | Full shell and Python suites show no new failures relative to baseline. | bash scripts/run-shell-tests.sh and bash scripts/run-python-tests.sh vs baseline. |
| AC-9 | scripts/README.md documents that every worktree run publishes a PR and that failure exits non-zero. | Manual read of README diff. |

