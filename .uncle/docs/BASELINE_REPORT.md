# Baseline Report (Issue 228)

Omitted sections: Reproduction of a single bug (multi-suite test-health issue; per-suite findings in section 11 instead)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`. `./scripts/run-all-tests.sh` reports 96 passed / 11 failed on main 4c23afa. Goal: 0 failed, 0 skipped, no weakened tests; classify each failure product-vs-test-vs-environment.

## 2. Repository architecture
Bash drivers (`scripts/stagegate.sh` 6918 lines, `scripts/change-workflow.sh`, `scripts/workflow.sh`), shell libs in `scripts/lib/` (`run-policy.sh`, `mode.sh`, `worktree_runs.py`, `all_suites.py`), Python TUI `uncle_tui.py`, suites in `scripts/tests/` (`*-test.sh`, `*-test.py`). `scripts/run-all-tests.sh` execs `scripts/lib/all_suites.py` (all Python+shell suites in one pool).

## 3. Relevant code paths
- `scripts/stagegate.sh:51-86` version/usage/arg parse; but `:29-38` runs `run_policy_app_preflight` (from `scripts/lib/run-policy.sh`) BEFORE arg parsing, so `--version`/`--help` are refused when the tree is dirty or not on clean main (observed: `Refusing app build: the working tree on 'main' has uncommitted changes`, empty stdout). Same ordering in `scripts/change-workflow.sh` (version at :51, args at :84).
- `scripts/tests/unattended-test.sh:39,46` sg-version-flag / `--help` documents `--unattended`.
- `scripts/lib/worktree_runs.py:55-62` raises `WorktreeListError` when `git worktree list` fails; reached from `uncle_tui.py:5750-5762` (`_resume_build`/`_latest_resumable_run`); `scripts/tests/home-actions-test.py:192,204`.
- `scripts/tests/early-branch-test.py:280-302` (t5) and t1/t3/t4; `scripts/tests/supervisor-test.py:~1785` signing audit; `scripts/tests/attestation-statement-test.py:392,447,473`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `stagegate.sh --version` in dirty tree | Run-policy refusal, no version printed | ran it | No (defect) |
| B-2 | `stagegate.sh --help` | Same preflight refusal in dirty tree; usage text itself mentions `--unattended` | usage at :54-72 | Help text yes |
| B-3 | Run policy on dirty/non-main app build | Refuses build | run-policy.sh | Yes |
| B-4 | `attestation-statement-test.py` here | 3 failures; output shows `approved artifact is ignored: .gitignore:36:.uncle` -> fixture inherits this worktree's UNCOMMITTED `.gitignore` line `.uncle`, causing tree-mismatch | ran suite; `git diff .gitignore` | Attestation ignore-boundary yes |
| B-5 | `home-actions-test.py` resume tests | `WorktreeListError: fatal: not a git repository` from `git worktree list` | ran suite | Error on real git failure: yes |
| B-6 | `early-branch-test.py` t5 | Unexpected `refs/heads/uncle/early-branch-demo` created in a case that must create no ref | ran suite | Yes |
| B-7 | `supervisor-test.py` signing audit | Lists fixture commits without explicit no-sign flags, e.g. `tree-attested-final-audit-test.sh:10`, `build-attestation-test.py:34,62` (+1) | ran suite | Policy yes |
| B-8 | `worktree-run-test.sh` | Did NOT reproduce exit 127 locally (no FAIL lines) | ran suite | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | App builds start only from clean main | `run-policy.sh` preflight | run-policy tests | High |
| I-2 | Every fixture git commit/tag disables signing | convention + audit test | `supervisor-test.py` signing audit | High |
| I-3 | `.uncle`-ignored artifacts never enter attested tree boundary | attestation code | `attestation-statement-test.py` | Medium |
| I-4 | Early-branch skips (no remote/detached/unborn) create no ref/journal | early-branch code | `early-branch-test.py` | Medium |

## 6. Interface contracts
`stagegate.sh --version` prints `0.1.0`, exit 0; `--help` exits 0 and documents `--unattended`; same for `change-workflow.sh`. `run-all-tests.sh` exit 0 only if all suites pass.

## 7. Existing automated-test coverage
Suites run in a shared pool by `all_suites.py`; shell and Python suites use separate temp dirs, so they are grouped. Critical-tier default runners skip non-critical suites; full coverage needs `run-all-tests.sh`.

## 9. Baseline test results
Commands come from `scripts/README.md`/runners. Not run here (driver baseline is authority). Issue documents 96 passed / 11 failed; the failing list is in CHANGE_REQUEST. Failures may differ by environment: this worktree has an uncommitted `.gitignore` line `.uncle` and branch `uncle/fix-...`, which plausibly explain B-1, B-4 (not main-clean).

## 10. Existing failures, warnings, flakiness
See section 4 rows B-1..B-8. Not reproduced locally: worktree-run exit 127 (likely PATH/tool assumption in CI/sandbox), gates-verification-integrity* (IMPLEMENT vs REPAIR/COMPLETE; possibly a consequence of the same dirty-tree/run-policy or git-signing behavior). UNRESOLVED until driver baseline logs.

## 12. Likely change surface
`scripts/stagegate.sh`, `scripts/change-workflow.sh` (arg parsing before preflight); `scripts/lib/worktree_runs.py` or `uncle_tui.py` caller / test fixtures (home-actions); early-branch implementation or fixture; fixture git calls in `tree-attested-final-audit-test.sh`, `build-attestation-test.py` and others flagged by the signing audit; attestation fixture `.gitignore` isolation; gates-verification-integrity suites.

## 13. Regression-sensitive components
Run policy (I-1), attestation boundary (I-3), early-branch ref mutation (I-4), signing hygiene (I-2).

## 14. Outside the change
No weakening/deleting/skipping tests; no unrelated cleanup; no change to run-policy semantics for real builds.

## 15. Unknowns and assumptions
- Which failures are caused by this worktree's state vs. real on clean main is unknown; plan requires reproducing in a clean checkout (`git worktree` of main HEAD) first.
- Exit 127 cause and gates-verification-integrity cause are unknown.

## 16. Initial risk
Medium: many independent root causes; changing preflight ordering must not let real builds bypass I-1.

## Exact build and test commands executed

```sh
bash scripts/run-all-tests.sh
```

