# Baseline report: issue 155 (unattended by default)

Omitted sections: Reproduction result (not a bug); Existing failures (none documented in-repo; the driver baseline in `.uncle/workflow/green-check.baseline.tsv` is authoritative)

## 1. Change-request summary
See CHANGE_REQUEST.md (Issue 155). Flip the default so runs are unattended; add `--attended`; deprecate `--unattended` (notice, still works); add `UNCLE_ATTENDED`; one resolver for launcher, drivers and TUI.

## 2. Repository architecture
Bash launcher `uncle` -> Python TUI `uncle_tui.py` or directly `scripts/stagegate.sh` (new app), `scripts/change-workflow.sh` (change), `scripts/from-issue.sh` (issue wrapper), `scripts/housekeeping-workflow.sh`. Shared bash libs in `scripts/lib/*.sh` read the derived variable `UNATTENDED` (about 60 sites) or the exported `UNCLE_UNATTENDED` (a few). Tests: `scripts/tests/*-test.sh` and `*-test.py`.

## 3. Relevant code paths
| Path | Lines | Role |
|---|---|---|
| `uncle` | 59-63, 85-112 | usage text naming `--unattended` |
| `uncle` | 119, 182 | `UNCLE_UNATTENDED=""`; `--unattended` case appends to `UNCLE_ARGS` |
| `uncle` | 251 | option list used for typo suggestion |
| `uncle` | 274-275 | exports `UNCLE_STARTUP_UNATTENDED=1` for the TUI |
| `uncle` | 459-476, 528 | restart loop only when `--unattended` in args; interactive path appends `--unattended` unless `misc.auto_mode false` |
| `uncle` | 771, 830 | `run_workflow stagegate.sh/change-workflow.sh ${UNCLE_ARGS[@]}` |
| `scripts/stagegate.sh` | 45-74, 119, 412, 6675 | usage, parse (`UNATTENDED=0` default), export `UNCLE_UNATTENDED`, ledger `unattended-enabled` |
| `scripts/change-workflow.sh` | 49-77, 106, 141, 431, 4958 | same pattern |
| `scripts/from-issue.sh` | 111, 485-493 | `--unattended` into `ISSUE_WORKFLOW_ARGS`; refuses CR replacement when unattended/no TTY |
| `scripts/housekeeping-workflow.sh` | 6, 272-282 | `UNCLE_HOUSEKEEPING_UNATTENDED=1` skips `Run these commands? [y/N]`; policy gate runs before (line 266) |
| `scripts/lib/upgrade-check.sh` | 71-75 | `upgrade_should_check` returns 1 when `--unattended` in `UNCLE_ARGS` or no TTY |
| `scripts/lib/{acceptance-gate,approval-gates-*,implementation-gates*,plan-recovery,audit-verdict,background-verify,change-class-stage,change-pr,repair-limit,checklist-capability}.sh` | various | consume `UNATTENDED` / `UNCLE_UNATTENDED` |
| `uncle_tui.py` | 1021-1024, 1341, 1552, 1562, 2104-2109, 2177, 2402, 5441 | startup env, auto-mode text, `cmd_for` appends `--unattended` when `_next_run_unattended()`, Shift-Tab toggle |

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `stagegate.sh`/`change-workflow.sh` direct, no flag | attended (`UNATTENDED=0`) | stagegate.sh:65 | NO (flips) |
| B-2 | any driver with `--unattended` | no prompts; gates delegated; ledger `unattended-enabled` | stagegate.sh:409-413 | YES (behavior), flag name becomes deprecated alias |
| B-3 | TUI, interactive | auto mode already default; only `misc.auto_mode false` is attended; Shift-Tab toggles | uncle_tui.py:2104-2109, 5441 | YES |
| B-4 | `uncle` interactive path | appends `--unattended` unless `misc.auto_mode false` | uncle:522-532 | YES |
| B-5 | `uncle --application T` (no flag) | TUI auto-mode default decides; direct driver path attended | uncle_tui.py:1021 | MODIFY (launcher must print mode) |
| B-6 | upgrade check | skipped with `--unattended` or no TTY, else prompts | upgrade-check.sh:71-75 | MODIFY |
| B-7 | housekeeping | attended prompt unless `UNCLE_HOUSEKEEPING_UNATTENDED=1` | housekeeping-workflow.sh:272 | MODIFY (default), policy gate PRESERVE |
| B-8 | unattended gates | `approved_by` empty, `delegated_by: unattended`, human-only checks waived, PR body states no human reviewed | approval-gates-*.sh, change-pr.sh:958,1514 | YES |
| B-9 | `--unattended` + `--attended` | `--attended` unknown arg -> error | stagegate.sh:71 | n/a |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| EI-1 | gate satisfied without a person is ledgered (`record_unattended_gate`) and reported unreviewed | approval-gates-*.sh, change-pr.sh | `unattended-test.sh`, `attestation-test.py`, `pr-auto-publish-test.sh` | high |
| EI-2 | unattended is never inferred from missing TTY | comment stagegate.sh:62-64 | `launcher-args-test.sh` (partial) | medium |
| EI-3 | failing tests stop an unattended run; waiver text `Waived by an unattended run; no person assessed this check` | acceptance-gate.sh:54-64 | `unattended-human-waiver-prompts-test.py` | high |
| EI-4 | driver exports one `UNCLE_UNATTENDED` value to subprocesses | stagegate.sh:74, change-workflow.sh:77 | `unattended-test.sh` | medium |

