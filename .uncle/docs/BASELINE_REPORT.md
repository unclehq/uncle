# Baseline report: issue 260

Omitted sections: Reproduction result (no deterministic repro; writer not observed live); Areas outside change folded into section 12

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`: uncle must not edit `.gitignore` (or any tracked file) after the code is committed / PR pushed; any `.gitignore` edit must be pre-commit, planned and in the diff; a test must show the post-push phase leaves `.gitignore` byte-identical.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh` new-app, `scripts/change-workflow.sh`, `scripts/from-issue.sh`) plus Python helpers in `scripts/lib/`. `scripts/lib/uncle_gitignore.py` owns uncle's managed ignore block. `scripts/lib/change-pr.sh` (embedded Python) binds, commits and pushes the audited change. `uncle_tui.py` is the UI.

## 3. Relevant code paths
| Where | What |
|---|---|
| `scripts/lib/uncle_gitignore.py:80` `ensure()` + `:250` CLI main | Rewrites/creates tracked `<root>/.gitignore` (the only tracked-file writer of uncle's block) |
| `scripts/lib/uncle_gitignore.py:191` `ensure_exclude()` | Writes `.git/info/exclude` only; untracked, safe |
| `scripts/lib/worktrees.sh:130` | `ensure` CLI at worktree creation (also on `--reuse-branch` reruns) |
| `scripts/lib/change-pr.sh:2097-2098` (`bind`) | `ensure('.')` in linked worktrees, before commit tree is bound |
| `scripts/lib/change-pr.sh:1963` | `git push` of the intended head (end of publish) |
| `scripts/stagegate.sh:483` (`build_attest_completed`, called `:7147`) | `ensure` CLI at completion, before `worktree_merge_finish_all` commit |
| `scripts/from-issue.sh:391-405` | `git add -A` + commit in worktree finalize (sweeps any `.gitignore` edit into the commit) |
| `uncle_tui.py:301-321,1980` | Calls `ensure_exclude` only; does not touch tracked file |
| `prompts/project-plan-investigate.md:263-279`, `docs/plan-duties.md` | New-app plan `.gitignore` duty (pre-implementation, in `Owns:`); change flow has none (`change_plan_duties.py:13`) |

The request's 'step that writes .gitignore after the push' was NOT located: no call site executes strictly after the push. Callers run at worktree creation (incl. reruns after a push), at `bind` (pre-commit) and at completion (pre-merge-commit). A bare `.uncle` line appended to `.gitignore` by an unidentified concurrent process is documented in `uncle_gitignore.py:59`; this worktree currently shows exactly that (`git diff .gitignore`: `+.uncle`).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | Worktree created for a run | Tracked `.gitignore` normalized to canonical block | `worktrees.sh:130` | Yes |
| B-2 | `change-pr.sh bind` in linked worktree | `.gitignore` normalized before commit tree bound | `change-pr.sh:2097` | Yes |
| B-3 | New-app completion | `.gitignore` normalized, then attested and merged | `stagegate.sh:483` | Yes (pre-commit) |
| B-4 | Rerun/reuse of a worktree after push | Normalization may rewrite tracked `.gitignore` again, leaving uncommitted change | `worktrees.sh:63,130`; this worktree status | No (the bug) |
| B-5 | TUI start | Only `.git/info/exclude` written | `uncle_tui.py:314` | Yes |
| B-6 | Snapshots/guards | Tolerate managed-line-only `.gitignore` diffs | `only_adds_managed` `uncle_gitignore.py:56`; `change-pr.sh:1003-1015` | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Only worktree creation (and bind in linked worktree) runs `ensure` | grep-based caller enumeration | `gitignore-clean-end-test.py` `CallerEnumeration` | Medium (stagegate.sh:483 looks like an offender under its regex; baseline run is authority) |
| I-2 | TUI never edits tracked `.gitignore` | TUI uses `ensure_exclude` | `gitignore-clean-end-test.py` `TuiHelper` | High |
| I-3 | Publish/completion guard refuses unaudited tracked edits | `assert_tree_matches_attested` `change-pr.sh:24` | `gitignore-clean-end-test.py` `Guard` | High |

## 6. Interfaces
`python3 scripts/lib/uncle_gitignore.py [root]` CLI; `ensure(root)->bool`, `ensure_exclude(root)->bool`. No schema/API consumers outside the repo.

## 7. Existing automated-test coverage
`scripts/tests/uncle-gitignore-test.sh`, `gitignore-tolerance-test.py`, `gitignore-clean-end-test.py`, `pr-snapshot-managed-ignore-test.py`, `snapshot-excludes-history-test.sh`, `worktree-run-test.sh`. No test covers the post-push phase. Shell and Python runners use separate temp dirs and share no ports, so they form one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (repo-mandated runners, per workflow instructions). Not executed here; the driver's baseline (`.uncle/workflow/green-check.baseline.tsv`) is the authority. Some Python suites are documented to fail on a clean checkout.

## 10. Existing failures
None documented in repo for this area. Possible pre-existing failure: `CallerEnumeration` vs `stagegate.sh:483` (unverified).

## 12. Likely change surface
`scripts/lib/uncle_gitignore.py`, `scripts/lib/change-pr.sh`, `scripts/from-issue.sh`, `scripts/stagegate.sh`, new test, `docs/plan-duties.md`.

## 13. Regression-sensitive components
Worktree creation normalization (B-1) that prevents tracked `.uncle/workflow-history` leakage; PR snapshot/commit-tree binding in `change-pr.sh`.

## 14. Outside the change
`ensure_exclude`, TUI, plan-stage `.gitignore` duty in new-app flow, `only_adds_managed`/`strip_managed`, self-hosted `.uncle/.gitignore`.

## 15. Unknowns
U-1: exact post-push writer unidentified (see section 3); U-2: source of stray bare `.uncle` line unknown.

## 16. Risk
Medium: `.gitignore` handling guards against a past 2379-file leak; freezing too early could skip needed normalization.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
bash scripts/run-python-tests.sh -- gitignore-post-push
```

