# Baseline Report (Issue 149)

Omitted sections: Reproduction (not run; trigger traced statically); Areas outside change merged into 14

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md (Issue 149): Uncle must make no tracked-file edit (esp. `.gitignore`) after the final audit snapshot; checkout/worktree clean at PR publish.

## 2. Repository architecture
Python TUI (`uncle_tui.py`) + bash/python drivers under `scripts/` and `scripts/lib/`. Ignore-rule normalizer is `scripts/lib/uncle_gitignore.py`. PR publish engine is embedded Python in `scripts/lib/change-pr.sh`. Worktree lifecycle is `scripts/lib/worktrees.sh`; post-PR removal guard in `scripts/from-issue.sh`.

## 3. Relevant code paths
| Path | Role |
|---|---|
| uncle_tui.py:281-292 `_ensure_uncle_gitignored` | calls `uncle_gitignore.ensure(root)` |
| uncle_tui.py:1617 in `load_config` | calls it on EVERY load_config |
| uncle_tui.py:1708-1714 | load_config re-run whenever `.uncle/config` stamp changes (mid-run reload) |
| uncle_tui.py:3500-3510 | load_config on project switch |
| scripts/lib/uncle_gitignore.py:80-123 `ensure` | rewrites/appends tracked `.gitignore` |
| scripts/lib/uncle_gitignore.py:126-128 | CLI main calls ensure |
| scripts/lib/worktrees.sh:130 | runs the CLI on each new worktree (pre-run) |
| scripts/lib/change-pr.sh:508-620 `snapshot` | non-audit snapshots strip managed lines from `.gitignore` (:595-612); audit=True keeps exact bytes |
| scripts/lib/change-pr.sh:384,435,704-720 | attest records `reviewed_tree` (tolerant) and `commit_tree` (exact); `validate` compares both |
| scripts/lib/change-pr.sh:22-73 `change_pr_complete/publish` | completion/publish entry |
| scripts/from-issue.sh:316-345 `auto_removal_content_refusal` | refuses removal on any tracked-file porcelain entry |
| tree_fingerprint.py:21, approval_snapshot.py:7, triage_guard.py:40, parallel_steps.py:34 | consumers of `strip_managed`/`only_adds_managed` |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | TUI start / config-stamp change / project switch | `.gitignore` of project root normalized (may become ` M`) | uncle_tui.py:1617,1708-1714 | Normalization of ignore coverage: yes; tracked write: no |
| B-2 | New worktree created | worktree `.gitignore` normalized before the run | worktrees.sh:130 | yes (pre-audit, in diff) |
| B-3 | Comparison snapshots | managed `.gitignore` lines ignored | change-pr.sh:595 | until in-flight runs drain |
| B-4 | commit tree | exact `.gitignore` bytes at attest | change-pr.sh:435,717 | yes |
| B-5 | Post-PR removal | refused if tracked modification | from-issue.sh:325 | yes |
| B-6 | Canonical block | `.uncle/*`, `!.uncle/docs/`, 3 attestation negations | uncle_gitignore.py:53 | yes (non-goal to change) |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| EI-1 | commit tree equals attested commit_tree | change-pr.sh validate :717 | pr-*-test.py/sh | High |
| EI-2 | `.uncle/docs` visible to git via negation | CANONICAL block | gitignore tests | Medium |
| EI-3 | removal refuses tracked changes | from-issue.sh:325 | pr-auto-publish-test.sh | Medium |
| EI-4 | only Uncle-managed lines tolerated in guards | only_adds_managed | scripts/tests/gitignore-tolerance-test.py | High |

## 6. Interface contracts
`uncle_gitignore.ensure(root)->bool`, `strip_managed`, `only_adds_managed`, CLI `uncle_gitignore.py [root]`. `_ensure_uncle_gitignored(root)` in TUI.

## 7. Existing automated-test coverage
scripts/tests/gitignore-tolerance-test.py (tolerance); pr-auto-commit-test.py, pr-reconcile-test.py, pr-signing-test.py, pr-auto-publish-test.sh (publish). No test asserts clean `git status` after COMPLETE or that TUI reload leaves tracked files untouched. Shell and Python runners use separate temp dirs and no shared ports, so they run in parallel.

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (CLAUDE.md/Uncle task contract). Not run here; driver baseline in `.uncle/workflow/green-check.baseline.tsv` is authoritative. Some Python suites may already fail on a clean checkout.

## 10. Existing failures/flakiness
None documented in repository for this surface; UNRESOLVED until driver baseline.

## 11. Reproduction
Not executed. Static trace: `load_config` unconditionally calls `ensure` (uncle_tui.py:1617) and is re-invoked on config-stamp change (:1708-1714), so a TUI session that sees `.uncle/config` change near end of a run rewrites the main checkout's `.gitignore` (matches reported ` M .gitignore`). Worktree.sh:130 is pre-run. Snapshot tolerance (change-pr.sh:595) hides the edit from `reviewed_tree` comparison, so an edit between audit and attest enters the PR via exact-bytes commit_tree. Exact end-of-run call not live-confirmed.

## 12. Likely change surface
uncle_gitignore.py, uncle_tui.py (:281-292, :1617), worktrees.sh:130, change-pr.sh (validate/complete), tests.

## 13. Regression-sensitive components
Attestation negations (EI-2), guards using strip_managed, worktree creation, existing gitignore-tolerance test.

## 14. Outside the change
Canonical block contents; `.uncle/workflow/` snapshot treatment; stale `parallel/step-*` worktree cleanup.

## 15. Unknowns and assumptions
- Exact live trigger unconfirmed (see 11); plan removes all end-of-run tracked writes regardless.
- `.git/info/exclude` is shared by linked worktrees via the common git dir (assumed standard git behavior; verified by test in plan).

## 16. Initial risk
Medium: ignore coverage regressions could hide `.uncle/docs` from PR; tolerance removal could break in-flight runs.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

