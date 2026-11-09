# Baseline: branch and worktree policy

Omitted sections: Reproduction result (not a bug); Baseline test results beyond section 9 (driver supplies); Areas outside the change folded into section 14.

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md` (Behavior change). Change runs go on a newly created branch; new application builds run in `main` of the current checkout with no worktree and no branch; refuse an app build off `main` or with uncommitted changes; keep opt-in issue worktrees.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh` = app, `scripts/change-workflow.sh` = change, `scripts/from-issue.sh` = issue) launched by `uncle` (bash), `uncle_tui.py`, `scripts/lib/uncle_headless.py`, `scripts/lib/repl_actions.py`, all via `scripts/lib/run_duties.py`. Git plumbing: `scripts/lib/worktrees.sh`, `worktree-merge.sh`, `change-pr.sh` (embedded Python engine), `project-git.sh`. Home-agent actions: `scripts/lib/home_actions.py`, `prompts/home-agent.md`.

## 3. Relevant code paths
- `scripts/lib/worktrees.sh:292` `worktree_auto`: gives EVERY non-issue run (app and change) its own worktree + new branch unless `WORKFLOW_WORKTREE=0`, already inside a worktree, or marker `.uncle/workflow/worktree-owned`; writes that marker (:319).
- Callers of `worktree_auto`: `uncle:724-748` (`run_workflow`; skips when `${1##*/}` is `from-issue.sh`), `uncle_tui.py:2381-2414` (`_enter_run_worktree`, skips `workflow_idx==1`; idx 0=app, 2=change; called :9187), `scripts/lib/run_duties.py:169-192` (`prepare_worktree(issue=...)`), `scripts/lib/uncle_headless.py:408-418` (skips `UNCLE_STARTUP_ACTION=github_issue`).
- `scripts/stagegate.sh:173` sources `worktree-merge.sh`; `:5373` area calls `uncle_ensure_project_git` (`scripts/lib/project-git.sh:3`, does `git init` when no repo); `:6818-6842` merges a finished app build from an owned worktree into the source branch (`worktree_merge_owned`, `worktree_merge_finish_all`).
- `scripts/change-workflow.sh:3834-3837`: `uncle_ensure_project_git`, then `change_pr_engine start`. Engine `start_build` (`scripts/lib/change-pr.sh:1342-1401`) creates and switches to a PR-head branch ONLY when HEAD is born, a branch is checked out, a remote exists and a default branch is known; otherwise it silently stays on the current branch (no-remote/unborn/detached = today's path). Branch name: `change_pr_engine run-branch-name` (:1900). On a non-default current branch it adopts that branch as head.
- `scripts/from-issue.sh:492-536`: `WORKTREE=1` default (comment says off), `--no-worktree`, `--worktree-dir`, `--branch`; `--new` forces `WORKTREE=0` unless explicit; explicit `--worktree` with `--new` exits 1 (:543).
- `scripts/README.md:184-196,245-322` and `docs/worktrees.md` document worktree behavior; `prompts/home-agent.md` has no branch/worktree policy (only mentions branches under cleanup rules, lines 15-16; clear/resume lines 49-56 mention issue worktrees in `home_actions.py` prompt).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Non-issue run (app or change) via `uncle`/TUI/headless, git repo, `WORKFLOW_WORKTREE` unset | Sibling worktree `<project>-<branch>` on new branch; run happens there | worktrees.sh:292-355; worktree-auto-seed-test.sh | MODIFY for app; keep for change |
| B-2 | `WORKFLOW_WORKTREE=0` or no git | Run in place; no branch created by launcher | worktrees.sh:295-296 | Change: gain branch guard |
| B-3 | Change run, remote + default branch known, HEAD on default | Engine creates/switches to new branch before first stage | change-pr.sh:1374-1401; early-branch-test.py T1 | PRESERVE |
| B-4 | Change run with no remote / unborn / detached | No branch created; edits land on current branch | change-pr.sh:1346-1351; early-branch-test.py T5 | MODIFY (gap) |
| B-5 | Change run already on non-default branch | Branch adopted as PR head | change-pr.sh:1376; early-branch-test.py T3 | PRESERVE for resume |
| B-6 | Finished app build in owned worktree | Committed and merged into source branch, worktree removed | stagegate.sh:6818-6842; README:192-196 | PRESERVE code for in-flight legacy runs |
| B-7 | `from-issue.sh N --worktree[-dir]` | Worktree on new branch, copy of `.uncle/config` | from-issue.sh:507-518; worktree-run-test.sh | PRESERVE |
| B-8 | `from-issue.sh --new --worktree` | Exit 1: `--worktree and --worktree-dir require --change` | from-issue.sh:543 | PRESERVE |
| B-9 | App build on non-main branch / dirty tree | Runs; no check | stagegate.sh (no check found) | MODIFY |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Branches are never deleted by worktree removal | worktrees.sh `worktree_create` rollback; README | worktree-run-test.sh | Medium |
| I-2 | Engine never overwrites a divergent candidate ref | change-pr.sh claim_ref | early-branch-test.py T4 | High |
| I-3 | Engine start uses only reads and one ref update; signer never invoked | change-pr.sh start_build | early-branch-test.py T6,T7 | High |
| I-4 | worktree_auto declines (returns 0, prints nothing) when unwanted/impossible | worktrees.sh:295-304 | worktree-auto-seed-test.sh | Medium |

## 6. Interface contracts
`worktree_auto <root>` prints the worktree path or nothing. `run_duties.prepare_worktree(root_dir, project_root, environ, issue, runner)` returns dir or None. Env `WORKFLOW_WORKTREE` (0 disables). `.uncle/workflow/worktree-owned` marker. No schema/API persistence changes.

## 7. Existing automated-test coverage
Shell suites via `scripts/run-shell-tests.sh`; Python (`scripts/tests/*-test.py`) via `scripts/run-python-tests.sh`. Relevant: worktree-auto-seed-test.sh, worktree-run-test.sh, worktree-branch-test.py, worktree-runs-test.py, early-branch-test.py, project-git-test.py, home-actions-test.py. ~27 suites drive `change-workflow.sh` and ~23 drive `stagegate.sh`; several create git repos (audit-command, change-workflow-exit-status, gates, worktree-run). The two runners use separate temp dirs and share no ports (per the task contract), so they run as one parallel group.

## 9. Baseline test results
Commands come from the task contract and runner scripts present in `scripts/`. No results were produced here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. Some Python suites are documented as already failing on a clean checkout.

## 12. Likely change surface
`scripts/lib/worktrees.sh`, new `scripts/lib/run-policy.sh`, `scripts/stagegate.sh`, `scripts/change-workflow.sh`, `uncle`, `uncle_tui.py`, `scripts/lib/run_duties.py`, `scripts/lib/uncle_headless.py`, docs, prompt, new tests.

## 13. Regression-sensitive components
The ~50 driver-driven suites that run git fixtures (a new branch guard or app preflight can change branch/exit behavior); worktree_auto callers; engine `start_build`; `worktree-merge.sh` legacy path.

## 14. Outside the change
Review/plan/verification stages, approval gates, `from-issue.sh` worktree creation, `worktree-merge.sh` removal, PR push/open logic, `home_actions.py` validation.

## 15. Unknowns and assumptions
- `main` meaning: assumed `main`, or `master` when the repo has no `main` branch (stock `git init`).
- Whether existing driver fixtures are on a non-main branch or dirty with a born HEAD: UNRESOLVED until the suite runs; handled as a plan risk.

## 16. Initial risk
Medium: many driver tests exercise git fixtures; launcher behavior change for app runs is user-visible.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