## 6. Current interface contracts
Flags: `--unattended` on `uncle`, `stagegate.sh`, `change-workflow.sh`, `from-issue.sh`. Env: `UNCLE_UNATTENDED` (derived/exported), `UNCLE_STARTUP_UNATTENDED` (launcher->TUI), `UNCLE_HOUSEKEEPING_UNATTENDED`, `WORKFLOW_UNATTENDED` (TUI), `WORKFLOW_UNATTENDED_HUMAN_WAIVER`. Config: `misc.auto_mode`. Files: `.uncle/workflow/unattended-gates` ledger, `.uncle/attestation.json`. No `--attended` exists.

## 7. Existing automated-test coverage
`grep` finds `unattended` in about 70 files under `scripts/tests` (22+ pass the flag) plus `scripts/uncle-verify.py`. Direct driver invocations without a flag in tests currently mean attended and will change meaning. Shell suites (`run-shell-tests.sh`) and Python suites (`run-python-tests.sh`) use separate temp dirs and no shared ports, so they run as one parallel group (per workflow documentation).

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (existing in repo). Not executed here; the driver baseline supplies results. Documented: some Python suites already fail on a clean checkout (task instructions); no in-repo flaky list found.

## 12. Likely change surface
`uncle`, `uncle_tui.py`, `scripts/stagegate.sh`, `scripts/change-workflow.sh`, `scripts/from-issue.sh`, `scripts/housekeeping-workflow.sh`, new `scripts/lib/mode.sh`, `scripts/lib/upgrade-check.sh`, tests that call drivers or the launcher, README/QUICK_START/GITHUB_INTEGRATION/docs/quickstart.

## 13. Regression-sensitive components
Every lib reading `UNATTENDED` (semantics unchanged; only the default flips); the restart loop in `uncle:471-476`; `from-issue.sh` CR replacement refusal; tests that pipe stdin answers to attended drivers.

## 14. Outside the change
What unattended does or waives; approval record format; PR publication logic; housekeeping allowlist/disallow policy gate; per-gate modes.

## 15. Unknowns and assumptions
- Exact set of tests relying on the old attended default is unknown until the suite runs; the implementer finds them from failures.
- `WORKFLOW_UNATTENDED` is read only by the TUI (uncle_tui.py:2402).
- No release-notes file exists in the repo.

## 16. Initial risk assessment
High blast radius on tests (default flips), medium on user surprise (mitigated by startup banner), low on core gate logic (unchanged).

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

