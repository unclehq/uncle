# Baseline Report - Issue 141

Omitted sections: API/schema contracts (no schema; CLI text only); Reproduction (feature, not bug); Flaky behavior (none documented)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`. A `--worktree` run that reaches COMPLETE without a PR leaves the worktree and the main project untouched. Wanted: commit, remove worktree, switch main project to the run branch, with guards.

## 2. Repository architecture
Shell driver scripts under `scripts/`; `scripts/from-issue.sh` wraps `change-workflow.sh` for an issue; worktree helpers in `scripts/lib/worktrees.sh`; hermetic shell suites in `scripts/tests/*-test.sh` run by `scripts/run-shell-tests.sh`; Python suites by `scripts/run-python-tests.sh`.

## 3. Relevant code paths
- `scripts/from-issue.sh:175-192` `offer_worktree_removal` (y/N prompt).
- `scripts/from-issue.sh:195-232` `journal_signature`, `pr_created_in`.
- `scripts/from-issue.sh:241-296` `auto_removal_refusal` (path guards 243-266; untracked/pushed guards 267-294).
- `scripts/from-issue.sh:838-874` post-run block: PR path auto-removes; no-PR path prompts only when tty and attended, else prints manual remove command.
- `scripts/from-issue.sh:302-304` source-only test hook.
- `scripts/lib/worktrees.sh:213-239` `worktree_remove` (refuses on lock, non-COMPLETE state, dirty tree; keeps branch).
- `scripts/README.md:255-310` documents current removal behavior.
- `scripts/tests/worktree-run-test.sh` lines ~341-342, 596-680 (offer/prompt/kept expectations), 690-810 (PR auto-removal cases).

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | COMPLETE + valid fresh PR journal | Worktree removed, branch kept, no prompt, exit unchanged | from-issue.sh:846-863; worktree-run-test.sh ~690-810 | Yes |
| B-2 | COMPLETE, no PR, tty, attended | Prompt `Remove worktree <dir>? [y/N]` | from-issue.sh:866-870; test ~654 | No (replaced) |
| B-3 | COMPLETE, no PR, no tty or `--unattended` | Prints `Worktree <dir> kept; remove with: ...`; worktree kept; main project untouched | from-issue.sh:871-873; test ~341, ~663 | No (replaced) |
| B-4 | Driver not COMPLETE | No removal, no prompt | from-issue.sh:845 | Yes |
| B-5 | `worktree_remove` called | Refuses on lock / non-COMPLETE / dirty; keeps branch | worktrees.sh:213-239 | Yes |
| B-6 | Driver exits non-zero | Script exits with the driver status | test ~668 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | Exit status equals run's status regardless of removal outcome | `|| true` / no `set -e` effect at 870 | worktree-run-test.sh | High |
| I-2 | Branch never deleted by removal | worktree_remove uses `git worktree remove` only | worktree-run-test.sh ~617 | High |
| I-3 | Worktree never removed while lock held or state != COMPLETE | worktrees.sh:220-228 | ~486-492 | High |
| I-4 | Post-PR auto-removal only inside managed root, never the source | auto_removal_refusal | ~726-808 | High |
| I-5 | Fixture commits never sign | tests use --no-gpg-sign | worktree-run-test.sh header | High |

## 7. Existing automated-test coverage
`bash scripts/run-shell-tests.sh` (parallel suites, includes worktree-run-test.sh and close-flow-test.sh) and `bash scripts/run-python-tests.sh`. The two use separate temp dirs and no shared ports, so they are grouped. worktree-run-test.sh refuses to run while an uncle build drives the checkout (see its header); under a build it reports as skipped/refused, which is pre-existing.

## 9. Baseline test results
Not run here. Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (CHANGE_REQUEST/stage instructions). Driver baseline at `.uncle/workflow/green-check.baseline.tsv` is authoritative. Some Python suites are documented to fail on a clean checkout.

## 12. Likely change surface
`scripts/from-issue.sh` post-run block and a new helper; `scripts/README.md`; `scripts/tests/worktree-run-test.sh` (existing no-PR expectations conflict).

## 13. Regression-sensitive components
Post-PR auto-removal (B-1, `auto_removal_refusal`), `worktree_remove`, prompt helper tests that source `offer_worktree_removal` directly.

## 14. Outside the change
`change-workflow.sh`, PR creation (`change-pr.sh`), `worktree_auto`, `uncle --runs`, the TUI.

## 15. Unknowns and assumptions
- The run's base branch is not recorded; the plan derives eligibility from git ancestry instead.
- Assumption: committing in an unattended run is acceptable (answers open questions: automatic, attended and unattended).

## 16. Initial risk assessment
Medium: changes cwd/branch of the user's real checkout. Mitigated by refusing on any doubt.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

