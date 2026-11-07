# Baseline report

Omitted sections: Reproduction result (not executed; derived from code reading); Areas outside change folded into section 12.

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`: every finished worktree build must publish a PR (push + gh PR), issue-based or not; reuse existing PR; surface failure; no force push.

## 2. Repository architecture
Bash drivers (`scripts/change-workflow.sh`, `from-issue.sh`, `stagegate.sh`) plus Python helpers in `scripts/lib`. PR publication is `scripts/lib/change-pr.sh`: bash entry points (`change_pr_complete`, `change_pr_publish`, `change_pr_no_pr`) over a embedded Python engine `change_pr_engine` (journal at `.uncle/workflow/pr/journal.json`). Worktrees: `scripts/lib/worktrees.sh` (`worktree_auto` for non-issue runs, called via `scripts/lib/run_duties.py:prepare_worktree`; marker `.uncle/workflow/worktree-owned` written at worktrees.sh:319). Issue worktrees: `from-issue.sh --worktree`.

## 3. Relevant code paths
- change-pr.sh:55-104 `change_pr_complete`: auto-publish only when `CLOSE_ISSUE==1 && UNATTENDED==1 && -s $ORIGIN_FILE` (line 66); attended + CLOSE_ISSUE==1 -> interactive dialog; otherwise 'PR handoff disabled or unattended; no PR was created' (lines 86-95) and returns 0.
- change-pr.sh:107-200 `change_pr_publish`; issue-eligibility check only when ORIGIN_FILE non-empty (line 138); origin-less path already supported by engine (`check_remotes` ~1316, `resolve` ~1343).
- change-pr.sh engine: existing-PR lookup `gh pr list` (~1430), push of intended_head to head_branch without force (~1636), `gh pr create` (~1668).
- change-workflow.sh:4980-5004: completion; always `exit 0` after `change_pr_complete`; on_exit prints stopped extras only when rc != 0 (lines ~501-504).
- worktrees.sh:292-343 `worktree_auto`; marker line 319.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Unattended issue-linked build finishes | PR published without dialog (draft if audit not READY) | change-pr.sh:66-72; pr-auto-publish-test.sh | Yes |
| B-2 | Attended build, CLOSE_ISSUE=1 | Handoff dialog then publish | change-pr.sh:73-104 | Yes |
| B-3 | Unattended/headless worktree build with no origin file | 'no PR was created', exit 0 | change-pr.sh:86-95 (by reading) | No (the defect) |
| B-4 | PR creation fails/refused (validate/tree/handoff) | message on stderr, `change_pr_complete` returns 0, driver exits 0 | change-pr.sh:107-198, change-workflow.sh:5004 | No for worktrees |
| B-5 | Non-worktree build | unchanged flow above | same | Yes |
| B-6 | PR already exists for branch | engine looks it up and reuses | change-pr.sh ~1430-1465 | Yes |
| B-7 | WORKFLOW_CLOSE_ISSUE=0 | handoff disabled, no PR | change-pr.sh:86 | Yes (explicit opt-out) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | No force push | engine uses plain `git push` (~1636) | none direct | Medium |
| I-2 | PR only from audited tree | `assert_tree_matches_attested` (change-pr.sh:30-53, called in publish) | pr-verdict-binding-test.sh | High |
| I-3 | Issue closes only on READY | `issue_close_eligible` gate line 138+ | pr-verdict-binding-test.sh | High |
| I-4 | One PR per branch (journal + lookup) | journal phase + gh lookup | pr-reconcile-test.py | Medium |
| I-5 | Worktree directory/branch never removed by this path | worktrees.sh/from-issue.sh only | worktree-run-test.sh | High |

## 6. Interface contracts
`change_pr_complete` returns 0 always today; `CHANGE_PR_EXTRAS_REASON` values: published, published-draft-unreviewed, handoff-disabled, publication-pending, verdict-not-ready, validate-failed, tree-mismatch, handoff-failed, handoff-incomplete, issue-not-eligible. Journal schema untouched.

## 7. Existing automated-test coverage
`scripts/tests/pr-auto-publish-test.sh` stubs `change_pr_publish`/`change_pr_engine` and tests routing of `change_pr_complete` (the natural home for the no-origin case). `pr-publish-reason-test.sh`, `pr-verdict-binding-test.sh`, `pr-reconcile-test.py`, `worktree-run-test.sh`, `worktree-auto-seed-test.sh` cover neighbours. Shell suites (run-shell-tests.sh) and Python suites (run-python-tests.sh) use separate temp dirs and share no ports, so they may run as one parallel group (groups `1 2`, to be declared by the driver's parallel_groups mechanism).

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (task contract). Not executed in this stage; driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Known: some Python suites already fail on a clean checkout per stage contract; none identified here.

## 11. Reproduction
Not run. By code reading: unattended/headless run in a `worktree_auto` worktree has empty ORIGIN_FILE, so line 66 is false, `interactive=0`, and path at lines 86-95 prints 'no PR was created' and returns 0.

## 12. Likely change surface
`scripts/lib/change-pr.sh` (routing + failure return), `scripts/change-workflow.sh` (exit status at ~5004), `scripts/tests/pr-auto-publish-test.sh`, `scripts/README.md`. Probably not `worktrees.sh`/`parallel_steps.py` (named in request but not on the PR path; parallel_steps worktrees are plan step sandboxes, not run worktrees).

## 13. Regression-sensitive components
Issue-linked auto-publish (B-1), attended dialogs (B-2), journal/engine, signing-resume path, finished_extras reason reporting.

## 14. Outside the change
Auto-merge, review/approval gates, worktree cleanup, greenfield `stagegate.sh`/`workflow.sh` (no PR flow exists there), engine internals.

## 15. Unknowns and assumptions
- Assumption: 'worktree' = run inside a linked git worktree (marker `worktree-owned` or git-dir != git-common-dir).
- Assumption: 'whether or not from an issue' applies to the change-workflow driver; greenfield builds have no PR machinery and stay out of scope.
- Assumption: explicit WORKFLOW_CLOSE_ISSUE=0 opt-out remains honoured.
- Unknown: whether `.uncle/workflow/state` is written COMPLETE before change_pr_complete (not confirmed).
- Not run: live gh/network behaviour; no remote verification here.

## 16. Initial risk assessment
Medium: touches completion routing shared with issue flow; mitigated by gating on worktree detection and keeping issue path byte-identical.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

