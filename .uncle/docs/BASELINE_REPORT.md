# Baseline: add `uncle --audit`

Omitted sections: Reproduction of reported bug (feature, not bug); Existing failures/flaky (none documented; driver baseline is authority)

## 1. Change-request summary
See `.uncle/docs/CHANGE_REQUEST.md`: new `uncle --audit` reruns the auditor on a branch; open questions (how auditor runs today, branch argument, output location) are answered below.

## 2. Repository architecture
- `uncle` (bash, 1074 lines): launcher. Parses flags (`uncle:240-339`), resolves mode (`uncle:340-385`), then runs TUI / headless / line menu.
- `scripts/change-workflow.sh`: state-machine driver for change requests. `scripts/stagegate.sh`: new-app driver. `scripts/from-issue.sh`: issue driver.
- State lives in `<checkout>/.uncle/workflow/state` (`change-workflow.sh:132,176`), written by `state_write` (`scripts/lib/state.sh:54`), read by `state_read` (`:17`). `.uncle/workflow/family` records `change` or `app` (`scripts/lib/workflow_family.py:15-30`).
- Per-run git worktrees: `scripts/lib/worktrees.sh` (`worktree_branch_dir` :48 maps a branch to its checkout path).

## 3. Relevant code paths
- **The auditor today is the `FINAL_AUDIT` state** of the driver: `change-workflow.sh:4838-4880` (reuses green check, runs `run_final_audit_panel` :3138, writes `.uncle/docs/FINAL_AUDIT.md`), then `VALIDATE_AUDIT` :4882-4908 (verdict classification via `scripts/lib/audit-verdict.sh`, envelope write, routing), `WAIT_AUDIT_OVERRIDE` :4910. Same state name exists in `stagegate.sh:4921`.
- Auditor output: `.uncle/docs/FINAL_AUDIT.md`, verdict file `.uncle/workflow/audit-verdict` (`:181`), envelope stage `audit`.
- Driver accepts only `-h --version --attended --unattended` (`change-workflow.sh:72-80`); it self-locks via `driver.lock` (`:113-118`) and reads mode from `UNCLE_UNATTENDED`.
- Launcher dispatch to driver: `run_change_workflow` `uncle:1020`; `run_workflow` `uncle:664`. Early-exit flags `verify`, `--performance`, `--runs` at `uncle:244-246`. Did-you-mean list at `uncle:332`. Usage text `uncle:66-120`.

## 4. Current observable behavior
| ID | Trigger | Current result | Evidence | Must preserve? |
|---|---|---|---|---|
| B-1 | `uncle --audit` | `Unknown argument: --audit`, usage, exit `$UNCLE_REFUSE_CODE` (1; 2 under --noui) | `uncle:322-338` | No (this is the change) |
| B-2 | `uncle --help` | prints usage, exit 0 | `uncle:242` | Yes, apart from adding the new line |
| B-3 | `uncle --runs` / `--performance` / `verify` | exec early-exit helpers | `uncle:244-246` | Yes |
| B-4 | `--application`/`--issue`/`--change-request` mutually exclusive | error exit 1 | `uncle:217-227` | Yes |
| B-5 | unknown flag near a known one | `Did you mean X?` | `uncle:329-335`; `scripts/tests/launcher-args-test.sh` | Yes |
| B-6 | change driver reaching FINAL_AUDIT | audit panel runs, FINAL_AUDIT.md written, verdict routed | `change-workflow.sh:4838-4908` | Yes, unchanged |
| B-7 | second concurrent driver in same checkout | refused by `driver.lock` | `change-workflow.sh:113-118` | Yes |

## 5. Existing invariants
| ID | Invariant | Current enforcement | Existing test | Confidence |
|---|---|---|---|---|
| I-1 | One driver per checkout state dir | `driver.lock` via plan-executability.py lock-run | scripts/tests (lock suites) | Medium |
| I-2 | Builds start only via app action path when `UNCLE_HOME_AGENT=1` | `uncle:343-355` | startup-action tests | Medium |
| I-3 | Audit result is bound to files/HEAD/branch and refused if they changed | `change_pr_engine bind` `change-workflow.sh:4890-4896` | change-workflow suites | Medium |
| I-4 | Unknown launcher args exit with `$UNCLE_REFUSE_CODE` | `uncle:338` | launcher-removed-flag-test.sh | High |
| I-5 | Test fixtures never use signing | project rule | launcher tests use no commits | High |

## 6. Current interface contracts
Launcher flags in usage text; driver flags above; state file format `[N:]STATE` (`workflow_family.py` strips `^\d+:`). `UNCLE_RUNTIME_ROOT` lets tests point `uncle` at a stub install (`uncle:21-23`).

## 7. Existing automated-test coverage
- Shell: `scripts/tests/launcher-args-test.sh`, `launcher-noui-test.sh`, `launcher-removed-flag-test.sh`, `launcher-stdin-text-test.sh`, run by `scripts/run-shell-tests.sh`.
- Python: `scripts/tests/*-test.py` (e.g. `startup-action-test.py`) run by `scripts/run-python-tests.sh`.
- No test covers re-entering FINAL_AUDIT from the CLI. The two runners use separate temp dirs and share no ports, hence one parallel group.

## 9. Baseline test results
Commands come from `scripts/run-shell-tests.sh` and `scripts/run-python-tests.sh` (both exist). Not run here; driver baseline (`.uncle/workflow/green-check.baseline.tsv`) is authoritative. CLAUDE.md notes some Python suites already fail on a clean checkout; none documented individually.

## 12. Likely change surface
`uncle` (flag, usage, hint list, post-mode dispatch), new `scripts/audit-command.sh`, new test `scripts/tests/audit-command-test.sh`, docs (`scripts/README.md`/README usage mention).

## 13. Regression-sensitive components
Launcher flag loop and mutual-exclusion pre-scan (`uncle:214-239`), usage text (tests may match it), did-you-mean list, `change-workflow.sh` FINAL_AUDIT/VALIDATE_AUDIT (must not be modified).

## 14. Outside the change
Auditor content/lenses/prompts (`prompts/change/final-audit.md`), `audit-verdict.sh`, `stagegate.sh`, TUI, other commands.

## 15. Unknowns and assumptions
- A1: "the auditor" = the change-workflow FINAL_AUDIT stage. `stagegate.sh` also has FINAL_AUDIT but the request's constraints and `CLAUDE.md` Existing-Code section target the change driver; app-family checkouts are refused.
- A2: Rerun is only meaningful where a prior change workflow ran (state dir, VERIFICATION_REPORT) on that branch.
- U1: whether launcher tests assert exact usage text (implementer greps before editing).

## 16. Initial risk assessment
| Risk | Level |
|---|---|
| Writing state while a live driver holds the lock | Medium: probe/refuse |
| Mode resolution skipped if dispatched too early | Medium: dispatch after `uncle:381` |
| Usage-text test breakage | Low |
| Auditor behavior altered | Low: no edits to driver

## Exact build and test commands executed

```sh
bash scripts/run-shell-tests.sh
bash scripts/run-python-tests.sh
```

## Parallel verification groups

```text
1 2
```

