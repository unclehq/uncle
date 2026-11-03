# Baseline Report

Omitted sections: Reproduction (feature, not a bug); Existing failures (driver baseline is authority, none documented in repo)

## 1. Change-request summary
See .uncle/docs/CHANGE_REQUEST.md (Issue 142): prompt before a new change request replaces an existing `.uncle/docs/CHANGE_REQUEST.md`.

## 2. Repository architecture
Bash drivers in `scripts/` (`from-issue.sh` seeds, `change-workflow.sh` runs stages), helpers in `scripts/lib/`, tests in `scripts/tests/` (`*-test.sh` via run-shell-tests.sh, `*-test.py` via run-python-tests.sh).

## 3. Relevant code paths
- `scripts/from-issue.sh` `change)` case (~L918-948): `check_origin_or_refuse`; if `UNCLE_NEW_WORKFLOW==1` archives workflow evidence via `workflow_family.py change`; SEED_ONLY writes under noclobber; else `seed_is_current` (L98) ? resume : `write_change_request` (~L760, unconditional `cat >` overwrite).
- `from-issue.sh` L462-470: `UNATTENDED` set by `--unattended`. L174-190 `offer_worktree_removal`: existing `read -r` y/N prompt pattern.
- `scripts/lib/change_request_stdin.py` L16,L41: `uncle --change-request` stdin path already refuses with EXISTS when file exists (no prompt).
- `scripts/lib/generated-input.sh` `generated_input_path`: resolves root vs `.uncle/docs` copy.
- `scripts/change-workflow.sh` L77 exports `UNCLE_UNATTENDED`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B1 | from-issue change mode, file exists, not current in-flight run for same issue | `write_change_request` silently overwrites | from-issue.sh ~L945-948,L760-766 | No (MODIFY) |
| B2 | same issue, run in flight | prints Resuming, file untouched | L945 | Yes |
| B3 | no existing file | file written, no prompt | write_change_request | Yes |
| B4 | `UNCLE_NEW_WORKFLOW=1` fresh start | evidence archived then reseeded | L933-943 | Yes |
| B5 | `--seed-only` with existing file | noclobber write fails | L945 | Yes |
| B6 | `--change-request` stdin with existing file | rejected with EXISTS | change_request_stdin.py L41 | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I1 | Seed never clobbers a hand-edited brief of an in-flight same-issue run | `seed_is_current` | worktree-auto-seed-test.sh / issue-document-test.sh | Medium |
| I2 | Seed-only and stdin imports never replace an existing brief | noclobber; EXISTS | issue-document-test.sh | Medium |

## 6. Interface contracts
No schema/API changes. CLI flags `--unattended`, env `UNCLE_UNATTENDED` exist; no env opt-in for replacement exists yet.

## 7. Existing automated-test coverage
issue-document-test.sh extracts functions from from-issue.sh by name and runs them in temp dirs (pattern reusable). unattended-test.sh covers unattended gating. Shell and Python runners use separate temp dirs and no shared ports, so they run in parallel (group `1 2`).

## 9. Baseline test results
Commands come from scripts/run-shell-tests.sh and scripts/run-python-tests.sh (CLAUDE task guidance). Not run here; driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authority. Some Python suites may already fail on a clean checkout.

## 12. Likely change surface
`scripts/from-issue.sh`, new test `scripts/tests/change-request-exists-prompt-test.sh`, `scripts/README.md`.

## 13. Regression-sensitive components
`seed_is_current` resume path; UNCLE_NEW_WORKFLOW archive path; worktree-auto-seed flow; TUI Start flows that call from-issue.sh non-interactively.

## 14. Outside the change
`change_request_stdin.py` (already refuses), `change-workflow.sh` stages, new-app (`new)`) flow, archiving of old requests.

## 15. Unknowns and assumptions
- Assumption: the 'new change request' entry point is from-issue.sh change mode; stdin path already refuses.
- Unknown: whether TUI invokes from-issue.sh with a tty; non-tty EOF is treated as no.

## 16. Initial risk assessment
Medium: prompt could hang or break non-interactive callers; mitigated by EOF=no and unattended default-stop.

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

