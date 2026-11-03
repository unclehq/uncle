# Implementation notes

### Files changed

- `scripts/from-issue.sh` — Add worktree_path_refusal (split from auto_removal_refusal) and finalize_no_pr_worktree: commit, clean check, main-project guards, remove, switch, one summary line; replace no-PR prompt/kept branches in post-run block; Selected approach steps 1-7; S-1..S-9, N-1, N-2, N-3, N-5
- `scripts/tests/worktree-run-test.sh` — New no-PR cases: switch, dirty-main, other-branch, failed-removal, switch-fail, commit-fail, guard refusals, summary text; Verification; S-1..S-10
- `scripts/README.md` — Document new no-PR commit/remove/switch behavior; drop y/N prompt as the no-PR flow; Docs; AC-6

### Deviations

- `.gitignore`: An earlier attempt added '.uncle'; outside frozen scope, so it was reverted this run. Not part of the final diff.

### Unresolved concerns

- scripts/tests/worktree-run-test.sh refuses to run inside an uncle build (nested skip); UNCLE_TEST_ALLOW_NESTED=1 override was denied by the permission classifier, so the new cases were not executed by this stage. Only bash -n syntax was checked. The driver's green check runs scripts/run-shell-tests.sh and is the authoritative result.
- Frozen-scope entry 'worktree-run-test.sh' at repo root does not exist; the real file is scripts/tests/worktree-run-test.sh.

## Acceptance delivery

| ID | Status | Changed code | Observed targeted verification |
|---|---|---|---|
| AC-1 | INCOMPLETE | scripts/from-issue.sh finalize_no_pr_worktree (commit incl. untracked, remove, switch, no prompt) | Not executed: worktree-run-test.sh skips when nested and the override was denied. bash -n passes only. |
| AC-2 | INCOMPLETE | scripts/from-issue.sh main-project guards (dirty, non-ancestor) keep worktree and print git switch | Not executed (same blocker); bash -n passes only. |
| AC-3 | INCOMPLETE | scripts/from-issue.sh failure handling for commit, removal, switch; exit status untouched | Not executed (same blocker); bash -n passes only. |
| AC-4 | INCOMPLETE | scripts/from-issue.sh single summary line 'Branch <b>: worktree removed\|kept; project switched\|not switched.' | Not executed (same blocker); bash -n passes only. |
| AC-5 | INCOMPLETE | PR path still calls auto_removal_refusal unchanged; no branch deletion | Not executed (same blocker); bash -n passes only. |
| AC-6 | IMPLEMENTED | scripts/README.md no-PR section rewritten | grep of README/from-issue.sh: remaining 'kept; remove with' strings are the PR path at from-issue.sh:326,970,973 and README:293; read inspection only. |
